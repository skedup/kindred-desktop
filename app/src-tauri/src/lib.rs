mod origin;
mod preferences;
mod transport;

#[cfg(target_os = "macos")]
mod macos_lifecycle;

use preferences::{save_atomic, ShellPreferences, PREFERENCES_FILE};
use serde::Serialize;
use std::{
    collections::{BTreeSet, VecDeque},
    path::PathBuf,
    sync::Mutex,
    time::Duration,
};
use tauri::{
    menu::{CheckMenuItem, Menu, MenuItem, PredefinedMenuItem, Submenu},
    AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, State, WebviewUrl, WebviewWindow,
    WebviewWindowBuilder, WindowEvent,
};
use tokio::sync::watch;

const MENU_SETTINGS: &str = "settings";
const MENU_ALWAYS_ON_TOP: &str = "always-on-top";
const MENU_RETRY: &str = "retry";
const MENU_OPEN_KINDRED: &str = "open-kindred";
const MENU_QUIT: &str = "quit";
const WINDOW_WIDTH: f64 = 320.0;
const WINDOW_HEIGHT: f64 = 540.0;
const MAX_PRE_CANCELLED_REQUESTS: usize = 64;
const WINDOW_POSITION_DEBOUNCE: Duration = Duration::from_millis(350);

struct RuntimeState {
    preferences: ShellPreferences,
    observation_generation: u64,
    preferences_path: Option<PathBuf>,
    capabilities: ShellCapabilities,
    window_position_revision: u64,
    window_persist_worker_running: bool,
}

struct AppState {
    runtime: Mutex<RuntimeState>,
    native_suspensions: Mutex<NativeSuspensionState>,
    http: reqwest::Client,
    snapshot_gate: tokio::sync::Mutex<()>,
    snapshot_requests: Mutex<SnapshotRequestControl>,
}

struct ActiveSnapshotRequest {
    id: String,
    cancel: watch::Sender<bool>,
}

#[derive(Default)]
struct SnapshotRequestControl {
    active: Option<ActiveSnapshotRequest>,
    pre_cancelled: VecDeque<String>,
}

#[derive(Clone, Serialize)]
struct PreferencesEnvelope {
    preferences: ShellPreferences,
    observation_generation: u64,
    capabilities: ShellCapabilities,
}

#[derive(Clone, Default, Serialize)]
struct ShellCapabilities {
    transparent_window: bool,
}

#[derive(Default)]
struct NativeSuspensionState {
    active_reasons: BTreeSet<&'static str>,
    revision: u64,
}

#[derive(Clone, Serialize)]
struct SuspensionEvent {
    reason: &'static str,
    suspended: bool,
    revision: u64,
}

#[derive(Clone, Serialize)]
struct SuspensionEnvelope {
    active_reasons: Vec<&'static str>,
    revision: u64,
}

#[derive(Clone, Serialize)]
struct ShellMenuEvent {
    command: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    always_on_top: Option<bool>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<String>,
}

impl AppState {
    fn new() -> Result<Self, String> {
        Ok(Self {
            runtime: Mutex::new(RuntimeState {
                preferences: ShellPreferences::default(),
                observation_generation: 1,
                preferences_path: None,
                capabilities: ShellCapabilities::default(),
                window_position_revision: 0,
                window_persist_worker_running: false,
            }),
            native_suspensions: Mutex::new(NativeSuspensionState::default()),
            http: transport::build_client()?,
            snapshot_gate: tokio::sync::Mutex::new(()),
            snapshot_requests: Mutex::new(SnapshotRequestControl::default()),
        })
    }

    fn envelope(&self) -> Result<PreferencesEnvelope, String> {
        let runtime = self
            .runtime
            .lock()
            .map_err(|_| "state_unavailable".to_owned())?;
        Ok(PreferencesEnvelope {
            preferences: runtime.preferences.clone(),
            observation_generation: runtime.observation_generation,
            capabilities: runtime.capabilities.clone(),
        })
    }
}

impl NativeSuspensionState {
    fn update(&mut self, reason: &'static str, suspended: bool) -> Option<SuspensionEvent> {
        let changed = if suspended {
            self.active_reasons.insert(reason)
        } else {
            self.active_reasons.remove(reason)
        };
        if !changed {
            return None;
        }
        self.revision = self.revision.saturating_add(1);
        Some(SuspensionEvent {
            reason,
            suspended,
            revision: self.revision,
        })
    }

    fn envelope(&self) -> SuspensionEnvelope {
        SuspensionEnvelope {
            active_reasons: self.active_reasons.iter().copied().collect(),
            revision: self.revision,
        }
    }
}

impl SnapshotRequestControl {
    fn register(&mut self, request_id: &str) -> Result<watch::Receiver<bool>, String> {
        if let Some(index) = self
            .pre_cancelled
            .iter()
            .position(|candidate| candidate == request_id)
        {
            self.pre_cancelled.remove(index);
            return Err("snapshot_request_cancelled".to_owned());
        }
        if self.active.is_some() {
            return Err("snapshot_request_in_flight".to_owned());
        }
        let (cancel, receiver) = watch::channel(false);
        self.active = Some(ActiveSnapshotRequest {
            id: request_id.to_owned(),
            cancel,
        });
        Ok(receiver)
    }

    fn cancel(&mut self, request_id: &str) {
        if let Some(active) = self
            .active
            .as_ref()
            .filter(|active| active.id == request_id)
        {
            active.cancel.send_replace(true);
            return;
        }
        if self.pre_cancelled.iter().any(|value| value == request_id) {
            return;
        }
        if self.pre_cancelled.len() == MAX_PRE_CANCELLED_REQUESTS {
            self.pre_cancelled.pop_front();
        }
        self.pre_cancelled.push_back(request_id.to_owned());
    }

    fn finish(&mut self, request_id: &str) {
        if self
            .active
            .as_ref()
            .is_some_and(|active| active.id == request_id)
        {
            self.active = None;
        }
    }
}

#[tauri::command]
fn get_preferences(state: State<'_, AppState>) -> Result<PreferencesEnvelope, String> {
    state.envelope()
}

#[tauri::command]
fn get_native_suspensions(
    app: AppHandle,
    state: State<'_, AppState>,
) -> Result<SuspensionEnvelope, String> {
    #[cfg(target_os = "macos")]
    macos_lifecycle::refresh_current_state(&app).map_err(str::to_owned)?;
    #[cfg(not(target_os = "macos"))]
    let _ = app;
    state
        .native_suspensions
        .lock()
        .map(|value| value.envelope())
        .map_err(|_| "state_unavailable".to_owned())
}

pub(crate) fn update_native_suspension(app: &AppHandle, reason: &'static str, suspended: bool) {
    let Some(state) = app.try_state::<AppState>() else {
        return;
    };
    let event = state
        .native_suspensions
        .lock()
        .ok()
        .and_then(|mut value| value.update(reason, suspended));
    if let Some(event) = event {
        let _ = app.emit("kindred://suspension", event);
    }
}

#[tauri::command]
fn save_preferences(
    window: WebviewWindow,
    state: State<'_, AppState>,
    preferences: ShellPreferences,
) -> Result<PreferencesEnvelope, String> {
    let mut candidate = preferences.validate().map_err(str::to_owned)?;
    let mut runtime = state
        .runtime
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?;
    candidate.window = runtime.preferences.window.clone();
    let source_changed = !candidate.observation_source_equal(&runtime.preferences);
    let path = runtime
        .preferences_path
        .as_ref()
        .ok_or_else(|| "preferences_path_unavailable".to_owned())?;
    let previous_always_on_top = runtime.preferences.always_on_top;
    if candidate.always_on_top != previous_always_on_top {
        window
            .set_always_on_top(candidate.always_on_top)
            .map_err(|_| "window_level_failed".to_owned())?;
    }
    if let Err(error) = save_atomic(path, &candidate) {
        if candidate.always_on_top != previous_always_on_top {
            let (actual, rollback_failed) = reconcile_window_level_after_failed_save(
                &window,
                &mut runtime,
                previous_always_on_top,
                candidate.always_on_top,
            );
            drop(runtime);
            sync_application_menu_window_level(window.app_handle(), actual);
            if rollback_failed {
                emit_shell_menu(
                    window.app_handle(),
                    MENU_ALWAYS_ON_TOP,
                    Some(actual),
                    Some("window_level_rollback_failed".to_owned()),
                );
                return Err(format!("{error};window_level_rollback_failed"));
            }
        }
        return Err(error);
    }
    runtime.preferences = candidate;
    if source_changed {
        runtime.observation_generation = runtime.observation_generation.saturating_add(1);
    }
    let envelope = PreferencesEnvelope {
        preferences: runtime.preferences.clone(),
        observation_generation: runtime.observation_generation,
        capabilities: runtime.capabilities.clone(),
    };
    let always_on_top = runtime.preferences.always_on_top;
    drop(runtime);
    sync_application_menu_window_level(window.app_handle(), always_on_top);
    Ok(envelope)
}

#[tauri::command]
async fn fetch_visual_snapshot(
    state: State<'_, AppState>,
    request_id: String,
) -> Result<transport::SnapshotEnvelope, String> {
    validate_request_id(&request_id)?;
    let _request_guard = state.snapshot_gate.lock().await;
    let mut cancellation = state
        .snapshot_requests
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?
        .register(&request_id)?;
    let (origin, source_label, generation) = {
        let runtime = state
            .runtime
            .lock()
            .map_err(|_| "state_unavailable".to_owned())?;
        let profile = runtime.preferences.active_profile();
        (
            profile.base_url.clone(),
            profile.label.clone(),
            runtime.observation_generation,
        )
    };
    let result = tokio::select! {
        snapshot = transport::fetch(&state.http, &origin) => snapshot,
        changed = cancellation.changed() => {
            let _ = changed;
            Err("snapshot_request_cancelled".to_owned())
        }
    };
    state
        .snapshot_requests
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?
        .finish(&request_id);
    let snapshot = result?;
    let runtime = state
        .runtime
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?;
    if runtime.observation_generation != generation {
        return Err("stale_observation_generation".to_owned());
    }
    Ok(transport::SnapshotEnvelope {
        snapshot,
        observation_generation: generation,
        source_label,
    })
}

#[tauri::command]
fn cancel_visual_snapshot(state: State<'_, AppState>, request_id: String) -> Result<(), String> {
    validate_request_id(&request_id)?;
    state
        .snapshot_requests
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?
        .cancel(&request_id);
    Ok(())
}

fn validate_request_id(request_id: &str) -> Result<(), String> {
    if request_id.len() != 36
        || request_id.char_indices().any(|(index, character)| {
            if matches!(index, 8 | 13 | 18 | 23) {
                character != '-'
            } else {
                !character.is_ascii_hexdigit()
            }
        })
    {
        return Err("invalid_snapshot_request_id".to_owned());
    }
    Ok(())
}

#[tauri::command]
fn open_kindred(state: State<'_, AppState>, observation_generation: u64) -> Result<(), String> {
    let origin = {
        let runtime = state
            .runtime
            .lock()
            .map_err(|_| "state_unavailable".to_owned())?;
        current_origin_for_generation(&runtime, observation_generation)?
    };
    open_external_origin(&origin)
}

fn current_origin_for_generation(
    runtime: &RuntimeState,
    observation_generation: u64,
) -> Result<String, String> {
    if runtime.observation_generation != observation_generation {
        return Err("stale_observation_generation".to_owned());
    }
    Ok(runtime.preferences.active_profile().base_url.clone())
}

#[tauri::command]
fn show_context_menu(window: WebviewWindow, state: State<'_, AppState>) -> Result<(), String> {
    let always_on_top = state
        .runtime
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?
        .preferences
        .always_on_top;
    let settings = MenuItem::with_id(&window, MENU_SETTINGS, "Settings…", true, None::<&str>)
        .map_err(|_| "context_menu_failed".to_owned())?;
    let keep_on_top = CheckMenuItem::with_id(
        &window,
        MENU_ALWAYS_ON_TOP,
        "Keep on Top",
        true,
        always_on_top,
        None::<&str>,
    )
    .map_err(|_| "context_menu_failed".to_owned())?;
    let retry = MenuItem::with_id(
        &window,
        MENU_RETRY,
        "Retry observation now",
        true,
        None::<&str>,
    )
    .map_err(|_| "context_menu_failed".to_owned())?;
    let open = MenuItem::with_id(
        &window,
        MENU_OPEN_KINDRED,
        "Open Kindred in Browser",
        true,
        None::<&str>,
    )
    .map_err(|_| "context_menu_failed".to_owned())?;
    let separator =
        PredefinedMenuItem::separator(&window).map_err(|_| "context_menu_failed".to_owned())?;
    let quit = MenuItem::with_id(&window, MENU_QUIT, "Quit Kindred", true, None::<&str>)
        .map_err(|_| "context_menu_failed".to_owned())?;
    let menu = Menu::with_items(
        &window,
        &[&settings, &keep_on_top, &retry, &open, &separator, &quit],
    )
    .map_err(|_| "context_menu_failed".to_owned())?;
    window
        .popup_menu(&menu)
        .map_err(|_| "context_menu_failed".to_owned())
}

fn application_menu(app: &tauri::AppHandle) -> tauri::Result<Menu<tauri::Wry>> {
    let about = PredefinedMenuItem::about(app, None, None)?;
    let first_separator = PredefinedMenuItem::separator(app)?;
    let second_separator = PredefinedMenuItem::separator(app)?;
    let settings = MenuItem::with_id(app, MENU_SETTINGS, "Settings…", true, Some("CmdOrCtrl+,"))?;
    let keep_on_top = CheckMenuItem::with_id(
        app,
        MENU_ALWAYS_ON_TOP,
        "Keep on Top",
        true,
        true,
        None::<&str>,
    )?;
    let retry = MenuItem::with_id(
        app,
        MENU_RETRY,
        "Retry observation now",
        true,
        Some("CmdOrCtrl+R"),
    )?;
    let open = MenuItem::with_id(
        app,
        MENU_OPEN_KINDRED,
        "Open Kindred in Browser",
        true,
        None::<&str>,
    )?;
    let quit = MenuItem::with_id(
        app,
        MENU_QUIT,
        "Quit Kindred Desktop Spirit",
        true,
        Some("CmdOrCtrl+Q"),
    )?;
    let app_menu = Submenu::with_items(
        app,
        "Kindred Desktop Spirit",
        true,
        &[
            &about,
            &first_separator,
            &settings,
            &keep_on_top,
            &retry,
            &open,
            &second_separator,
            &quit,
        ],
    )?;
    Menu::with_items(app, &[&app_menu])
}

fn handle_menu(app: &tauri::AppHandle, id: &str) {
    match id {
        MENU_SETTINGS | MENU_RETRY => {
            let command = if id == MENU_SETTINGS {
                MENU_SETTINGS
            } else {
                MENU_RETRY
            };
            emit_shell_menu(app, command, None, None);
        }
        MENU_OPEN_KINDRED => {
            let result = if let Some(state) = app.try_state::<AppState>() {
                if let Ok(runtime) = state.runtime.lock() {
                    open_external_origin(&runtime.preferences.active_profile().base_url)
                } else {
                    Err("state_unavailable".to_owned())
                }
            } else {
                Err("state_unavailable".to_owned())
            };
            if let Err(error) = result {
                emit_shell_menu(app, MENU_OPEN_KINDRED, None, Some(error));
            }
        }
        MENU_ALWAYS_ON_TOP => match toggle_always_on_top(app) {
            Ok(always_on_top) => {
                emit_shell_menu(app, MENU_ALWAYS_ON_TOP, Some(always_on_top), None);
            }
            Err(error) => {
                let current = current_always_on_top(app);
                if let Some(value) = current {
                    sync_application_menu_window_level(app, value);
                }
                emit_shell_menu(app, MENU_ALWAYS_ON_TOP, current, Some(error));
            }
        },
        MENU_QUIT => app.exit(0),
        _ => {}
    }
}

fn emit_shell_menu(
    app: &AppHandle,
    command: &'static str,
    always_on_top: Option<bool>,
    error: Option<String>,
) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.emit(
            "kindred://menu",
            ShellMenuEvent {
                command,
                always_on_top,
                error,
            },
        );
    }
}

fn current_always_on_top(app: &AppHandle) -> Option<bool> {
    app.try_state::<AppState>()?
        .runtime
        .lock()
        .ok()
        .map(|runtime| runtime.preferences.always_on_top)
}

fn reconcile_window_level_after_failed_save(
    window: &WebviewWindow,
    runtime: &mut RuntimeState,
    previous: bool,
    attempted: bool,
) -> (bool, bool) {
    if window.set_always_on_top(previous).is_ok() {
        return (previous, false);
    }
    let actual = window.is_always_on_top().unwrap_or(attempted);
    runtime.preferences.always_on_top = actual;
    (actual, true)
}

fn toggle_always_on_top(app: &tauri::AppHandle) -> Result<bool, String> {
    let window = app
        .get_webview_window("main")
        .ok_or_else(|| "window_unavailable".to_owned())?;
    let state = app.state::<AppState>();
    let mut runtime = state
        .runtime
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?;
    let path = runtime
        .preferences_path
        .as_ref()
        .ok_or_else(|| "preferences_path_unavailable".to_owned())?;
    let previous = runtime.preferences.always_on_top;
    let next = !previous;
    window.set_always_on_top(next).map_err(|_| {
        sync_application_menu_window_level(app, previous);
        "window_level_failed".to_owned()
    })?;
    let mut candidate = runtime.preferences.clone();
    candidate.always_on_top = next;
    if let Err(error) = save_atomic(path, &candidate) {
        let (actual, rollback_failed) =
            reconcile_window_level_after_failed_save(&window, &mut runtime, previous, next);
        drop(runtime);
        sync_application_menu_window_level(app, actual);
        return if rollback_failed {
            Err(format!("{error};window_level_rollback_failed"))
        } else {
            Err(error)
        };
    }
    runtime.preferences = candidate;
    drop(runtime);
    sync_application_menu_window_level(app, next);
    Ok(next)
}

fn sync_application_menu_window_level(app: &tauri::AppHandle, checked: bool) {
    let Some(menu) = app.menu() else {
        return;
    };
    let Ok(items) = menu.items() else {
        return;
    };
    for item in items {
        let Some(submenu) = item.as_submenu() else {
            continue;
        };
        let Some(item) = submenu.get(MENU_ALWAYS_ON_TOP) else {
            continue;
        };
        if let Some(check) = item.as_check_menuitem() {
            let _ = check.set_checked(checked);
        }
    }
}

fn open_external_origin(origin: &str) -> Result<(), String> {
    let origin = origin::validate_origin(origin).map_err(str::to_owned)?;
    #[cfg(target_os = "macos")]
    {
        use objc2_app_kit::NSWorkspace;
        use objc2_foundation::{NSString, NSURL};

        let value = NSString::from_str(&origin);
        let url =
            NSURL::URLWithString(&value).ok_or_else(|| "external_browser_failed".to_owned())?;
        if NSWorkspace::sharedWorkspace().openURL(&url) {
            Ok(())
        } else {
            Err("external_browser_failed".to_owned())
        }
    }
    #[cfg(not(target_os = "macos"))]
    {
        let _ = origin;
        Err("unsupported_desktop_platform".to_owned())
    }
}

fn navigation_allowed(url: &url::Url) -> bool {
    if url.scheme() == "tauri" && url.host_str() == Some("localhost") {
        return matches!(url.path(), "/" | "/desktop.html");
    }
    cfg!(debug_assertions)
        && url.scheme() == "http"
        && url.host_str() == Some("127.0.0.1")
        && url.port() == Some(1420)
        && matches!(url.path(), "/" | "/desktop.html")
}

fn initialize_runtime(
    app: &tauri::App,
    state: &AppState,
) -> Result<(), Box<dyn std::error::Error>> {
    let preferences_path = app.path().app_config_dir()?.join(PREFERENCES_FILE);
    let preferences = preferences::load(&preferences_path);
    let mut runtime = state.runtime.lock().map_err(|_| "state_unavailable")?;
    runtime.preferences = preferences;
    runtime.preferences_path = Some(preferences_path);
    Ok(())
}

fn build_with_transparent_fallback<T, E>(
    force_decorated: bool,
    build_transparent: impl FnOnce() -> Result<T, E>,
    build_decorated: impl FnOnce(Option<&E>) -> Result<T, E>,
) -> Result<(T, bool), E> {
    if force_decorated {
        return build_decorated(None).map(|window| (window, false));
    }
    match build_transparent() {
        Ok(window) => Ok((window, true)),
        Err(error) => build_decorated(Some(&error)).map(|window| (window, false)),
    }
}

fn build_window(app: &tauri::App, decorated: bool) -> tauri::Result<WebviewWindow> {
    WebviewWindowBuilder::new(app, "main", WebviewUrl::App("desktop.html".into()))
        .title("Kindred")
        .inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        .min_inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        .max_inner_size(WINDOW_WIDTH, WINDOW_HEIGHT)
        .resizable(false)
        .maximizable(false)
        .minimizable(decorated)
        .decorations(decorated)
        .transparent(!decorated)
        .shadow(decorated)
        .skip_taskbar(false)
        .visible(false)
        .on_navigation(navigation_allowed)
        .build()
}

fn create_window(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let force_decorated = std::env::var_os("KINDRED_DESKTOP_DECORATED").is_some();
    let (always_on_top, geometry) = app
        .state::<AppState>()
        .runtime
        .lock()
        .map(|runtime| {
            (
                runtime.preferences.always_on_top,
                runtime.preferences.window.clone(),
            )
        })
        .unwrap_or((true, None));
    let (window, transparent_window) = build_with_transparent_fallback(
        force_decorated,
        || build_window(app, false),
        |transparent_error| {
            if let Some(transparent_error) = transparent_error {
                if let Some(partial) = app.get_webview_window("main") {
                    let _ = partial.destroy();
                }
                eprintln!(
                    "transparent desktop window unavailable ({transparent_error}); using decorated fallback"
                );
            }
            build_window(app, true)
        },
    )?;
    window
        .set_always_on_top(always_on_top)
        .map_err(|_| "window_level_failed")?;

    if let Ok(mut runtime) = app.state::<AppState>().runtime.lock() {
        runtime.capabilities.transparent_window = transparent_window;
    }

    if let Some(geometry) = geometry {
        let _ = window.set_position(PhysicalPosition::new(geometry.x, geometry.y));
    }
    clamp_window_to_displays(&window.as_ref().window());
    sync_application_menu_window_level(app.handle(), always_on_top);
    window.show()?;
    Ok(())
}

fn clamp_window_to_displays(window: &tauri::Window) {
    let Ok(monitors) = window.available_monitors() else {
        return;
    };
    let Ok(position) = window.outer_position() else {
        return;
    };
    let Ok(size) = window.outer_size() else {
        return;
    };
    let target = monitors
        .iter()
        .find(|monitor| {
            let area = monitor.work_area();
            position.x >= area.position.x
                && position.x < area.position.x + area.size.width as i32
                && position.y >= area.position.y
                && position.y < area.position.y + area.size.height as i32
        })
        .or_else(|| monitors.first());
    let Some(monitor) = target else {
        return;
    };
    let area = monitor.work_area();
    let clamped = clamp_position_to_work_area(position, size, area.position, area.size);
    if clamped != position {
        let _ = window.set_position(clamped);
    }
}

fn clamp_position_to_work_area(
    position: PhysicalPosition<i32>,
    window_size: PhysicalSize<u32>,
    area_position: PhysicalPosition<i32>,
    area_size: PhysicalSize<u32>,
) -> PhysicalPosition<i32> {
    let max_x = area_position.x + (area_size.width.saturating_sub(window_size.width)) as i32;
    let max_y = area_position.y + (area_size.height.saturating_sub(window_size.height)) as i32;
    PhysicalPosition::new(
        position
            .x
            .clamp(area_position.x, max_x.max(area_position.x)),
        position
            .y
            .clamp(area_position.y, max_y.max(area_position.y)),
    )
}

fn queue_window_position_persist(window: &tauri::Window, position: PhysicalPosition<i32>) {
    let state = window.state::<AppState>();
    let Ok(mut runtime) = state.runtime.lock() else {
        return;
    };
    runtime.preferences.window = Some(preferences::WindowGeometry {
        x: position.x,
        y: position.y,
    });
    runtime.window_position_revision = runtime.window_position_revision.saturating_add(1);
    if runtime.window_persist_worker_running {
        return;
    }
    runtime.window_persist_worker_running = true;
    drop(runtime);

    let app = window.app_handle().clone();
    tauri::async_runtime::spawn(async move {
        loop {
            let observed_revision = {
                let state = app.state::<AppState>();
                let Ok(runtime) = state.runtime.lock() else {
                    return;
                };
                runtime.window_position_revision
            };
            tokio::time::sleep(WINDOW_POSITION_DEBOUNCE).await;
            {
                let state = app.state::<AppState>();
                let Ok(mut runtime) = state.runtime.lock() else {
                    return;
                };
                if runtime.window_position_revision != observed_revision {
                    continue;
                }
                runtime.window_persist_worker_running = false;
                if let Some(path) = &runtime.preferences_path {
                    let _ = save_atomic(path, &runtime.preferences);
                }
            }
            return;
        }
    });
}

fn persist_runtime_preferences(app: &AppHandle) -> Result<(), String> {
    let state = app.state::<AppState>();
    let runtime = state
        .runtime
        .lock()
        .map_err(|_| "state_unavailable".to_owned())?;
    let path = runtime
        .preferences_path
        .as_ref()
        .ok_or_else(|| "preferences_path_unavailable".to_owned())?;
    save_atomic(path, &runtime.preferences)
}

pub fn run() {
    let state = AppState::new().expect("failed to initialize desktop host");
    let app = tauri::Builder::default()
        .manage(state)
        .menu(application_menu)
        .on_menu_event(|app, event| handle_menu(app, event.id().as_ref()))
        .on_window_event(|window, event| match event {
            WindowEvent::CloseRequested { .. } => window.app_handle().exit(0),
            WindowEvent::Moved(_) => {
                clamp_window_to_displays(window);
                if let Ok(position) = window.outer_position() {
                    queue_window_position_persist(window, position);
                }
            }
            WindowEvent::ScaleFactorChanged { .. } => clamp_window_to_displays(window),
            _ => {}
        })
        .setup(|app| {
            let state = app.state::<AppState>();
            initialize_runtime(app, &state)?;
            #[cfg(target_os = "macos")]
            macos_lifecycle::register(app.handle().clone());
            create_window(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            cancel_visual_snapshot,
            fetch_visual_snapshot,
            get_native_suspensions,
            get_preferences,
            open_kindred,
            save_preferences,
            show_context_menu,
        ])
        .build(tauri::generate_context!())
        .expect("error while building Kindred desktop spirit");
    app.run(|app, event| {
        if matches!(event, tauri::RunEvent::ExitRequested { .. }) {
            let _ = persist_runtime_preferences(app);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn top_level_navigation_is_packaged_only_in_release_policy() {
        assert!(navigation_allowed(
            &url::Url::parse("tauri://localhost/desktop.html").unwrap()
        ));
        assert!(!navigation_allowed(
            &url::Url::parse("https://kindred.example/").unwrap()
        ));
    }

    #[test]
    fn suspension_payload_is_serializable_and_narrow() {
        let event = SuspensionEvent {
            reason: "sleep",
            suspended: true,
            revision: 4,
        };
        assert_eq!(
            serde_json::to_value(event).unwrap(),
            serde_json::json!({"reason": "sleep", "suspended": true, "revision": 4})
        );
    }

    #[test]
    fn independent_native_suspension_sources_remain_active_until_each_clears() {
        let mut state = NativeSuspensionState::default();
        assert_eq!(state.update("session-inactive", true).unwrap().revision, 1);
        assert_eq!(state.update("screen-locked", true).unwrap().revision, 2);
        assert!(state.update("screen-locked", true).is_none());
        assert_eq!(state.update("session-inactive", false).unwrap().revision, 3);
        assert_eq!(state.envelope().active_reasons, vec!["screen-locked"]);
        assert_eq!(state.update("screen-locked", false).unwrap().revision, 4);
        assert!(state.envelope().active_reasons.is_empty());
    }

    #[test]
    fn transparent_window_failure_uses_the_decorated_fallback() {
        let attempts = std::cell::RefCell::new(Vec::new());
        let (window, transparent) = build_with_transparent_fallback(
            false,
            || {
                attempts.borrow_mut().push("transparent");
                Err("transparent_failed")
            },
            |error| {
                assert_eq!(error, Some(&"transparent_failed"));
                attempts.borrow_mut().push("decorated");
                Ok("window")
            },
        )
        .unwrap();

        assert_eq!(window, "window");
        assert!(!transparent);
        assert_eq!(*attempts.borrow(), vec!["transparent", "decorated"]);
    }

    #[test]
    fn forced_decorated_window_skips_the_transparent_attempt() {
        let mut transparent_attempted = false;
        let (window, transparent) = build_with_transparent_fallback(
            true,
            || {
                transparent_attempted = true;
                Ok::<_, &str>("transparent")
            },
            |error| {
                assert!(error.is_none());
                Ok("decorated")
            },
        )
        .unwrap();

        assert_eq!(window, "decorated");
        assert!(!transparent);
        assert!(!transparent_attempted);
    }

    #[test]
    fn external_open_requires_the_current_observation_generation() {
        let runtime = RuntimeState {
            preferences: ShellPreferences::default(),
            observation_generation: 7,
            preferences_path: None,
            capabilities: ShellCapabilities::default(),
            window_position_revision: 0,
            window_persist_worker_running: false,
        };
        assert_eq!(
            current_origin_for_generation(&runtime, 7).unwrap(),
            "http://127.0.0.1:8787"
        );
        assert_eq!(
            current_origin_for_generation(&runtime, 6),
            Err("stale_observation_generation".into())
        );
    }

    #[test]
    fn restored_geometry_is_fully_clamped_inside_the_selected_work_area() {
        let area_position = PhysicalPosition::new(-3840, 134);
        let area_size = PhysicalSize::new(3840, 2160);
        let window_size = PhysicalSize::new(640, 1080);

        assert_eq!(
            clamp_position_to_work_area(
                PhysicalPosition::new(-50_000, 50_000),
                window_size,
                area_position,
                area_size,
            ),
            PhysicalPosition::new(-3840, 1214)
        );
        assert_eq!(
            clamp_position_to_work_area(
                PhysicalPosition::new(-3000, 400),
                window_size,
                area_position,
                area_size,
            ),
            PhysicalPosition::new(-3000, 400)
        );
    }

    #[test]
    fn snapshot_request_ids_are_opaque_and_bounded() {
        assert!(validate_request_id("89abcdef-0123-4567-89ab-cdef01234567").is_ok());
        for value in [
            "",
            "89abcdef-0123-4567-89ab-cdef0123456",
            "89abcdef-0123-4567-89ab-cdef0123456g",
            "89abcdef/0123/4567/89ab/cdef01234567",
        ] {
            assert_eq!(
                validate_request_id(value),
                Err("invalid_snapshot_request_id".into())
            );
        }
    }

    #[test]
    fn native_snapshot_control_handles_active_and_pre_start_cancellation() {
        let mut control = SnapshotRequestControl::default();
        let active_id = "89abcdef-0123-4567-89ab-cdef01234567";
        let cancellation = control.register(active_id).unwrap();
        control.cancel(active_id);
        assert!(cancellation.has_changed().unwrap());
        control.finish(active_id);

        let early_id = "01234567-89ab-cdef-0123-456789abcdef";
        control.cancel(early_id);
        assert_eq!(
            control.register(early_id).unwrap_err(),
            "snapshot_request_cancelled"
        );
        assert!(control.register(active_id).is_ok());
    }
}
