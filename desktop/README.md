# Reins Desktop

Reins Desktop is distributed to Windows users as one installer:

```text
Reins-Setup-x64.exe
```

The installer includes the Reins web application, agent runtime, Office support,
browser support, Finance, and WeCom integration. End users do not install Node,
Python, Rust, .NET, OfficeCLI, or any upstream agent package. They only install
and launch Reins.

## End-user experience

1. Double-click `Reins-Setup-x64.exe`.
2. Complete the per-user installer; administrator access is not required. When
   upgrading, the installer stops the Reins window and its private background
   processes before replacing the bundled runtime.
3. Launch **Reins** from the Start menu or desktop shortcut.
4. Sign in or create the local Reins account.
5. Open **Settings → WeCom** and enter the ticket URL, ticket token, group robot
   webhook, and default recipient. Reins stores these values in the user's
   private application-data directory and starts the WeCom ticket poller in the
   background.

## Configure credentials

End users should configure credentials inside Reins instead of copying a
project `.env` file into the installation directory:

- Open **Models → Add provider** to enter an AI provider, API key, base URL,
  and model. Reins stores these values for the selected profile.
- Open **Settings → WeCom** to enter the work-order API and WeCom values. Reins
  writes the supported values to its private user configuration and restarts
  the background ticket service.

For advanced support only, the desktop product environment file is stored at:

```text
%LOCALAPPDATA%\com.copariot.reins\.env
```

Close Reins before manually editing this file. Values saved through the UI are
preferred because they are validated before the related service is restarted.

Office and Finance are enabled automatically. PowerPoint files are created and
previewed through Office; there is no separate Presentation feature.

## Build the Windows installer

The release must be built on a Windows x64 machine. The build machine needs:

- Node.js 24 and pnpm 10
- uv
- Rust with the `x86_64-pc-windows-msvc` target
- .NET SDK 10
- Visual Studio C++ Build Tools (available on GitHub's Windows runner)

From PowerShell at the repository root:

```powershell
.\scripts\build-windows-desktop.ps1
```

The build prompts twice for the administrator password. It must contain at
least 12 characters. For a non-interactive build, set either
`REINS_ADMIN_PASSWORD` or a previously generated `REINS_ADMIN_PASSWORD_HASH`.
Only the salted `scrypt` hash is included in the installer; the plaintext
password is never staged. Every fresh installation is therefore protected
before its first launch.

The output is:

```text
release\Reins-Setup-x64.exe
```

The staging script builds and embeds all private runtimes under the Tauri
resource directory. These build-time directories are ignored by Git and must
not be committed.

## GitHub Actions build

Run **Build Reins for Windows** manually from the Actions page, or push a tag
matching `desktop-v*`. Manual builds provide the `Reins-Windows-x64` workflow
artifact for testing. Tagged builds also create a GitHub Release and attach:

```text
Reins-Setup-x64.exe
Reins-Setup-x64.exe.sha256
```

Release downloads are public when the GitHub repository is public. Releases in
a private repository remain available only to people who can access the
repository. Re-running a tagged workflow replaces the files on its existing
release instead of creating duplicates.

Before creating a release tag, keep these three desktop versions equal to the
tag version:

```text
desktop/package.json
desktop/src-tauri/tauri.conf.json
desktop/src-tauri/Cargo.toml
```

For a public release, configure these repository secrets so the workflow signs
the installer and avoids Windows' unsigned-publisher warning:

- `WINDOWS_SIGNING_PFX_BASE64`: Base64-encoded Authenticode `.pfx` certificate
- `WINDOWS_SIGNING_PFX_PASSWORD`: Certificate password

The workflow also requires one of these administrator-access secrets:

- `REINS_ADMIN_PASSWORD`: Administrator password used for this Windows build
- `REINS_ADMIN_PASSWORD_HASH`: Pre-generated Reins password hash; when present,
  it takes precedence over `REINS_ADMIN_PASSWORD`

## User data and background work

Mutable data is stored outside the installation directory:

```text
%LOCALAPPDATA%\com.copariot.reins
```

This includes the local database, generated Office documents, Finance data,
logs, and the private configuration written by the Settings UI. The WeCom
poller is registered as a current-user scheduled task named
`Reins WeCom Ticket Poller`, so it starts at sign-in and continues after the
main window closes. Uninstalling Reins removes the scheduled task but preserves
the user's data.

Third-party notices remain bundled with the application as required by their
licenses, but no third-party setup screens, commands, or product names are shown
in the normal Reins installation and application flow.
