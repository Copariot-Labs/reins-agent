use std::{
    path::{Path, PathBuf},
    process::{Child, Command, Stdio},
    sync::Mutex,
};

use tauri::Manager;

struct BackendProcess(Mutex<Option<Child>>);

fn project_root() -> Result<PathBuf, String> {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../..")
        .canonicalize()
        .map_err(|error| {
            format!("Failed to resolve Reins project root: {error}")
        })
}

#[cfg(debug_assertions)]
fn start_backend(
    project_root: &Path,
) -> Result<Child, String> {
    let web_root = project_root.join("web");

    let server_entry =
        web_root.join("packages/server/src/index.ts");

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
            "ts-node/register",
            "packages/server/src/index.ts",
        ])
        .current_dir(&web_root)
        .env("NODE_ENV", "development")
        .env("PORT", "8647")
        .env("BIND_HOST", "127.0.0.1")
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|error| {
            format!("Failed to start Reins backend: {error}")
        })
}

fn stop_backend(
    state: &BackendProcess,
) {
    let Ok(mut guard) = state.0.lock() else {
        eprintln!("Failed to lock Reins backend state");
        return;
    };

    let Some(mut backend) = guard.take() else {
        return;
    };

    println!(
        "Stopping Reins backend (PID {})...",
        backend.id()
    );

    if let Err(error) = backend.kill() {
        eprintln!(
            "Failed to stop Reins backend: {}",
            error
        );
    }

    if let Err(error) = backend.wait() {
        eprintln!(
            "Failed to wait for Reins backend: {}",
            error
        );
    }

    println!("Reins backend stopped.");
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let root = project_root()
                    .map_err(
                        |error| -> Box<dyn std::error::Error> {
                            error.into()
                        },
                    )?;

                let backend = start_backend(&root)
                    .map_err(
                        |error| -> Box<dyn std::error::Error> {
                            error.into()
                        },
                    )?;

                println!(
                    "Reins backend process started with PID {}",
                    backend.id()
                );

                app.manage(
                    BackendProcess(
                        Mutex::new(Some(backend)),
                    ),
                );
            }

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Reins");

    app.run(|app_handle, event| {
        if let tauri::RunEvent::Exit = event {
            #[cfg(debug_assertions)]
            {
                if let Some(state) =
                    app_handle.try_state::<BackendProcess>()
                {
                    stop_backend(&state);
                }
            }
        }
    });
}