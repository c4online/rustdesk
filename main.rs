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
    // 【建议】通过环境变量获取敏感信息，避免硬编码
    let target_rendezvous = std::env::var("RD_RENDEZVOUS_SERVER").unwrap_or_else(|_| "r.3d98.com.cn:21116".to_string());
    let target_relay = std::env::var("RD_RELAY_SERVER").unwrap_or_else(|_| "r.3d98.com.cn:21117".to_string());
    let target_key = std::env::var("RD_KEY").unwrap_or_else(|_| "3yPOFgXbTyzUf0WbgBRsQ9TAmCDqd+nz0NhY8E6YcKw=".to_string());

    let config_path = match get_config_path() {
        Some(p) => p,
        None => {
            warn!("Could not determine config path.");
            return;
        }
    };

    if !config_path.exists() {
        info!("Config file does not exist, skipping sync.");
        return;
    }

    // 增加重试逻辑，最多尝试3次
    for attempt in 1..=3 {
        match sync_config_inner(&config_path, &target_rendezvous, &target_relay, &target_key) {
            Ok(_) => return,
            Err(e) => {
                warn!("Attempt {} failed to sync config: {}. Retrying...", attempt, e);
                if attempt < 3 {
                    std::thread::sleep(std::time::Duration::from_millis(500));
                }
            }
        }
    }
}

fn sync_config_inner(
    config_path: &PathBuf, 
    rendezvous: &str, 
    relay: &str, 
    key: &str
) -> Result<(), String> {
    let content = fs::read_to_string(config_path)
        .map_err(|e| format!("Read error: {}", e))?;

    let mut doc: Document = content.parse()
        .map_err(|e| format!("Parse error: {}", e))?;

    let mut changed = false;

    // 注意：请根据实际 RustDesk 版本的 config.rs 确认以下键名是否正确
    // 常见键名可能是 "custom-rendezvous-server", "relay-server", "key" 等
    let mut update_field = |key: &str, new_val: &str| {
        // 检查字段是否存在且值不同
        let need_update = match doc.get(key) {
            Some(v) => v.as_str() != Some(new_val),
            None => true, // 字段不存在，需要创建
        };

        if need_update {
            doc[key] = Value::from(new_val);
            changed = true;
            info!("Config updated: {} = {}", key, new_val);
        }
    };

    // 请再次确认这些键名是否与你的 RustDesk 版本匹配
    update_field("rendezvous-server", rendezvous);
    update_field("relay-server", relay);
    update_field("key", key);

    if changed {
        fs::write(config_path, doc.to_string())
            .map_err(|e| format!("Write error: {}", e))?;
        info!("Configuration synchronized successfully.");
    } else {
        info!("Configuration is already up to date.");
    }
    
    Ok(())
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

    // 在核心逻辑启动前同步配置
    sync_config_settings();

    if let Some(args) = crate::core_main::core_main().as_mut() {
        ui::start(args);
    }
    common::global_clean();
}
