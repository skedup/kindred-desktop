use serde_json::Value;

const CAPABILITY: &str = include_str!("../capabilities/desktop.json");
const CONFIG: &str = include_str!("../tauri.conf.json");
const HOST: &str = include_str!("../src/lib.rs");
const PREFERENCES: &str = include_str!("../src/preferences.rs");
const TRANSPORT: &str = include_str!("../src/transport.rs");

#[test]
fn capability_set_is_minimal_and_has_no_network_or_pointer_passthrough() {
    let capability: Value = serde_json::from_str(CAPABILITY).unwrap();
    assert_eq!(
        capability["permissions"],
        serde_json::json!([
            "core:event:allow-listen",
            "core:event:allow-unlisten",
            "core:window:allow-start-dragging"
        ])
    );
    for forbidden in ["http", "shell", "opener", "ignore-cursor", "always-on-top"] {
        assert!(!CAPABILITY.to_ascii_lowercase().contains(forbidden));
    }
}

#[test]
fn packaged_host_has_no_remote_window_or_generic_request_surface() {
    let config: Value = serde_json::from_str(CONFIG).unwrap();
    assert_eq!(config["app"]["windows"], serde_json::json!([]));
    assert!(config["app"]["security"]["csp"]
        .as_str()
        .unwrap()
        .contains("object-src 'none'"));
    assert!(!HOST.contains("set_ignore_cursor_events"));
    assert!(HOST.contains("set_always_on_top"));
    assert!(PREFERENCES.contains("always_on_top: true"));
    assert!(!HOST.contains("tauri_plugin_http"));
    assert!(!HOST.contains("tauri_plugin_shell"));
    assert!(!HOST.contains("control_heart"));
    assert!(!HOST.contains("control_web"));
}

#[test]
fn bridge_transport_has_one_fixed_visual_endpoint_and_only_an_opaque_request_token() {
    let production = TRANSPORT.split("#[cfg(test)]").next().unwrap();
    assert!(production.contains(".get(url)"));
    assert!(!production.contains("authorization"));
    assert!(!production.contains("cookie"));
    assert!(!production.contains("pub async fn request"));
    assert!(HOST.contains("async fn fetch_visual_snapshot(\n    state:"));
    assert!(HOST.contains("request_id: String"));
    assert!(!HOST.contains("request_url:"));
    assert!(!HOST.contains("request_headers:"));
}
