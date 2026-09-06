use std::fs;

use serde::{Deserialize, Serialize};
use tauri::menu::{Menu, MenuItem};
use tauri::{Manager, Url, WebviewWindow};

#[derive(Serialize, Deserialize, Default)]
struct Config {
    server_url: Option<String>,
}

/// The bundled setup page's URL under Tauri's local-asset custom protocol.
/// WebView2 (Windows/Android) requires an http(s) scheme for that protocol;
/// WebKit/WKWebView (macOS/Linux/iOS) use a `tauri://` scheme instead.
/// Hardcoded (rather than captured from `window.url()` at startup) because
/// that capture races the webview's own initial navigation and can return a
/// placeholder like `about:blank`, leaving "change server" stuck on a blank page.
fn local_setup_url() -> Url {
    let raw = if cfg!(any(windows, target_os = "android")) {
        "http://tauri.localhost/index.html"
    } else {
        "tauri://localhost/index.html"
    };
    Url::parse(raw).expect("static local setup URL is valid")
}

fn config_path(app: &tauri::AppHandle) -> tauri::Result<std::path::PathBuf> {
    let dir = app.path().app_config_dir()?;
    fs::create_dir_all(&dir)?;
    Ok(dir.join("config.json"))
}

fn read_config(app: &tauri::AppHandle) -> Config {
    config_path(app)
        .ok()
        .and_then(|p| fs::read_to_string(p).ok())
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn write_config(app: &tauri::AppHandle, cfg: &Config) -> Result<(), String> {
    let path = config_path(app).map_err(|e| e.to_string())?;
    let body = serde_json::to_string_pretty(cfg).map_err(|e| e.to_string())?;
    fs::write(path, body).map_err(|e| e.to_string())
}

#[tauri::command]
fn get_server_url(app: tauri::AppHandle) -> Option<String> {
    read_config(&app).server_url
}

fn validate_server_url(url: &str) -> Result<Url, String> {
    let trimmed = url.trim();
    let parsed = Url::parse(trimmed).map_err(|_| "Server URL không hợp lệ".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("Server URL phải bắt đầu bằng http:// hoặc https://".to_string());
    }
    Ok(parsed)
}

#[tauri::command]
fn save_server_url(app: tauri::AppHandle, window: WebviewWindow, url: String) -> Result<(), String> {
    let parsed = validate_server_url(&url)?;
    write_config(&app, &Config { server_url: Some(parsed.to_string()) })?;
    window.navigate(parsed).map_err(|e| e.to_string())
}

#[cfg(test)]
mod tests {
    use super::validate_server_url;

    #[test]
    fn accepts_http_and_https() {
        assert!(validate_server_url("https://app.example.com").is_ok());
        assert!(validate_server_url("  http://localhost:3000  ").is_ok());
    }

    #[test]
    fn rejects_non_http_schemes_and_garbage() {
        assert!(validate_server_url("ftp://example.com").is_err());
        assert!(validate_server_url("not a url").is_err());
        assert!(validate_server_url("").is_err());
    }
}

fn reset_server(app: &tauri::AppHandle, window: &WebviewWindow) {
    let _ = write_config(app, &Config::default());
    let _ = window.navigate(local_setup_url());
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![get_server_url, save_server_url])
        .setup(|app| {
            let window = app.get_webview_window("main").expect("main window missing");

            let change_server = MenuItem::with_id(app, "change-server", "Đổi Server URL...", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&change_server])?;
            app.set_menu(menu)?;

            let cfg = read_config(app.handle());
            if let Some(server_url) = cfg.server_url {
                if let Ok(parsed) = Url::parse(&server_url) {
                    window.navigate(parsed)?;
                }
            }
            Ok(())
        })
        .on_menu_event(|app, event| {
            if event.id() == "change-server" {
                if let Some(window) = app.get_webview_window("main") {
                    reset_server(app, &window);
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
