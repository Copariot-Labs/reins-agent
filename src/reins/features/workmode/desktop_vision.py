from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import time
from typing import Any

from reins.features.workmode.desktop_window import DesktopRect, parse_rect
from reins.features.workmode.proof import capture_desktop_screenshot, get_proof_dir
from reins.features.workmode.workers.ocr.engine import extract_text_from_image


@dataclass(frozen=True)
class TextVerification:
    ok: bool
    mode: str
    expected: list[str]
    found: list[str]
    missing: list[str]
    case_sensitive: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")


def _safe_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower())
    label = label.strip("-._")
    return label[:48] or "vision"


def _expected_terms(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        terms = [value]
    elif isinstance(value, (list, tuple, set)):
        terms = [str(item) for item in value]
    else:
        terms = [str(value)]
    return [term.strip() for term in terms if term and term.strip()]


def normalize_ocr_text(value: Any, *, case_sensitive: bool = False) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if case_sensitive else text.lower()


def verify_text_contains(
    text: str,
    expected: Any,
    *,
    mode: str = "all",
    case_sensitive: bool = False,
) -> dict[str, Any]:
    terms = _expected_terms(expected)
    if not terms:
        return TextVerification(
            ok=True,
            mode=mode,
            expected=[],
            found=[],
            missing=[],
            case_sensitive=case_sensitive,
        ).to_dict()

    normalized_text = normalize_ocr_text(text, case_sensitive=case_sensitive)
    found: list[str] = []
    missing: list[str] = []

    for term in terms:
        needle = normalize_ocr_text(term, case_sensitive=case_sensitive)
        if needle and needle in normalized_text:
            found.append(term)
        else:
            missing.append(term)

    check_mode = str(mode or "all").lower()
    ok = bool(found) if check_mode == "any" else not missing

    return TextVerification(
        ok=ok,
        mode="any" if check_mode == "any" else "all",
        expected=terms,
        found=found,
        missing=missing,
        case_sensitive=case_sensitive,
    ).to_dict()


def crop_image(
    *,
    case_id: str,
    image_path: str | Path,
    rect: DesktopRect | dict[str, Any] | list[Any] | tuple[Any, ...] | str,
    label: str = "crop",
) -> dict[str, Any]:
    target_rect = parse_rect(rect)
    source_path = Path(image_path)
    action: dict[str, Any] = {
        "ok": False,
        "kind": "vision_crop",
        "source": str(source_path),
        "rect": target_rect.to_dict() if target_rect else None,
    }

    if target_rect is None:
        action["error"] = "A valid crop rectangle is required."
        return action

    try:
        from PIL import Image
    except Exception as exc:
        action.update({
            "error_type": type(exc).__name__,
            "error": f"Pillow is unavailable: {exc}",
        })
        return action

    try:
        image = Image.open(source_path)
        left = max(0, target_rect.x)
        top = max(0, target_rect.y)
        right = max(left + 1, min(image.width, target_rect.x + target_rect.width))
        bottom = max(top + 1, min(image.height, target_rect.y + target_rect.height))
        cropped = image.crop((left, top, right, bottom))

        output_path = get_proof_dir(case_id) / f"{_safe_label(label)}-{_timestamp()}.png"
        cropped.save(output_path)

        action.update({
            "ok": True,
            "path": str(output_path),
            "source_size": {"width": image.width, "height": image.height},
            "crop_box": {"left": left, "top": top, "right": right, "bottom": bottom},
        })
        return action
    except Exception as exc:
        action.update({
            "error_type": type(exc).__name__,
            "error": str(exc),
        })
        return action


class DesktopVisionLayer:
    def __init__(self, *, case_id: str, visible: bool = True, hold_seconds: float = 0.25):
        self.case_id = case_id
        self.visible = visible
        self.hold_seconds = max(0.0, hold_seconds)

    def capture(self, *, label: str = "desktop-vision") -> dict[str, Any]:
        if self.visible and self.hold_seconds > 0:
            time.sleep(self.hold_seconds)
        screenshot = capture_desktop_screenshot(case_id=self.case_id, label=label)
        return {
            "ok": bool(screenshot.get("ok")),
            "kind": "vision_capture",
            "label": label,
            "screenshot": screenshot,
            "path": screenshot.get("path"),
            "error": screenshot.get("error"),
            "error_type": screenshot.get("error_type"),
        }

    def ocr_image(
        self,
        image_path: str | Path,
        *,
        label: str = "ocr",
        region: Any = None,
        expected_text: Any = None,
        match_mode: str = "all",
        case_sensitive: bool = False,
        language: str | None = None,
        config: str | None = None,
    ) -> dict[str, Any]:
        actions: list[dict[str, Any]] = []
        source_path = str(image_path)
        ocr_path = source_path

        if region is not None:
            crop = crop_image(
                case_id=self.case_id,
                image_path=source_path,
                rect=region,
                label=f"{label}-crop",
            )
            actions.append(crop)
            if not crop.get("ok") or not crop.get("path"):
                return {
                    "ok": False,
                    "kind": "vision_ocr",
                    "source": source_path,
                    "actions": actions,
                    "error": crop.get("error") or "Unable to crop image before OCR.",
                    "error_type": crop.get("error_type") or "CropError",
                }
            ocr_path = str(crop["path"])

        ocr = extract_text_from_image(ocr_path, language=language, config=config)
        text = str(ocr.get("text") or "")
        verification = verify_text_contains(
            text,
            expected_text,
            mode=match_mode,
            case_sensitive=case_sensitive,
        )
        require_expected = bool(_expected_terms(expected_text))
        ok = bool(ocr.get("ok")) and (verification.get("ok") or not require_expected)

        return {
            "ok": ok,
            "kind": "vision_ocr",
            "source": source_path,
            "ocr_source": ocr_path,
            "label": label,
            "ocr": ocr,
            "text": text,
            "verification": verification,
            "actions": actions,
            "error": None if ok else ocr.get("error") or "OCR verification failed.",
            "error_type": None if ok else ocr.get("error_type") or "VerificationError",
        }

    def capture_and_ocr(
        self,
        *,
        label: str = "desktop-ocr",
        region: Any = None,
        expected_text: Any = None,
        match_mode: str = "all",
        case_sensitive: bool = False,
        language: str | None = None,
        config: str | None = None,
    ) -> dict[str, Any]:
        capture = self.capture(label=label)
        actions: list[dict[str, Any]] = [capture]
        screenshot = capture.get("screenshot") if isinstance(capture.get("screenshot"), dict) else {}
        screenshot_path = screenshot.get("path") or capture.get("path")

        if not capture.get("ok") or not screenshot_path:
            return {
                "ok": False,
                "kind": "vision_capture_ocr",
                "label": label,
                "actions": actions,
                "screenshots": [],
                "error": capture.get("error") or "No screenshot available for OCR.",
                "error_type": capture.get("error_type") or "ScreenshotError",
            }

        ocr_result = self.ocr_image(
            str(screenshot_path),
            label=label,
            region=region,
            expected_text=expected_text,
            match_mode=match_mode,
            case_sensitive=case_sensitive,
            language=language,
            config=config,
        )
        actions.extend(ocr_result.get("actions") or [])

        screenshots = [str(screenshot_path)]
        for action in actions:
            path = action.get("path")
            if path:
                screenshots.append(str(path))

        return {
            "ok": bool(ocr_result.get("ok")),
            "kind": "vision_capture_ocr",
            "label": label,
            "source": str(screenshot_path),
            "ocr_source": ocr_result.get("ocr_source"),
            "screenshot": screenshot,
            "screenshots": list(dict.fromkeys(screenshots)),
            "ocr": ocr_result.get("ocr"),
            "text": ocr_result.get("text", ""),
            "verification": ocr_result.get("verification"),
            "actions": actions,
            "error": ocr_result.get("error"),
            "error_type": ocr_result.get("error_type"),
        }
