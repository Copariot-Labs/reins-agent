from __future__ import annotations

from dataclasses import asdict, dataclass
import os
from pathlib import Path
from typing import Any
import warnings

from reins.api.home import get_reins_home


SYSTEM_BROWSER_CANDIDATES = (
    ("chrome", Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")),
    ("chrome", Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe")),
    ("edge", Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")),
    ("edge", Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")),
    ("chrome", Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")),
    ("edge", Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge")),
    ("chrome", Path("/usr/bin/google-chrome")),
    ("chrome", Path("/usr/bin/google-chrome-stable")),
    ("chromium", Path("/usr/bin/chromium")),
    ("chromium", Path("/usr/bin/chromium-browser")),
    ("edge", Path("/usr/bin/microsoft-edge")),
    ("edge", Path("/usr/bin/microsoft-edge-stable")),
)

@dataclass(frozen=True)
class BrowserLaunchConfig:
    headless: bool
    persistent: bool
    profile_dir: str | None
    executable_path: str | None
    channel: str | None
    browser_name: str
    source: str

    def __post_init__(self):
        """Validate config after initialization."""
        if self.headless and self.persistent:
            warnings.warn(
                "Persistent profile with headless mode may not work as expected. "
                "Consider using non-persistent or non-headless mode.",
                UserWarning
            )

    def launch_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {
            "headless": self.headless,
            # Add stealth args to avoid detection
            "args": [
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-features=IsolateOrigins,site-per-process",
                "--disable-site-isolation-trials",
            ],
        }
        if self.executable_path:
            options["executable_path"] = self.executable_path
        elif self.channel:
            options["channel"] = self.channel
        return options

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def ensure_profile_dir(self) -> None:
        """Create profile directory if it doesn't exist."""
        if self.profile_dir:
            Path(self.profile_dir).mkdir(parents=True, exist_ok=True)


def _truthy(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _expand_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def get_default_profile_dir() -> Path:
    return get_reins_home() / "workmode" / "browser-profile"


def detect_browser_name_from_path(path: Path) -> str:
    """Detect browser name from executable path."""
    path_str = str(path).lower()
    # Check chromium first because it contains "chrome"
    if "chromium" in path_str:
        return "chromium"
    elif "chrome" in path_str:
        return "chrome"
    elif "edge" in path_str:
        return "edge"
    return "chrome"  # fallback


def resolve_browser_executable(preference: str | None = None) -> str | None:
    explicit = os.getenv("WORKMODE_BROWSER_EXECUTABLE", "").strip()
    if explicit:
        path = _expand_path(explicit)
        if path.exists():
            return str(path)
        # Don't return invalid path
        warnings.warn(f"Browser executable not found: {explicit}", UserWarning)
        return None

    preferred = (preference or os.getenv("WORKMODE_BROWSER") or "chrome").strip().lower()
    aliases = {
        "default": {"chrome", "edge", "chromium"},
        "system": {"chrome", "edge", "chromium"},
        "chrome": {"chrome"},
        "google-chrome": {"chrome"},
        "edge": {"edge"},
        "msedge": {"edge"},
        "chromium": {"chromium"},
    }
    wanted = aliases.get(preferred, {preferred})

    ordered = [
        (name, path)
        for name, path in SYSTEM_BROWSER_CANDIDATES
        if name in wanted
    ]
    if preferred in {"default", "system"}:
        ordered = list(SYSTEM_BROWSER_CANDIDATES)

    for _, candidate in ordered:
        if candidate.exists():
            return str(candidate)
    
    warnings.warn(f"No browser executable found for preference: {preferred}", UserWarning)
    return None


def resolve_browser_launch_config(
    *,
    visible: bool,
    persistent: bool | None = None,
    headless: bool | None = None,
    debug: bool = False,
) -> BrowserLaunchConfig:
    requested_headless = _truthy(os.getenv("WORKMODE_BROWSER_HEADLESS"), default=not visible)
    if headless is not None:
        requested_headless = headless

    use_system = _truthy(os.getenv("WORKMODE_BROWSER_USE_SYSTEM"), default=visible)
    preference = (os.getenv("WORKMODE_BROWSER") or "chrome").strip().lower()
    executable_path = resolve_browser_executable(preference) if use_system else None

    channel = os.getenv("WORKMODE_BROWSER_CHANNEL", "").strip() or None
    if channel == "bundled":
        channel = None

    if channel is None and executable_path is None and use_system and preference in {"chrome", "google-chrome"}:
        channel = "chrome"
    elif channel is None and executable_path is None and use_system and preference in {"edge", "msedge"}:
        channel = "msedge"

    persistent_default = visible and bool(executable_path or channel)
    persistent_requested = _truthy(os.getenv("WORKMODE_BROWSER_PERSISTENT"), default=persistent_default)
    if persistent is not None:
        persistent_requested = persistent

    profile_dir: str | None = None
    if persistent_requested:
        profile_env = os.getenv("WORKMODE_BROWSER_PROFILE_DIR", "").strip()
        profile_dir = str(_expand_path(profile_env)) if profile_env else str(get_default_profile_dir())
        # Ensure directory exists
        Path(profile_dir).mkdir(parents=True, exist_ok=True)

    # Determine browser name and source
    if executable_path:
        browser_name = detect_browser_name_from_path(Path(executable_path))
        source = "system_executable"
    elif channel:
        browser_name = channel
        source = "playwright_channel"
    else:
        browser_name = "chromium"
        source = "playwright_bundled"

    config = BrowserLaunchConfig(
        headless=requested_headless,
        persistent=persistent_requested,
        profile_dir=profile_dir,
        executable_path=executable_path,
        channel=channel,
        browser_name=browser_name,
        source=source,
    )

    if debug:
        print(f"🔧 Browser config: {config.to_dict()}")
        if config.profile_dir:
            exists = Path(config.profile_dir).exists()
            print(f"   Profile exists: {exists}")
            if exists:
                size = sum(f.stat().st_size for f in Path(config.profile_dir).rglob('*') if f.is_file())
                print(f"   Profile size: {size / 1024 / 1024:.2f} MB")

    return config