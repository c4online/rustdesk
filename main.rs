
#![cfg_attr(
    all(not(debug_assertions), target_os = "windows"),
    windows_subsystem = "windows"
)]

use librustdesk::*;
use std::fs;
use std::path::PathBuf;
use std::net::SocketAddr;
use hbb_common::log::{info, warn, error};
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

/// 标准化地址格式，确保 IPv6 地址被正确包裹在 [] 中
/// 输入: "2001:db8::1", 21116 -> "[2001:db8::1]:21116"
/// 输入: "192.168.1.1", 21116 -> "192.168.1.1:21116"
/// 输入: "example.com", 21116 -> "example.com:21116"
fn normalize_address(host: &str, port: u16) -> String {
    // 尝试构造一个标准的 SocketAddr 字符串
    let addr_str = format!("{}:{}", host, port);
    
    // 尝试解析为 SocketAddr
    if let Ok(_addr) = addr_str.parse::<SocketAddr>() {
        // 如果解析成功，说明格式已经是标准的（IPv4或带括号的IPv6）
        // 但 parse::<SocketAddr> 对域名不支持，所以这里主要处理 IP
        return addr_str;
    }

    // 如果解析失败，可能是域名或者裸 IPv6
    // 检查是否是 IPv6 (包含冒号且不以 [ 开头)
    if host.contains(':') && !host.starts_with('[') {
        // 假设是裸 IPv6，添加括号
        return format!("[{}]:{}", host, port);
    }
    
    // 其他情况（域名或已格式化好的地址），直接返回
    addr_str
}

/// 强制同步配置文件中的服务器设置
fn sync_config_settings() {
    // 【建议】通过环境变量获取敏感信息，避免硬编码
    // 默认值仅作为 fallback
    let raw_rendezvous = std::env::var("RD_RENDEZVOUS_SERVER").unwrap_or_else(|_| "r.3d98.com.cn".to_string());
    let raw_relay = std::env::var("RD_RELAY_SERVER").unwrap_or_else(|_| "r.3d98.com.cn".to_string());
    let target_key = std::env::var("RD_KEY").unwrap_or_else(|_| "3yPOFgXbTyzUf0WbgBRsQ9TAmCDqd+nz0NhY8E6YcKw=".to_string());

    // 解析端口，如果环境变量中包含端口则提取，否则使用默认端口
    // 这里简化处理，假设环境变量只传 Host，端口固定或从另一变量传
    // 为了兼容性，我们允许环境变量传入 "host:port" 格式，也支持单独传入
    let (rendezvous_host, rendezvous_port) = parse_host_port(&raw_rendezvous, 21116);
    let (relay_host, relay_port) = parse_host_port(&raw_relay, 21117);

    let target_rendezvous = normalize_address(&rendezvous_host, rendezvous_port);
    let target_relay = normalize_address(&relay_host, relay_port);

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

/// 辅助函数：从字符串中解析 host 和 port
/// 如果输入包含 ":"，则分割；否则使用默认端口
fn parse_host_port(input: &str, default_port: u16) -> (String, u16) {
    if let Some(idx) = input.rfind(':') {
        // 检查是否是 IPv6 的括号格式 [::1]:port
        if input.starts_with('[') {
            if let Some(end_bracket) = input.find(']') {
                if end_bracket < idx {
                    let host = input[..idx].to_string(); // 包含 []
                    let port_str = &input[idx+1..];
                    if let Ok(port) = port_str.parse::<u16>() {
                        return (host, port);
                    }
                }
            }
        } else {
            // 普通 host:port
            let host = &input[..idx];
            let port_str = &input[idx+1..];
            if let Ok(port) = port_str.parse::<u16>() {
                return (host.to_string(), port);
            }
        }
    }
    (input.to_string(), default_port)
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

    // 辅助闭包：检查并更新字段
    let mut update_field = |key: &str, new_val: &str| {
        let current_val = doc.get(key).and_then(|v| v.as_str()).unwrap_or("");
        if current_val != new_val {
            doc[key] = Value::from(new_val);
            changed = true;
            info!("Config updated: {} = {}", key, new_val);
        }
    };

    // 注意：键名需与 RustDesk 实际配置结构匹配
    // 常见键名: "rendezvous-server", "relay-server", "key", "custom-rendezvous-server"
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
