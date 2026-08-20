use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};

#[cfg(not(debug_assertions))]
use std::{
    fs::OpenOptions,
    io::{Read, Write},
    net::{SocketAddr, TcpStream},
    thread,
    time::{Duration, Instant},
};

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

#[tauri::command]
async fn save_download(file_name: String, bytes: Vec<u8>) -> Result<bool, String> {
    let safe_file_name = Path::new(&file_name)
        .file_name()
        .and_then(|name| name.to_str())
        .filter(|name| !name.is_empty())
        .unwrap_or("download")
        .to_owned();

    let Some(target) = rfd::AsyncFileDialog::new()
        .set_file_name(&safe_file_name)
        .save_file()
        .await
    else {
        return Ok(false);
    };

    target
        .write(&bytes)
        .await
        .map_err(|error| format!("Failed to save {}: {error}", target.path().display()))?;

    Ok(true)
}

#[cfg(debug_assertions)]
fn project_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|error| format!("Failed to resolve Reins project root: {error}"))
}

#[cfg(not(debug_assertions))]
fn backend_is_ready(port: u16) -> bool {
    let address = SocketAddr::from(([127, 0, 0, 1], port));
    let Ok(mut stream) = TcpStream::connect_timeout(&address, Duration::from_millis(500)) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    if stream
        .write_all(b"GET /health/ready HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }
    let mut response = [0_u8; 512];
    let Ok(length) = stream.read(&mut response) else {
        return false;
    };
    String::from_utf8_lossy(&response[..length]).contains(" 200 ")
}

#[cfg(not(debug_assertions))]
enum BackendWaitResult {
    Ready,
    Exited(String),
    TimedOut,
}

#[cfg(not(debug_assertions))]
fn backend_exit_detail(state: &BackendProcess) -> Option<String> {
    let Ok(mut guard) = state.0.lock() else {
        return Some("The local service state could not be checked.".to_owned());
    };
    let backend = guard.as_mut()?;
    match backend.try_wait() {
        Ok(Some(status)) => Some(match status.code() {
            Some(code) => format!("The local service stopped with exit code {code}."),
            None => "The local service stopped unexpectedly.".to_owned(),
        }),
        Ok(None) => None,
        Err(error) => Some(format!("The local service could not be checked: {error}")),
    }
}

#[cfg(not(debug_assertions))]
fn wait_for_backend(state: &BackendProcess, port: u16, timeout: Duration) -> BackendWaitResult {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if backend_is_ready(port) {
            return BackendWaitResult::Ready;
        }
        if let Some(detail) = backend_exit_detail(state) {
            return BackendWaitResult::Exited(detail);
        }
        thread::sleep(Duration::from_millis(250));
    }
    if backend_is_ready(port) {
        BackendWaitResult::Ready
    } else if let Some(detail) = backend_exit_detail(state) {
        BackendWaitResult::Exited(detail)
    } else {
        BackendWaitResult::TimedOut
    }
}

#[cfg(not(debug_assertions))]
fn show_startup_error(message: &str) {
    let _ = rfd::MessageDialog::new()
        .set_title("Reins could not start")
        .set_description(message)
        .set_level(rfd::MessageLevel::Error)
        .show();
}

#[cfg(debug_assertions)]
fn start_backend(project_root: &Path) -> Result<Child, String> {
    let web_root = project_root.join("web");

    let server_entry = web_root.join("packages/server/src/index.ts");

    if !server_entry.exists() {
        return Err(format!(
            "Reins development server not found: {}",
            server_entry.display()
        ));
    }

    println!("Starting Reins development backend");
    println!("Web root: {}", web_root.display());
    println!("Server: {}", server_entry.display());

    Command::new("node")
        .args([
            "-r",
            "ts-node/register/transpile-only",
            "packages/server/src/index.ts",
        ])
        .current_dir(&web_root)
        .env("NODE_ENV", "development")
        .env("PORT", "8647")
        .env("BIND_HOST", "127.0.0.1")
        .env("TS_NODE_PROJECT", "packages/server/tsconfig.json")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| format!("Failed to start Reins backend: {error}"))
}

#[cfg(not(debug_assertions))]
fn start_backend(app: &tauri::App) -> Result<Option<Child>, String> {
    const PORT: u16 = 8648;
    if backend_is_ready(PORT) {
        return Ok(None);
    }

    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|error| format!("Failed to resolve Reins resources: {error}"))?;
    let runtime = resource_dir.join("runtime");
    let node = runtime.join("node").join("node.exe");
    let server = runtime.join("web").join("server").join("index.js");
    let python = runtime.join("python").join("python.exe");
    let reins = runtime.join("bin").join("reins-runtime.exe");
    let officecli = runtime.join("bin").join("officecli.exe");
    let agent_root = runtime.join("agent");
    let skills = runtime.join("web").join("skills");

    for required in [&node, &server, &python, &reins, &officecli] {
        if !required.is_file() {
            return Err(format!(
                "Required Reins runtime file is missing: {}",
                required.display()
            ));
        }
    }
    if !agent_root.join("run_agent.py").is_file() {
        return Err(format!(
            "Reins agent runtime is incomplete: {}",
            agent_root.display()
        ));
    }

    let reins_home = app
        .path()
        .app_local_data_dir()
        .map_err(|error| format!("Failed to resolve Reins data directory: {error}"))?;
    let logs_dir = reins_home.join("logs");
    std::fs::create_dir_all(&logs_dir)
        .map_err(|error| format!("Failed to create Reins data directory: {error}"))?;
    let backend_log_path = logs_dir.join("desktop-backend.log");
    let mut backend_stdout = OpenOptions::new()
        .create(true)
        .append(true)
        .open(&backend_log_path)
        .map_err(|error| format!("Failed to open {}: {error}", backend_log_path.display()))?;
    writeln!(
        backend_stdout,
        "\n--- Reins desktop startup ---\nRuntime: {}\nNode: {}\nServer: {}",
        runtime.display(),
        node.display(),
        server.display(),
    )
    .map_err(|error| format!("Failed to write the Reins startup log: {error}"))?;
    let backend_stderr = backend_stdout
        .try_clone()
        .map_err(|error| format!("Failed to prepare the Reins startup log: {error}"))?;

    let mut path_entries = vec![
        runtime.join("bin"),
        runtime.join("python"),
        runtime.join("node"),
    ];
    if let Some(existing) = std::env::var_os("PATH") {
        path_entries.extend(std::env::split_paths(&existing));
    }
    let runtime_path = std::env::join_paths(path_entries)
        .map_err(|error| format!("Failed to construct Reins runtime PATH: {error}"))?;

    let mut command = Command::new(&node);
    command
        // The working directory is runtime/web, so use a relative entry path.
        // This avoids Windows drive-letter and space parsing edge cases.
        .arg(Path::new("server").join("index.js"))
        .current_dir(runtime.join("web"))
        .env("NODE_ENV", "production")
        .env("PORT", PORT.to_string())
        .env("BIND_HOST", "127.0.0.1")
        .env("REINS_DESKTOP", "1")
        .env("REINS_HOME", &reins_home)
        .env("HERMES_HOME", &reins_home)
        .env("HERMES_WEB_UI_HOME", reins_home.join("web-ui"))
        .env("REINS_RUNTIME_ROOT", &runtime)
        .env("REINS_BIN", &reins)
        .env("HERMES_BIN", &reins)
        .env("REINS_SERVICE_PYTHON", &python)
        .env("HERMES_AGENT_BRIDGE_PYTHON", &python)
        .env("HERMES_AGENT_ROOT", &agent_root)
        .env("HERMES_WEB_UI_SKILLS_DIR", &skills)
        .env("OFFICECLI_BIN", &officecli)
        .env("OFFICECLI_SKIP_UPDATE", "1")
        .env("PLAYWRIGHT_BROWSERS_PATH", runtime.join("playwright"))
        .env("PYTHONHOME", runtime.join("python"))
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
        .env("HERMES_WEB_UI_DISABLE_UPDATE_CHECK", "true")
        .env("PATH", runtime_path)
        .stdin(Stdio::null())
        .stdout(Stdio::from(backend_stdout))
        .stderr(Stdio::from(backend_stderr));

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    command
        .spawn()
        .map(Some)
        .map_err(|error| format!("Failed to start the private Reins runtime: {error}"))
}

fn stop_backend(state: &BackendProcess) {
    let Ok(mut guard) = state.0.lock() else {
        eprintln!("Failed to lock Reins backend state");
        return;
    };

    let Some(mut backend) = guard.take() else {
        return;
    };

    println!("Stopping Reins backend (PID {})...", backend.id());

    if let Err(error) = backend.kill() {
        eprintln!("Failed to stop Reins backend: {}", error);
    }

    if let Err(error) = backend.wait() {
        eprintln!("Failed to wait for Reins backend: {}", error);
    }

    println!("Reins backend stopped.");
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![save_download])
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let root = project_root()
                    .map_err(|error| -> Box<dyn std::error::Error> { error.into() })?;

                let backend = start_backend(&root)
                    .map_err(|error| -> Box<dyn std::error::Error> { error.into() })?;

                println!("Reins backend process started with PID {}", backend.id());

                app.manage(BackendProcess(Mutex::new(Some(backend))));
                if let Some(window) = app.get_webview_window("main") {
                    window.show()?;
                }
            }

            #[cfg(not(debug_assertions))]
            {
                let backend = match start_backend(app) {
                    Ok(backend) => backend,
                    Err(error) => {
                        show_startup_error(&error);
                        return Err(error.into());
                    }
                };
                app.manage(BackendProcess(Mutex::new(backend)));

                let handle = app.handle().clone();
                let startup_log = app
                    .path()
                    .app_local_data_dir()
                    .map(|path| path.join("logs").join("desktop-backend.log"))
                    .unwrap_or_else(|_| PathBuf::from("desktop-backend.log"));
                thread::spawn(move || {
                    let wait_result = if let Some(state) = handle.try_state::<BackendProcess>() {
                        wait_for_backend(&state, 8648, Duration::from_secs(30))
                    } else {
                        BackendWaitResult::Exited(
                            "The local service process was not initialized.".to_owned(),
                        )
                    };
                    match wait_result {
                        BackendWaitResult::Ready => {}
                        BackendWaitResult::Exited(detail) => {
                            show_startup_error(&format!(
                                "Reins could not start its local service. {detail}\n\nPlease reinstall the latest Reins release. If the problem continues, send this log file to support:\n{}",
                                startup_log.display()
                            ));
                            handle.exit(1);
                            return;
                        }
                        BackendWaitResult::TimedOut => {
                            show_startup_error(&format!(
                                "Reins is taking longer than expected to start. Restart Reins once. If the problem continues, send this log file to support:\n{}",
                                startup_log.display()
                            ));
                            handle.exit(1);
                            return;
                        }
                    }
                    if let Some(window) = handle.get_webview_window("main") {
                        // Keep the packaged frontend on Tauri's trusted local origin.
                        // It already sends API requests to the private service on port
                        // 8648. Navigating the webview to that HTTP origin removes the
                        // Tauri IPC bridge, which is required by save_download.
                        if let Err(error) = window.eval("window.location.reload()") {
                            show_startup_error(&format!(
                                "Failed to initialize the Reins interface: {error}"
                            ));
                            handle.exit(1);
                            return;
                        }
                        if let Err(error) = window.show() {
                            show_startup_error(&format!("Failed to show the Reins window: {error}"));
                            handle.exit(1);
                        }
                    }
                });
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Reins");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            if let Some(state) = app_handle.try_state::<BackendProcess>() {
                stop_backend(&state);
            }
        }
    });
}
