#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use keyring::Entry;
use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use std::env;
use std::fs;
use std::io::ErrorKind;
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Manager, RunEvent, State};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

const CREDENTIAL_SERVICE: &str = "com.wishforge.research";
const CREDENTIAL_SLOTS: &[(&str, &str)] = &[
    ("paper_search", "WISHFORGE_PAPER_API_KEY"),
    ("community_search", "WISHFORGE_COMMUNITY_API_KEY"),
    ("explanation_model", "WISHFORGE_EXPLANATION_API_KEY"),
    ("experiment_runner", "WISHFORGE_EXPERIMENT_API_KEY"),
];

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
#[serde(default)]
struct PersistedRuntimeSettings {
    paper_provider: Option<String>,
    paper_base_url: Option<String>,
    paper_model: Option<String>,
    paper_enabled: Option<bool>,
    community_provider: Option<String>,
    community_base_url: Option<String>,
    community_model: Option<String>,
    community_enabled: Option<bool>,
    explanation_provider: Option<String>,
    explanation_model: Option<String>,
    explanation_base_url: Option<String>,
    explanation_enabled: Option<bool>,
    experiment_provider: Option<String>,
    experiment_base_url: Option<String>,
    experiment_model: Option<String>,
    experiment_enabled: Option<bool>,
    demo_mode: Option<bool>,
}

#[derive(Debug, Clone, Serialize)]
struct DesktopRuntimeConfig {
    desktop: bool,
    version: String,
    api_base_url: String,
    data_dir: String,
    explanation_provider: Option<String>,
    explanation_model: Option<String>,
    explanation_base_url: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
struct CredentialStatus {
    slot: String,
    configured: bool,
    masked: Option<String>,
}

struct AppState {
    sidecar: Mutex<Option<Child>>,
    config: Mutex<DesktopRuntimeConfig>,
    data_dir: Mutex<Option<PathBuf>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            sidecar: Mutex::new(None),
            config: Mutex::new(DesktopRuntimeConfig {
                desktop: true,
                version: env!("CARGO_PKG_VERSION").to_string(),
                api_base_url: String::new(),
                data_dir: String::new(),
                explanation_provider: None,
                explanation_model: None,
                explanation_base_url: None,
            }),
            data_dir: Mutex::new(None),
        }
    }
}

fn config_path(data_dir: &Path) -> PathBuf {
    data_dir.join("runtime-settings.json")
}

fn load_runtime_settings(data_dir: &Path) -> PersistedRuntimeSettings {
    match fs::read_to_string(config_path(data_dir)) {
        Ok(text) => serde_json::from_str(&text).unwrap_or_default(),
        Err(error) if error.kind() == ErrorKind::NotFound => PersistedRuntimeSettings::default(),
        Err(_) => PersistedRuntimeSettings::default(),
    }
}

fn persist_runtime_settings(
    data_dir: &Path,
    settings: &PersistedRuntimeSettings,
) -> Result<(), String> {
    fs::create_dir_all(data_dir).map_err(|error| format!("创建应用数据目录失败：{error}"))?;
    let path = config_path(data_dir);
    let temp = path.with_extension("json.tmp");
    let body = serde_json::to_vec_pretty(settings)
        .map_err(|error| format!("编码运行时设置失败：{error}"))?;
    fs::write(&temp, body).map_err(|error| format!("写入运行时设置失败：{error}"))?;
    fs::rename(&temp, &path).map_err(|error| format!("提交运行时设置失败：{error}"))
}

fn validate_slot(slot: &str) -> Result<&'static str, String> {
    CREDENTIAL_SLOTS
        .iter()
        .find(|(known, _)| *known == slot)
        .map(|(_, variable)| *variable)
        .ok_or_else(|| "未知的凭据用途".to_string())
}

fn credential_entry(slot: &str) -> Result<Entry, String> {
    Entry::new(CREDENTIAL_SERVICE, slot).map_err(|error| format!("创建凭据项失败：{error}"))
}

fn read_credential(slot: &str) -> Option<String> {
    credential_entry(slot)
        .ok()
        .and_then(|entry| entry.get_password().ok())
}

fn credential_mask(secret: &str) -> String {
    if secret.chars().count() <= 4 {
        return "••••".to_string();
    }
    let tail: String = secret
        .chars()
        .rev()
        .take(4)
        .collect::<String>()
        .chars()
        .rev()
        .collect();
    format!("••••••••{tail}")
}

fn next_loopback_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("分配本地端口失败：{error}"))?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| format!("读取本地端口失败：{error}"))
}

fn sidecar_binary_name() -> String {
    // Phase 4 currently ships a Windows MSVC bundle.  `TARGET` is available
    // to build scripts but is not guaranteed to be defined for the Rust
    // crate itself, so keep the runtime name explicit and deterministic.
    "wishforge-sidecar-x86_64-pc-windows-msvc".to_string()
}

fn sidecar_command(
    app: &AppHandle,
    port: u16,
    data_dir: &Path,
    settings_path: &Path,
) -> Result<Command, String> {
    let repo_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .ok_or_else(|| "无法定位仓库目录".to_string())?
        .to_path_buf();
    let mut command = if let Some(custom) = env::var_os("WISHFORGE_SIDECAR_PATH") {
        Command::new(custom)
    } else if cfg!(debug_assertions) {
        let python = env::var_os("WISHFORGE_PYTHON").unwrap_or_else(|| "python".into());
        let mut value = Command::new(python);
        value
            .current_dir(&repo_root)
            .arg(repo_root.join("backend").join("sidecar.py"));
        value
    } else {
        let resource_dir = app
            .path()
            .resource_dir()
            .map_err(|error| format!("读取应用资源目录失败：{error}"))?;
        let target_name = format!("{}.exe", sidecar_binary_name());
        let mut candidates = vec![
            resource_dir.join("bin").join(&target_name),
            resource_dir.join(&target_name),
            resource_dir.join("bin").join("wishforge-sidecar.exe"),
            // Tauri's NSIS externalBin bundle places this executable beside
            // the main application and removes the target-triple suffix.
            resource_dir.join("wishforge-sidecar.exe"),
        ];
        if let Ok(executable) = env::current_exe() {
            if let Some(executable_dir) = executable.parent() {
                candidates.push(executable_dir.join(&target_name));
                candidates.push(executable_dir.join("wishforge-sidecar.exe"));
            }
        }
        let binary = candidates
            .iter()
            .find(|path| path.exists())
            .ok_or_else(|| {
                "找不到 WishForge Python sidecar；安装包可能不完整，请重新安装。".to_string()
            })?;
        Command::new(binary)
    };

    command
        .arg("--port")
        .arg(port.to_string())
        .arg("--data-dir")
        .arg(data_dir)
        .arg("--config")
        .arg(settings_path)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    command.env("WISHFORGE_APP_DATA_DIR", data_dir);
    command.env("WISHFORGE_DESKTOP_SIDECAR", "1");
    for (slot, variable) in CREDENTIAL_SLOTS {
        if let Some(secret) = read_credential(slot) {
            command.env(variable, secret);
        }
    }
    Ok(command)
}

fn wait_for_health(base_url: &str) -> Result<(), String> {
    let client = Client::builder()
        .timeout(Duration::from_millis(700))
        .build()
        .map_err(|error| format!("创建 sidecar 健康检查客户端失败：{error}"))?;
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if let Ok(response) = client.get(format!("{base_url}/api/v1/health")).send() {
            if response.status().is_success() {
                return Ok(());
            }
        }
        thread::sleep(Duration::from_millis(150));
    }
    Err("本地 FastAPI sidecar 在 30 秒内没有通过健康检查".to_string())
}

fn terminate_sidecar(child: &mut Child) {
    #[cfg(target_os = "windows")]
    {
        const CREATE_NO_WINDOW: u32 = 0x08000000;
        let status = Command::new("taskkill")
            .args(["/PID", &child.id().to_string(), "/T", "/F"])
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .creation_flags(CREATE_NO_WINDOW)
            .status();
        if !status.is_ok_and(|value| value.success()) {
            let _ = child.kill();
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = child.kill();
    }
    let _ = child.wait();
}

fn start_sidecar(app: &AppHandle, state: &AppState) -> Result<(), String> {
    let data_dir = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("读取应用数据目录失败：{error}"))?;
    fs::create_dir_all(&data_dir).map_err(|error| format!("创建应用数据目录失败：{error}"))?;
    let settings = load_runtime_settings(&data_dir);
    let settings_path = config_path(&data_dir);
    let port = next_loopback_port()?;
    let base_url = format!("http://127.0.0.1:{port}");
    let mut command = sidecar_command(app, port, &data_dir, &settings_path)?;
    command.envs([
        (
            "WISHFORGE_EXPLANATION_PROVIDER",
            settings
                .explanation_provider
                .clone()
                .unwrap_or_else(|| "openai".to_string()),
        ),
        (
            "WISHFORGE_EXPLANATION_MODEL",
            settings
                .explanation_model
                .clone()
                .unwrap_or_else(|| "gpt-4.1-mini".to_string()),
        ),
        (
            "WISHFORGE_EXPLANATION_BASE_URL",
            settings
                .explanation_base_url
                .clone()
                .unwrap_or_else(|| "https://api.openai.com/v1".to_string()),
        ),
    ]);
    let child = command
        .spawn()
        .map_err(|error| format!("启动 WishForge sidecar 失败：{error}"))?;
    if let Err(error) = wait_for_health(&base_url) {
        let mut child = child;
        terminate_sidecar(&mut child);
        return Err(error);
    }
    *state
        .sidecar
        .lock()
        .map_err(|_| "sidecar 状态锁不可用".to_string())? = Some(child);
    *state
        .data_dir
        .lock()
        .map_err(|_| "应用数据目录状态锁不可用".to_string())? = Some(data_dir.clone());
    let mut runtime = state
        .config
        .lock()
        .map_err(|_| "运行时配置锁不可用".to_string())?;
    runtime.api_base_url = base_url;
    runtime.version = app.package_info().version.to_string();
    runtime.data_dir = data_dir.to_string_lossy().to_string();
    runtime.explanation_provider = settings.explanation_provider;
    runtime.explanation_model = settings.explanation_model;
    runtime.explanation_base_url = settings.explanation_base_url;
    Ok(())
}

impl AppState {
    fn stop(&self) {
        if let Ok(mut slot) = self.sidecar.lock() {
            if let Some(mut child) = slot.take() {
                terminate_sidecar(&mut child);
            }
        }
    }
}

#[tauri::command]
fn get_runtime_config(state: State<'_, AppState>) -> Result<DesktopRuntimeConfig, String> {
    state
        .config
        .lock()
        .map(|value| value.clone())
        .map_err(|_| "读取桌面运行时配置失败".to_string())
}

#[tauri::command]
fn set_credential(slot: String, value: String) -> Result<CredentialStatus, String> {
    validate_slot(&slot)?;
    let entry = credential_entry(&slot)?;
    if value.trim().is_empty() {
        match entry.delete_credential() {
            Ok(()) => {}
            Err(error) if error.to_string().to_lowercase().contains("no entry") => {}
            Err(error) => return Err(format!("清除凭据失败：{error}")),
        }
        return Ok(CredentialStatus {
            slot,
            configured: false,
            masked: None,
        });
    }
    entry
        .set_password(&value)
        .map_err(|error| format!("保存凭据失败：{error}"))?;
    Ok(CredentialStatus {
        slot,
        configured: true,
        masked: Some(credential_mask(&value)),
    })
}

#[tauri::command]
fn get_credential_status(slot: String) -> Result<CredentialStatus, String> {
    validate_slot(&slot)?;
    let value = read_credential(&slot);
    Ok(CredentialStatus {
        slot,
        configured: value.is_some(),
        masked: value.as_deref().map(credential_mask),
    })
}

#[tauri::command]
fn save_desktop_runtime_settings(
    provider: String,
    model: String,
    base_url: String,
    demo_mode: Option<bool>,
    state: State<'_, AppState>,
) -> Result<DesktopRuntimeConfig, String> {
    let parsed = base_url
        .parse::<url::Url>()
        .map_err(|_| "Base URL 必须是完整 URL".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https")
        || parsed.host_str().is_none()
        || parsed.query().is_some()
        || parsed.fragment().is_some()
    {
        return Err(
            "Base URL 必须是完整的 http:// 或 https:// 地址，且不能包含 query 或 fragment"
                .to_string(),
        );
    }
    let data_dir = state
        .data_dir
        .lock()
        .map_err(|_| "应用数据目录状态锁不可用".to_string())?
        .clone()
        .ok_or_else(|| "sidecar 尚未启动".to_string())?;
    let mut persisted = load_runtime_settings(&data_dir);
    persisted.explanation_provider = Some(provider.clone());
    persisted.explanation_model = Some(model.clone());
    persisted.explanation_base_url = Some(base_url.clone());
    if demo_mode.is_some() {
        persisted.demo_mode = demo_mode;
    }
    persist_runtime_settings(&data_dir, &persisted)?;
    let mut config = state
        .config
        .lock()
        .map_err(|_| "运行时配置锁不可用".to_string())?;
    config.explanation_provider = Some(provider);
    config.explanation_model = Some(model);
    config.explanation_base_url = Some(base_url);
    Ok(config.clone())
}

#[tauri::command]
fn save_desktop_provider_settings(
    slot: String,
    provider: String,
    model: Option<String>,
    base_url: Option<String>,
    enabled: bool,
    state: State<'_, AppState>,
) -> Result<DesktopRuntimeConfig, String> {
    let provider = provider.trim().to_string();
    if provider.is_empty() {
        return Err("Provider 不能为空".to_string());
    }
    let base_url = base_url
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    if let Some(value) = base_url.as_deref() {
        let parsed = value
            .parse::<url::Url>()
            .map_err(|_| "Base URL 必须是完整 URL".to_string())?;
        if !matches!(parsed.scheme(), "http" | "https")
            || parsed.host_str().is_none()
            || parsed.query().is_some()
            || parsed.fragment().is_some()
        {
            return Err(
                "Base URL 必须是完整的 http:// 或 https:// 地址，且不能包含 query 或 fragment"
                    .to_string(),
            );
        }
    }
    let model = model
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty());
    let data_dir = state
        .data_dir
        .lock()
        .map_err(|_| "应用数据目录状态锁不可用".to_string())?
        .clone()
        .ok_or_else(|| "sidecar 尚未启动".to_string())?;
    let mut persisted = load_runtime_settings(&data_dir);
    match slot.as_str() {
        "paper_search" => {
            persisted.paper_provider = Some(provider.clone());
            persisted.paper_base_url = base_url.clone();
            persisted.paper_model = model.clone();
            persisted.paper_enabled = Some(enabled);
        }
        "community_search" => {
            persisted.community_provider = Some(provider.clone());
            persisted.community_base_url = base_url.clone();
            persisted.community_model = model.clone();
            persisted.community_enabled = Some(enabled);
        }
        "explanation_model" => {
            persisted.explanation_provider = Some(provider.clone());
            persisted.explanation_base_url = base_url.clone();
            persisted.explanation_model = model.clone();
            persisted.explanation_enabled = Some(enabled);
        }
        "experiment_runner" => {
            persisted.experiment_provider = Some(provider.clone());
            persisted.experiment_base_url = base_url.clone();
            persisted.experiment_model = model.clone();
            persisted.experiment_enabled = Some(enabled);
        }
        _ => return Err("未知的 Provider 用途".to_string()),
    }
    persist_runtime_settings(&data_dir, &persisted)?;
    let mut config = state
        .config
        .lock()
        .map_err(|_| "运行时配置锁不可用".to_string())?;
    if slot == "explanation_model" {
        config.explanation_provider = Some(provider);
        config.explanation_model = model;
        config.explanation_base_url = base_url;
    }
    Ok(config.clone())
}

#[cfg(target_os = "windows")]
#[link(name = "user32")]
unsafe extern "system" {
    fn MessageBoxW(
        window: *mut core::ffi::c_void,
        text: *const u16,
        caption: *const u16,
        style: u32,
    ) -> i32;
}

#[cfg(target_os = "windows")]
fn report_startup_failure(error: &impl std::fmt::Display) {
    let log_dir = env::var_os("LOCALAPPDATA")
        .map(PathBuf::from)
        .unwrap_or_else(env::temp_dir)
        .join("WishForge");
    let log_path = log_dir.join("startup-error.log");
    let _ = fs::create_dir_all(&log_dir);
    let _ = fs::write(
        &log_path,
        format!("WishForge failed to start.\n\n{error}\n"),
    );
    let message = format!(
        "WishForge failed to start.\n\n{error}\n\nDetails were saved to:\n{}",
        log_path.display()
    );
    let mut wide_message: Vec<u16> = message.encode_utf16().collect();
    wide_message.push(0);
    let mut wide_caption: Vec<u16> = "WishForge startup error".encode_utf16().collect();
    wide_caption.push(0);
    // MB_ICONERROR
    unsafe {
        MessageBoxW(
            std::ptr::null_mut(),
            wide_message.as_ptr(),
            wide_caption.as_ptr(),
            0x0000_0010,
        );
    }
}

#[cfg(not(target_os = "windows"))]
fn report_startup_failure(error: &impl std::fmt::Display) {
    eprintln!("WishForge failed to start: {error}");
}

fn main() {
    let app = tauri::Builder::default()
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            get_runtime_config,
            set_credential,
            get_credential_status,
            save_desktop_runtime_settings,
            save_desktop_provider_settings
        ])
        .setup(|app| {
            let state = app.state::<AppState>();
            start_sidecar(&app.handle(), &state).map_err(std::io::Error::other)?;
            Ok(())
        })
        .build(tauri::generate_context!());

    match app {
        Ok(app) => app.run(|app_handle, event| {
            if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
                app_handle.state::<AppState>().stop();
            }
        }),
        Err(error) => report_startup_failure(&error),
    }
}
