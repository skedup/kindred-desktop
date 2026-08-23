use crate::update_native_suspension;
use block2::RcBlock;
use objc2_app_kit::{
    NSApplicationDidUnhideNotification, NSApplicationWillHideNotification, NSWorkspace,
    NSWorkspaceDidWakeNotification, NSWorkspaceSessionDidBecomeActiveNotification,
    NSWorkspaceSessionDidResignActiveNotification, NSWorkspaceWillSleepNotification,
};
use objc2_core_foundation::{CFBoolean, CFDictionary, CFNumber, CFRetained, CFString, CFType};
use objc2_core_graphics::CGSessionCopyCurrentDictionary;
use objc2_foundation::{
    NSDistributedNotificationCenter, NSNotification, NSNotificationCenter, NSNotificationName,
    NSOperationQueue, NSString,
};
use std::ptr::NonNull;

pub fn register(app: tauri::AppHandle) {
    let main_queue = NSOperationQueue::mainQueue();
    let workspace_center = NSWorkspace::sharedWorkspace().notificationCenter();
    // SAFETY: these AppKit symbols are immutable process-lifetime notification-name constants.
    let (
        will_sleep,
        did_wake,
        session_resigned,
        session_became_active,
        application_will_hide,
        application_did_unhide,
    ) = unsafe {
        (
            NSWorkspaceWillSleepNotification,
            NSWorkspaceDidWakeNotification,
            NSWorkspaceSessionDidResignActiveNotification,
            NSWorkspaceSessionDidBecomeActiveNotification,
            NSApplicationWillHideNotification,
            NSApplicationDidUnhideNotification,
        )
    };
    observe(
        &workspace_center,
        will_sleep,
        &main_queue,
        app.clone(),
        "sleep",
        true,
    );
    observe(
        &workspace_center,
        did_wake,
        &main_queue,
        app.clone(),
        "sleep",
        false,
    );
    observe(
        &workspace_center,
        session_resigned,
        &main_queue,
        app.clone(),
        "session-inactive",
        true,
    );
    observe(
        &workspace_center,
        session_became_active,
        &main_queue,
        app.clone(),
        "session-inactive",
        false,
    );

    let application_center = NSNotificationCenter::defaultCenter();
    observe(
        &application_center,
        application_will_hide,
        &main_queue,
        app.clone(),
        "system-hidden",
        true,
    );
    observe(
        &application_center,
        application_did_unhide,
        &main_queue,
        app.clone(),
        "system-hidden",
        false,
    );

    let distributed = NSDistributedNotificationCenter::defaultCenter();
    let screen_locked = NSString::from_str("com.apple.screenIsLocked");
    let screen_unlocked = NSString::from_str("com.apple.screenIsUnlocked");
    observe(
        &distributed,
        &screen_locked,
        &main_queue,
        app.clone(),
        "screen-locked",
        true,
    );
    observe(
        &distributed,
        &screen_unlocked,
        &main_queue,
        app.clone(),
        "screen-locked",
        false,
    );

    let _ = refresh_current_state(&app);
}

pub(crate) fn refresh_current_state(app: &tauri::AppHandle) -> Result<(), &'static str> {
    let (locked, on_console) = current_session_state().ok_or("native_lifecycle_unavailable")?;
    update_native_suspension(app, "screen-locked", locked);
    update_native_suspension(app, "session-inactive", !on_console);
    Ok(())
}

fn current_session_state() -> Option<(bool, bool)> {
    let dictionary = CGSessionCopyCurrentDictionary()?;
    // SAFETY: CGSessionCopyCurrentDictionary returns a property-list dictionary whose keys are
    // CFString values and whose values are Core Foundation objects.
    let dictionary: CFRetained<CFDictionary<CFString, CFType>> =
        unsafe { CFRetained::cast_unchecked(dictionary) };
    let locked = session_flag(&dictionary, "CGSSessionScreenIsLocked")
        .ok()?
        .unwrap_or(false);
    let on_console = session_flag(&dictionary, "kCGSSessionOnConsoleKey").ok()??;
    Some((locked, on_console))
}

fn session_flag(
    dictionary: &CFDictionary<CFString, CFType>,
    key: &str,
) -> Result<Option<bool>, ()> {
    let Some(value) = dictionary.get(&CFString::from_str(key)) else {
        return Ok(None);
    };
    if let Some(boolean) = value.downcast_ref::<CFBoolean>() {
        return Ok(Some(boolean.as_bool()));
    }
    value
        .downcast_ref::<CFNumber>()
        .and_then(CFNumber::as_i32)
        .map(|number| number != 0)
        .map(Some)
        .ok_or(())
}

fn observe(
    center: &NSNotificationCenter,
    name: &NSNotificationName,
    queue: &NSOperationQueue,
    app: tauri::AppHandle,
    reason: &'static str,
    suspended: bool,
) {
    let callback = RcBlock::new(move |_: NonNull<NSNotification>| {
        update_native_suspension(&app, reason, suspended);
    });
    // SAFETY: the notification name and sender filter are valid Foundation objects; delivery is
    // pinned to the main queue and the copied block captures only a Send + Sync AppHandle.
    unsafe {
        center.addObserverForName_object_queue_usingBlock(Some(name), None, Some(queue), &callback);
    }
}
