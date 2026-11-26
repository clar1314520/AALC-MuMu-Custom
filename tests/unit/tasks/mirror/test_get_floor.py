"""闸层识别：单帧取图 + 有界轮询的流程测试

get_floor 原先"固定 sleep(1) → 截图找设置面板 → 再截一张彩色图数 CLEAR"，
其中后两张图之间没有任何点击，白等一个截图间隔。改造后每轮只取一张彩色图，
模板匹配用它的灰度副本、CLEAR 统计用它的彩色原件。

这里用假截图源和假识别结果钉住：
1. 面板没出现时会继续轮询，出现后立刻停止；
2. 整轮只调用 take_screenshot，且 find_regions_by_color 拿到的是同一帧；
3. 楼层号仍按 CLEAR 区域数量 +1 计算。
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from module.automation import auto
from tasks.mirror import get_floor as get_floor_module


@pytest.fixture()
def fake_auto(monkeypatch):
    state = {"captures": 0, "panel_checks": 0, "regions_frame": None, "floor_clicks": []}

    def fake_take_screenshot(gray: bool = True, max_age: float = 0.0):
        state["captures"] += 1
        image = Image.new("L" if gray else "RGB", (1600, 900), color=0)
        auto.screenshot = image
        return image

    def fake_find_element(target, *args, **kwargs):
        if target.endswith("setting_assets.png"):
            return (800, 200)
        if target.endswith("to_window_assets.png"):
            state["panel_checks"] += 1
            return (100, 100) if state["panel_checks"] >= 3 else None
        return None

    def fake_find_regions_by_color(roi, mask_fn, min_area=300, min_dist=80, image=None):
        state["regions_frame"] = image
        return [(1, 2, 400), (3, 4, 500)]

    monkeypatch.setattr(auto, "take_screenshot", fake_take_screenshot)
    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(auto, "find_regions_by_color", fake_find_regions_by_color)
    monkeypatch.setattr(auto, "mouse_action_with_pos", lambda position, **kwargs: True)
    monkeypatch.setattr(auto, "mouse_click_blank", lambda *args, **kwargs: True)
    monkeypatch.setattr(get_floor_module, "sleep", lambda *_: None)
    return state


def test_get_floor_reuses_single_frame_per_poll(fake_auto):
    floor = get_floor_module.get_floor(previous_floor=2)

    assert floor == 3, "两层 CLEAR 应为第 3 层"
    assert fake_auto["panel_checks"] == 3, "面板未出现时应继续轮询"
    assert fake_auto["captures"] == 3, "每轮只允许一次截图"
    assert fake_auto["regions_frame"] is not None, "CLEAR 统计应复用轮询那一帧"
    assert isinstance(fake_auto["regions_frame"], np.ndarray)
    assert fake_auto["regions_frame"].shape[:2] == (900, 1600)


def test_get_floor_reports_unknown_when_panel_never_opens(monkeypatch, fake_auto):
    """面板一直不出现时应按超时退出并返回 0，不会卡死。"""
    monkeypatch.setattr(
        get_floor_module, "FLOOR_PANEL_WAIT_TIMEOUT", 0.0, raising=True
    )
    floor = get_floor_module.get_floor(previous_floor=2)

    assert floor == 0
    assert fake_auto["regions_frame"] is None
