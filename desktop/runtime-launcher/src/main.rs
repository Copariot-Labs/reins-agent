#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use std::{
    env,
    path::PathBuf,
    process::{Command, ExitCode, Stdio},
};

fn runtime_root() -> Result<PathBuf, String> {
    if let Some(configured) = env::var_os("REINS_RUNTIME_ROOT") {
        let path = PathBuf::from(configured);
        if path.is_dir() {
            return Ok(path);
        }
    }
    let executable =
        env::current_exe().map_err(|error| format!("Could not resolve Reins runtime: {error}"))?;
    executable
        .parent()
        .and_then(|bin| bin.parent())
        .map(PathBuf::from)
        .ok_or_else(|| "Could not resolve the private Reins runtime directory".to_owned())
}

fn run() -> Result<i32, String> {
    let runtime = runtime_root()?;
    let python = runtime.join("python").join("python.exe");
    if !python.is_file() {
        return Err("The Reins runtime is incomplete. Please reinstall Reins.".to_owned());
    }

    let mut command = Command::new(&python);
    command
        .args(["-m", "reins.main"])
        .args(env::args_os().skip(1))
        .env("REINS_RUNTIME_ROOT", &runtime)
        .env("HERMES_AGENT_ROOT", runtime.join("agent"))
        .env("OFFICECLI_BIN", runtime.join("bin").join("officecli.exe"))
        .env("OFFICECLI_SKIP_UPDATE", "1")
        .env("PLAYWRIGHT_BROWSERS_PATH", runtime.join("playwright"))
        .env("PYTHONHOME", runtime.join("python"))
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUTF8", "1")
        .stdin(Stdio::inherit())
        .stdout(Stdio::inherit())
        .stderr(Stdio::inherit());

    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        command.creation_flags(0x08000000);
    }

    let status = command
        .status()
        .map_err(|error| format!("Could not start Reins: {error}"))?;
    Ok(status.code().unwrap_or(1))
}

fn main() -> ExitCode {
    match run() {
        Ok(code) => ExitCode::from(u8::try_from(code).unwrap_or(1)),
        Err(error) => {
            eprintln!("{error}");
            ExitCode::FAILURE
        }
    }
}
