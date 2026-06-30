from __future__ import annotations

from reins.features.workmode.desktop_window import (
    DesktopRect,
    DesktopWindowLayer,
    _powershell_quote,
    parse_rect,
)


def test_parse_rect_accepts_dict_sequence_and_string():
    assert parse_rect({"x": 1, "y": 2, "width": 300, "height": 400}) == DesktopRect(1, 2, 300, 400)
    assert parse_rect([3, 4, 500, 600]) == DesktopRect(3, 4, 500, 600)
    assert parse_rect("7,8,900,1000") == DesktopRect(7, 8, 900, 1000)


def test_parse_rect_rejects_invalid_values():
    assert parse_rect("bad") is None
    assert parse_rect([1, 2, 3]) is None
    assert parse_rect({"x": "bad"}) is None


def test_collect_screenshots_reads_successful_action_proof_paths():
    layer = DesktopWindowLayer(case_id="case-1", visible=False)
    screenshots = layer.collect_screenshots([
        {"screenshot": {"ok": True, "path": "/tmp/a.png"}},
        {"screenshot": {"ok": False, "path": "/tmp/b.png"}},
        {"screenshot": {"ok": True, "path": "/tmp/a.png"}},
    ])

    assert screenshots == ["/tmp/a.png"]


def test_powershell_quote_escapes_single_quotes():
    assert _powershell_quote("Bob's App") == "Bob''s App"
