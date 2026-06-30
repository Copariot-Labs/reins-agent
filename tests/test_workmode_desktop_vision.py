from __future__ import annotations

import os

from reins.features.workmode.desktop_vision import (
    crop_image,
    normalize_ocr_text,
    verify_text_contains,
)


def test_normalize_ocr_text_collapses_whitespace_and_lowercases():
    assert normalize_ocr_text("  Hello\n\nWeChat\tTarget  ") == "hello wechat target"
    assert normalize_ocr_text("Hello", case_sensitive=True) == "Hello"


def test_verify_text_contains_supports_all_and_any_modes():
    text = "WeChat chat title Property Manager is visible."

    all_result = verify_text_contains(text, ["Property Manager", "WeChat"])
    assert all_result["ok"] is True
    assert all_result["missing"] == []

    missing_result = verify_text_contains(text, ["Property Manager", "Grid Office"])
    assert missing_result["ok"] is False
    assert missing_result["missing"] == ["Grid Office"]

    any_result = verify_text_contains(text, ["Grid Office", "WeChat"], mode="any")
    assert any_result["ok"] is True
    assert any_result["found"] == ["WeChat"]


def test_crop_image_writes_clamped_region(tmp_path):
    try:
        from PIL import Image
    except Exception:
        return

    old_home = os.environ.get("REINS_HOME")
    os.environ["REINS_HOME"] = str(tmp_path)
    try:
        source = tmp_path / "source.png"
        Image.new("RGB", (100, 80), "white").save(source)

        result = crop_image(
            case_id="case-vision",
            image_path=source,
            rect={"x": 90, "y": 70, "width": 50, "height": 40},
            label="corner",
        )

        assert result["ok"] is True
        assert result["crop_box"] == {"left": 90, "top": 70, "right": 100, "bottom": 80}
        assert os.path.exists(result["path"])

        cropped = Image.open(result["path"])
        assert cropped.size == (10, 10)
    finally:
        if old_home is None:
            os.environ.pop("REINS_HOME", None)
        else:
            os.environ["REINS_HOME"] = old_home
