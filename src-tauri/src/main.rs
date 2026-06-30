use serde::Serialize;
use std::{
    io::{Read, Write},
    net::{TcpStream, ToSocketAddrs},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::Mutex,
    thread,
    time::{Duration, Instant},
};
use tauri::Manager;

const APP_URL: &str = "http://127.0.0.1:8765";
const HEALTH_PATH: &str = "/api/settings/status";

struct BackendService {
    child: Mutex<Option<Child>>,
    project_root: Mutex<Option<PathBuf>>,
}

#[derive(Clone, Serialize)]
struct BackendStatus {
    running: bool,
    managed_by_tauri: bool,
    pid: Option<u32>,
    url: String,
    health_url: String,
    project_root: Option<String>,
    message: String,
}

fn health_url() -> String {
    format!("{APP_URL}{HEALTH_PATH}")
}

fn project_root() -> Option<PathBuf> {
    if let Ok(value) = std::env::var("SHU_REIMBURSEMENT_ROOT") {
        let path = PathBuf::from(value);
        if path.join("app.py").exists() {
            return Some(path);
        }
    }

    let mut candidates = Vec::new();
    if let Ok(current) = std::env::current_dir() {
        candidates.push(current);
    }
    if let Ok(exe) = std::env::current_exe() {
        candidates.extend(exe.ancestors().map(PathBuf::from));
    }

    for candidate in candidates {
        if candidate.join("app.py").exists() {
            return Some(candidate);
        }
        if candidate.join("../app.py").exists() {
            if let Some(parent) = candidate.parent() {
                return Some(parent.to_path_buf());
            }
        }
    }
    None
}

fn backend_health_ok() -> bool {
    let addr = match ("127.0.0.1", 8765).to_socket_addrs().ok().and_then(|mut a| a.next()) {
        Some(addr) => addr,
        None => return false,
    };
    let mut stream = match TcpStream::connect_timeout(&addr, Duration::from_millis(700)) {
        Ok(stream) => stream,
        Err(_) => return false,
    };
    let _ = stream.set_read_timeout(Some(Duration::from_millis(900)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(700)));
    if stream
        .write_all(b"GET /api/settings/status HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = String::new();
    if stream.read_to_string(&mut response).is_err() {
        return false;
    }
    response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200")
}

fn wait_for_backend(timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if backend_health_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(300));
    }
    false
}

fn start_backend_if_needed(state: &BackendService) -> Result<BackendStatus, String> {
    if backend_health_ok() {
        return Ok(BackendStatus {
            running: true,
            managed_by_tauri: false,
            pid: None,
            url: APP_URL.to_string(),
            health_url: health_url(),
            project_root: project_root().map(|p| p.display().to_string()),
            message: "本机 FastAPI 服务已在 127.0.0.1:8765 运行，桌面端直接复用。".to_string(),
        });
    }

    let root = project_root().ok_or_else(|| "未找到 app.py，无法启动本机 FastAPI 服务。".to_string())?;
    let child = Command::new("python3")
        .args(["-m", "uvicorn", "app:app", "--host", "127.0.0.1", "--port", "8765"])
        .current_dir(&root)
        .env("PYTHONUNBUFFERED", "1")
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|err| format!("启动 FastAPI 服务失败：{err}"))?;
    let pid = child.id();

    {
        let mut project_root = state.project_root.lock().map_err(|_| "服务状态锁异常".to_string())?;
        *project_root = Some(root.clone());
        let mut managed_child = state.child.lock().map_err(|_| "服务进程锁异常".to_string())?;
        *managed_child = Some(child);
    }

    if !wait_for_backend(Duration::from_secs(18)) {
        return Err("FastAPI 服务启动后没有通过健康检查。".to_string());
    }

    Ok(BackendStatus {
        running: true,
        managed_by_tauri: true,
        pid: Some(pid),
        url: APP_URL.to_string(),
        health_url: health_url(),
        project_root: Some(root.display().to_string()),
        message: "Tauri 已启动本机 FastAPI 服务。".to_string(),
    })
}

#[tauri::command]
fn backend_status(state: tauri::State<'_, BackendService>) -> BackendStatus {
    let child_pid = state
        .child
        .lock()
        .ok()
        .and_then(|child| child.as_ref().map(|process| process.id()));
    let project_root = state
        .project_root
        .lock()
        .ok()
        .and_then(|root| root.as_ref().map(|path| path.display().to_string()))
        .or_else(|| project_root().map(|path| path.display().to_string()));
    let running = backend_health_ok();
    BackendStatus {
        running,
        managed_by_tauri: child_pid.is_some(),
        pid: child_pid,
        url: APP_URL.to_string(),
        health_url: health_url(),
        project_root,
        message: if running {
            "本机 FastAPI 服务可用。".to_string()
        } else {
            "本机 FastAPI 服务不可用。".to_string()
        },
    }
}

fn shutdown_backend(state: &BackendService) {
    let Ok(mut child) = state.child.lock() else {
        return;
    };
    if let Some(mut process) = child.take() {
        let _ = process.kill();
        let _ = process.wait();
    }
}

fn main() {
    tauri::Builder::default()
        .manage(BackendService {
            child: Mutex::new(None),
            project_root: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![backend_status])
        .setup(|app| {
            let state = app.state::<BackendService>();
            start_backend_if_needed(&state)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                let state = window.state::<BackendService>();
                shutdown_backend(&state);
            }
        })
        .run(tauri::generate_context!())
        .expect("failed to run Shanghai University reimbursement agent");
}
