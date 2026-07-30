use std::env;
use std::path::{Path, PathBuf};


fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    {
        env::var_os("USERPROFILE").map(PathBuf::from)
    }

    #[cfg(not(windows))]
    {
        env::var_os("HOME").map(PathBuf::from)
    }
}


fn expand_home(path: PathBuf) -> PathBuf {
    let text = path.to_string_lossy();

    if text == "~" {
        return home_dir().unwrap_or(path);
    }

    if let Some(relative_path) = text.strip_prefix("~/") {
        if let Some(home) = home_dir() {
            return home.join(relative_path);
        }
    }

    path
}


fn is_executable_file(path: &Path) -> bool {
    if !path.is_file() {
        return false;
    }

    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;

        return path
            .metadata()
            .map(|metadata| {
                metadata.permissions().mode() & 0o111 != 0
            })
            .unwrap_or(false);
    }

    #[cfg(not(unix))]
    {
        true
    }
}


fn default_reins_home() -> Result<PathBuf, String> {
    #[cfg(windows)]
    {
        let local_app_data = env::var_os("LOCALAPPDATA")
            .ok_or_else(|| {
                "LOCALAPPDATA is unavailable. Reins home could not be resolved."
                    .to_string()
            })?;

        return Ok(
            PathBuf::from(local_app_data)
                .join("reins")
        );
    }

    #[cfg(not(windows))]
    {
        let home = home_dir().ok_or_else(|| {
            "HOME is unavailable. Reins home could not be resolved."
                .to_string()
        })?;

        Ok(home.join(".reins"))
    }
}


fn reins_home() -> Result<PathBuf, String> {
    match env::var_os("REINS_HOME") {
        Some(value) if !value.is_empty() => {
            Ok(expand_home(PathBuf::from(value)))
        }
        _ => default_reins_home(),
    }
}


fn launcher_filename() -> &'static str {
    #[cfg(windows)]
    {
        "reins-avatar-acp.cmd"
    }

    #[cfg(not(windows))]
    {
        "reins-avatar-acp"
    }
}


pub fn resolve_reins_acp_argv() -> Result<Vec<String>, String> {
    /*
     * Development override.
     *
     * `reins avatar dev` provides this environment variable so the
     * Tauri development application always uses the bridge generated
     * by the current Reins project.
     */
    if let Some(command) = env::var_os("REINS_AVATAR_ACP_COMMAND") {
        if !command.is_empty() {
            let command_path = expand_home(PathBuf::from(command));

            if is_executable_file(&command_path) {
                return Ok(vec![
                    command_path
                        .to_string_lossy()
                        .into_owned(),
                ]);
            }

            return Err(format!(
                "REINS_AVATAR_ACP_COMMAND does not point to an executable file: {}",
                command_path.display()
            ));
        }
    }

    /*
     * Production/default installation.
     */
    let launcher_path = reins_home()?
        .join("plugins")
        .join("reins-avatar")
        .join("bin")
        .join(launcher_filename());

    if is_executable_file(&launcher_path) {
        return Ok(vec![
            launcher_path
                .to_string_lossy()
                .into_owned(),
        ]);
    }

    /*
     * Final fallback for development machines where the Reins command
     * is available globally or from the current shell environment.
     */
    if let Some(reins_executable) =
        crate::commands::agent_setup::find_executable_on_path("reins")
    {
        return Ok(vec![
            reins_executable
                .to_string_lossy()
                .into_owned(),
            "acp".to_string(),
        ]);
    }

    Err(format!(
        "Reins Agent is not connected. The ACP bridge was expected at: {}. \
Run `reins avatar install` from the Reins Agent project.",
        launcher_path.display()
    ))
}


pub fn describe_reins_acp_command() -> Result<String, String> {
    resolve_reins_acp_argv()
        .map(|arguments| arguments.join(" "))
}


#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn launcher_name_matches_current_platform() {
        #[cfg(windows)]
        assert_eq!(
            launcher_filename(),
            "reins-avatar-acp.cmd"
        );

        #[cfg(not(windows))]
        assert_eq!(
            launcher_filename(),
            "reins-avatar-acp"
        );
    }
}