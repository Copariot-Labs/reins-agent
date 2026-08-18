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
2. Complete the per-user installer; administrator access is not required.
3. Launch **Reins** from the Start menu or desktop shortcut.
4. Sign in or create the local Reins account.
5. Open **Settings → WeCom** and enter the ticket URL, ticket token, group robot
   webhook, and default recipient. Reins stores these values in the user's
   private application-data directory and starts the WeCom ticket poller in the
   background.

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

The output is:

```text
release\Reins-Setup-x64.exe
```

The staging script builds and embeds all private runtimes under the Tauri
resource directory. These build-time directories are ignored by Git and must
not be committed.

## GitHub Actions build

Run **Build Reins for Windows** manually from the Actions page, or push a tag
matching `desktop-v*`. Download the `Reins-Windows-x64` workflow artifact.

For a public release, configure these repository secrets so the workflow signs
the installer and avoids Windows' unsigned-publisher warning:

- `WINDOWS_SIGNING_PFX_BASE64`: Base64-encoded Authenticode `.pfx` certificate
- `WINDOWS_SIGNING_PFX_PASSWORD`: Certificate password

Without those secrets, the workflow still creates an unsigned test installer.

## User data and background work

Mutable data is stored outside the installation directory:

```text
%LOCALAPPDATA%\reins
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
