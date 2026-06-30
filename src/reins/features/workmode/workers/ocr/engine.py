from __future__ import annotations

from typing import Any


def extract_text_from_image(
    image_path: str,
    *,
    language: str | None = None,
    config: str | None = None,
) -> dict[str, Any]:
    """
    OCR engine.

    Requires:
      pip install pillow pytesseract
      brew install tesseract
    """

    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": f"OCR dependencies unavailable: {exc}",
            "source": image_path,
        }

    try:
        image = Image.open(image_path)
        kwargs: dict[str, Any] = {}
        if language:
            kwargs["lang"] = language
        if config:
            kwargs["config"] = config
        text = pytesseract.image_to_string(image, **kwargs)

        return {
            "ok": True,
            "text": text.strip(),
            "source": image_path,
            "language": language,
            "config": config,
            "image_size": {
                "width": image.width,
                "height": image.height,
            },
        }

    except Exception as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "source": image_path,
        }
