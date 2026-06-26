from __future__ import annotations

import json
import platform
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from reins.api.home import get_reins_home


def get_proof_dir(case_id: str) -> Path:
    proof_dir = get_reins_home() / "workmode" / "proofs" / case_id
    proof_dir.mkdir(parents=True, exist_ok=True)
    return proof_dir


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def capture_desktop_screenshot(
    *,
    case_id: str,
    label: str = "desktop",
) -> dict[str, Any]:
    """
    Capture a desktop screenshot as visible proof.

    This is intentionally best-effort:
    - macOS: screencapture
    - Linux: gnome-screenshot or ImageMagick import
    - Windows: PIL ImageGrab if installed

    It should never crash WorkMode.
    """

    proof_dir = get_proof_dir(case_id)
    output_path = proof_dir / f"{label}-{_timestamp()}.png"

    system = platform.system().lower()

    try:
        if system == "darwin":
            return _capture_macos(output_path)

        if system == "linux":
            return _capture_linux(output_path)

        if system == "windows":
            return _capture_windows(output_path)

        return {
            "ok": False,
            "error": f"Unsupported platform for screenshot: {system}",
            "path": None,
        }

    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "path": None,
        }


def _capture_macos(output_path: Path) -> dict[str, Any]:
    if not shutil.which("screencapture"):
        return {
            "ok": False,
            "error": "macOS screencapture command not found.",
            "path": None,
        }

    proc = subprocess.run(
        ["screencapture", "-x", str(output_path)],
        text=True,
        capture_output=True,
        timeout=15,
    )

    if proc.returncode != 0:
        return {
            "ok": False,
            "error": proc.stderr.strip() or "screencapture failed",
            "path": None,
        }

    return {
        "ok": True,
        "kind": "screenshot",
        "path": str(output_path),
        "platform": "macos",
    }


def _capture_linux(output_path: Path) -> dict[str, Any]:
    if shutil.which("gnome-screenshot"):
        proc = subprocess.run(
            ["gnome-screenshot", "-f", str(output_path)],
            text=True,
            capture_output=True,
            timeout=15,
        )

        if proc.returncode == 0:
            return {
                "ok": True,
                "kind": "screenshot",
                "path": str(output_path),
                "platform": "linux",
                "tool": "gnome-screenshot",
            }

    if shutil.which("import"):
        proc = subprocess.run(
            ["import", "-window", "root", str(output_path)],
            text=True,
            capture_output=True,
            timeout=15,
        )

        if proc.returncode == 0:
            return {
                "ok": True,
                "kind": "screenshot",
                "path": str(output_path),
                "platform": "linux",
                "tool": "imagemagick-import",
            }

    return {
        "ok": False,
        "error": "No supported Linux screenshot tool found.",
        "path": None,
    }


def _capture_windows(output_path: Path) -> dict[str, Any]:
    try:
        from PIL import ImageGrab
    except Exception as exc:
        return {
            "ok": False,
            "error": f"PIL ImageGrab unavailable: {exc}",
            "path": None,
        }

    image = ImageGrab.grab()
    image.save(output_path)

    return {
        "ok": True,
        "kind": "screenshot",
        "path": str(output_path),
        "platform": "windows",
    }


def write_proof_manifest(
    *,
    case_id: str,
    proofs: list[dict[str, Any]],
) -> dict[str, Any]:
    proof_dir = get_proof_dir(case_id)
    manifest_path = proof_dir / "manifest.json"

    manifest = {
        "case_id": case_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "proofs": proofs,
    }

    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return {
        "ok": True,
        "kind": "proof_manifest",
        "path": str(manifest_path),
    }
