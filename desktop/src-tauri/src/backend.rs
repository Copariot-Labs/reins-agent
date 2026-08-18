use tauri::AppHandle;
use tauri_plugin_shell::ShellExt;

pub fn start_backend(app: &AppHandle) {

    let reins_path =
        "/Users/junxiang/Developer/reins-agent/.venv/bin/reins";

    let result = app
        .shell()
        .command(reins_path)
        .args(["web"])
        .spawn();

    match result {
        Ok(_) => {
            println!("Reins backend started");
        }

        Err(error) => {
            println!(
                "Failed to start Reins backend: {}",
                error
            );
        }
    }
}