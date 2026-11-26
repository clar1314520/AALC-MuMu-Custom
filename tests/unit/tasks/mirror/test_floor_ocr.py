"""楼层 OCR：解析容错、ROI 缩放、失败回退的回归测试。

原实现靠"点齿轮 → 数 CLEAR 徽章"识别楼层，一次要 3~4 秒；现在改成直接读界面上
的楼层文字（地图页 "Exploring Floor 3"、卡包页 "SELECT FLOOR 1 THEME PACK"）。
"""

from __future__ import annotations

import pytest

from module.automation import auto
from module.config import cfg
from tasks.mirror import get_floor as floor_module
from tasks.mirror.get_floor import get_floor, parse_floor_text


@pytest.mark.parametrize(
    ("texts", "expected"),
    [
        (["Exploring Floor 1"], 1),
        (["Exploring", "Floor 3"], 3),
        (["SELECTFLOOR1THEMEPACK"], 1),
        (["SELECT FLOOR 12 THEME PACK"], 12),
        (["SELECTFL0OR5THEMEPACK"], 5),  # OCR 把 O 认成 0
        (["Floor 7", "The Outcast"], 7),
        (["The Outcast", "NORMAL"], 0),  # 没有楼层字样
        (["FLOOR 25"], 0),  # 超出合理范围
        ([], 0),
        (None, 0),
    ],
)
def test_parse_floor_text(texts, expected):
    assert parse_floor_text(texts) == expected


def test_roi_scales_with_window_size(monkeypatch):
    monkeypatch.setattr(cfg.config, "set_win_size", 900)
    roi = floor_module._scale_roi(floor_module.FLOOR_OCR_ROI["theme_pack"])
    assert roi == (560, 100, 1040, 300)

    monkeypatch.setattr(cfg.config, "set_win_size", 1440)
    assert floor_module._scale_roi(floor_module.FLOOR_OCR_ROI["theme_pack"]) == (896, 160, 1664, 480)


def test_floor_by_ocr_parses_theme_pack_title(monkeypatch):
    calls = {}

    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())

    def fake_groups(crops, fast_ocr=True):
        calls["crops"] = crops
        return [["SELECTFLOOR4THEMEPACK"]]

    monkeypatch.setattr(auto, "ocr_text_groups", fake_groups)

    assert floor_module._floor_by_ocr("theme_pack") == 4
    assert len(calls["crops"]) == 1, "一次 OCR 只应裁一个区域"


def test_get_floor_falls_back_to_setting_panel(monkeypatch):
    """OCR 读不出时必须退回设置面板，而不是直接把楼层当成未知。"""
    monkeypatch.setattr(floor_module, "_floor_by_ocr", lambda screen: 0)
    monkeypatch.setattr(floor_module, "_floor_by_setting", lambda assets: 3)

    assert get_floor(2, "map") == 3


def test_get_floor_skips_panel_when_ocr_succeeds(monkeypatch):
    """OCR 成功时不允许再点齿轮（否则提速白做）。"""
    monkeypatch.setattr(floor_module, "_floor_by_ocr", lambda screen: 3)

    def fail_panel(assets):
        raise AssertionError("OCR 已识别到楼层，不应再打开设置面板")

    monkeypatch.setattr(floor_module, "_floor_by_setting", fail_panel)

    assert get_floor(2, "theme_pack") == 3
