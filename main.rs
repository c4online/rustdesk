
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use librustdesk::*;
use std::fs;
use std::path::PathBuf;
use hbb_common::log::{info, warn};
use toml_edit::{Document, Value};

/// 获取 RustDesk 配置文件路径
fn get_config_path() -> Option<PathBuf> {
    #[cfg(target_os = "windows")]
    {
        if let Some(app_data) = std::env::var_os("APPDATA") {
            return Some(PathBuf::from(app_data).join("RustDesk").join("RustDesk.toml"));
        }
    }
    #[cfg(target_os = "macos")]
    {
        if let Some(home) = std::env::var_os("HOME") {
            return Some(
                PathBuf::from(home)
                    .join("Library")
                    .join("Application Support")
                    .join("RustDesk")
                    .join("RustDesk.toml"),
            );
        }
    }
    #[cfg(target_os = "linux")]
    {
        if let Some(home) = std::env::var_os("HOME") {
            return Some(PathBuf::from(home).join(".config").join("rustdesk").join("RustDesk.toml"));
        }
    }
    None
}

/// 强制同步配置文件中的服务器设置
fn sync_config_settings() {
    // 【重要】请在此处替换为你的自建服务器信息
    let target_rendezvous = "r.3d98.com.cn:21116";
    let target_relay = "r.3d98.com.cn:21117";
    let target_key = "3yPOFgXbTyzUf0WbgBRsQ9TAmCDqd+nz0NhY8E6YcKw=";

    let config_path = match get_config_path() {
        Some(p) => p,
        None => return,
    };

    if !config_path.exists() {
        return;
    }

    let content = match fs::read_to_string(&config_path) {
        Ok(c) => c,
        Err(e) => {
            warn!("Failed to read config: {}", e);
            return;
        }
    };

    let mut doc: Document = match content.parse() {
        Ok(d) => d,
        Err(e) => {
            warn!("Failed to parse config: {}", e);
            return;
        }
    };

    let mut changed = false;

    // 辅助闭包：检查并更新字段
    let mut update_field = |key: &str, new_val: &str| {
        let current_val = doc.get(key).and_then(|v| v.as_str()).unwrap_or("");
        if current_val != new_val {
            doc[key] = Value::from(new_val);
            changed = true;
            info!("Config updated: {} = {}", key, new_val);
        }
    };

    update_field("rendezvous-server", target_rendezvous);
    update_field("relay-server", target_relay);
    update_field("key", target_key);

    if changed {
        if let Err(e) = fs::write(&config_path, doc.to_string()) {
            warn!("Failed to write config: {}", e);
        } else {
            info!("Configuration synchronized successfully.");
        }
    }
}

#[cfg(any(target_os = "android", target_os = "ios", feature = "flutter"))]
fn main() {
    if !common::global_init() {
        eprintln!("Global initialization failed.");
        return;
    }
    common::test_rendezvous_server();
    common::test_nat_type();
    common::global_clean();
}

#[cfg(not(any(
    target_os = "android",
    target_os = "ios",
    feature = "flutter"
)))]
fn main() {
    #[cfg(all(windows, not(feature = "inline")))]
    unsafe {
        winapi::um::shellscalingapi::SetProcessDpiAwareness(2);
    }

    // 在核心逻辑启动前同步配置，确保使用最新的服务器设置
    sync_config_settings();

    if let Some(args) = crate::core_main::core_main().as_mut() {
        ui::start(args);
    }
    common::global_clean();
}
