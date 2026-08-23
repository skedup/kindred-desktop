use crate::origin::{is_loopback, validate_origin};
use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
};

pub const PREFERENCES_FILE: &str = "desktop-spirit.json";

const fn default_always_on_top() -> bool {
    true
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SourceKind {
    Local,
    Remote,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SourceProfile {
    pub label: String,
    pub base_url: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WindowGeometry {
    pub x: i32,
    pub y: i32,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ShellPreferences {
    pub schema_version: u8,
    #[serde(default = "default_always_on_top")]
    pub always_on_top: bool,
    pub active_source: SourceKind,
    pub local: SourceProfile,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub remote: Option<SourceProfile>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub window: Option<WindowGeometry>,
}

impl Default for ShellPreferences {
    fn default() -> Self {
        Self {
            schema_version: 1,
            always_on_top: true,
            active_source: SourceKind::Local,
            local: SourceProfile {
                label: "Local".into(),
                base_url: "http://127.0.0.1:8787".into(),
            },
            remote: None,
            window: None,
        }
    }
}

impl ShellPreferences {
    pub fn validate(mut self) -> Result<Self, &'static str> {
        if self.schema_version != 1 {
            return Err("invalid_preferences_schema");
        }
        self.local = validate_profile(self.local)?;
        if !is_loopback(&self.local.base_url) {
            return Err("local_origin_must_be_loopback");
        }
        self.remote = self.remote.map(validate_profile).transpose()?;
        if self.active_source == SourceKind::Remote && self.remote.is_none() {
            return Err("remote_origin_required");
        }
        Ok(self)
    }

    pub fn active_profile(&self) -> &SourceProfile {
        match self.active_source {
            SourceKind::Local => &self.local,
            SourceKind::Remote => self.remote.as_ref().expect("validated remote profile"),
        }
    }

    pub fn observation_source_equal(&self, other: &Self) -> bool {
        self.active_source == other.active_source
            && self.active_profile().base_url == other.active_profile().base_url
    }
}

fn validate_profile(mut profile: SourceProfile) -> Result<SourceProfile, &'static str> {
    if profile.label.is_empty()
        || profile.label.len() > 80
        || profile.label.chars().any(char::is_control)
    {
        return Err("invalid_source_label");
    }
    profile.base_url = validate_origin(&profile.base_url)?;
    Ok(profile)
}

pub fn load(path: &Path) -> ShellPreferences {
    let Ok(bytes) = fs::read(path) else {
        return ShellPreferences::default();
    };
    serde_json::from_slice::<ShellPreferences>(&bytes)
        .ok()
        .and_then(|value| value.validate().ok())
        .unwrap_or_default()
}

pub fn save_atomic(path: &Path, preferences: &ShellPreferences) -> Result<(), String> {
    let parent = path
        .parent()
        .ok_or_else(|| "preferences_path_invalid".to_owned())?;
    fs::create_dir_all(parent).map_err(|_| "preferences_directory_failed".to_owned())?;
    let temp_path = temporary_path(path);
    let bytes = serde_json::to_vec_pretty(preferences)
        .map_err(|_| "preferences_serialize_failed".to_owned())?;
    let result = (|| {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temp_path)
            .map_err(|_| "preferences_write_failed".to_owned())?;
        file.write_all(&bytes)
            .and_then(|_| file.write_all(b"\n"))
            .and_then(|_| file.sync_all())
            .map_err(|_| "preferences_write_failed".to_owned())?;
        fs::rename(&temp_path, path).map_err(|_| "preferences_commit_failed".to_owned())
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    result
}

fn temporary_path(path: &Path) -> PathBuf {
    let mut name = path
        .file_name()
        .map(|value| value.to_os_string())
        .unwrap_or_else(|| PREFERENCES_FILE.into());
    name.push(format!(".{}.tmp", std::process::id()));
    path.with_file_name(name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn defaults_to_the_fixed_local_service() {
        let value = ShellPreferences::default();
        assert_eq!(value.active_source, SourceKind::Local);
        assert_eq!(value.active_profile().base_url, "http://127.0.0.1:8787");
        assert!(value.always_on_top);
        assert!(value.remote.is_none());
    }

    #[test]
    fn existing_preferences_without_window_level_default_to_always_on_top() {
        let value: ShellPreferences = serde_json::from_value(serde_json::json!({
            "schema_version": 1,
            "active_source": "local",
            "local": {
                "label": "Local",
                "base_url": "http://127.0.0.1:8787"
            }
        }))
        .unwrap();

        assert!(value.always_on_top);
    }

    #[test]
    fn requires_remote_configuration_before_selection() {
        let value = ShellPreferences {
            active_source: SourceKind::Remote,
            ..ShellPreferences::default()
        };
        assert_eq!(value.validate(), Err("remote_origin_required"));
    }

    #[test]
    fn local_profile_cannot_become_a_lan_or_wildcard_origin() {
        for origin in ["http://192.0.2.2:8787", "http://0.0.0.0:8787"] {
            let mut value = ShellPreferences::default();
            value.local.base_url = origin.into();
            assert!(value.validate().is_err(), "{origin}");
        }
    }

    #[test]
    fn only_active_origin_or_selection_changes_the_observation_source() {
        let baseline = ShellPreferences::default();
        let mut renamed = baseline.clone();
        renamed.local.label = "This Mac".into();
        assert!(baseline.observation_source_equal(&renamed));

        let mut changed_window_level = baseline.clone();
        changed_window_level.always_on_top = false;
        assert!(baseline.observation_source_equal(&changed_window_level));

        let mut inactive_remote = baseline.clone();
        inactive_remote.remote = Some(SourceProfile {
            label: "Ubuntu".into(),
            base_url: "https://kindred.example".into(),
        });
        assert!(baseline.observation_source_equal(&inactive_remote));

        let mut changed_local = baseline.clone();
        changed_local.local.base_url = "http://localhost:8787".into();
        assert!(!baseline.observation_source_equal(&changed_local));

        let selected_remote = inactive_remote.clone().validate().unwrap();
        let mut selected_remote = selected_remote;
        selected_remote.active_source = SourceKind::Remote;
        assert!(!baseline.observation_source_equal(&selected_remote));
    }
}
