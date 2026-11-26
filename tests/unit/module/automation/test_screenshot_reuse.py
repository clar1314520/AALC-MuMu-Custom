"""截图复用（max_age）与彩色帧复用的行为测试

背景：take_screenshot 受 cfg.screenshot_interval 节流，任意两次连续截图之间至少相隔
一个间隔。镜牢卡包页 / 事件页曾经出现过"中间没有任何点击，却连续截两次图"的写法，
每次白等一个间隔。这里用假截图源计数，钉住三条边界：

1. 默认 max_age=0 永远重新截图（不改变既有行为）；
2. 刚截过图且色彩模式一致时，max_age 允许复用同一帧，不再触发截图；
3. 模式不一致或帧已过期时必须重新截图。

另外验证 find_regions_by_color(image=...) 复用调用方帧时不再自行截图。
"""

from __future__ import annotations

import threading

import numpy as np
import pytest
from PIL import Image

from module.automation import automation as automation_module


@pytest.fixture()
def shot_counter(monkeypatch):
    """替换真实截图源，只计数不碰窗口。"""
    calls = {"gray": 0, "color": 0}

    def fake_take_screenshot(gray: bool = True):
        if gray:
            calls["gray"] += 1
            return Image.new("L", (8, 6))
        calls["color"] += 1
        return Image.new("RGB", (8, 6))

    monkeypatch.setattr(
        automation_module.ScreenShot, "take_screenshot", staticmethod(fake_take_screenshot)
    )
    calls["total"] = lambda: calls["gray"] + calls["color"]
    return calls


@pytest.fixture()
def driver(monkeypatch):
    """构造一个跳过 __init__ 的 Automation，只保留截图相关状态。"""
    from types import SimpleNamespace

    # 关掉节流，让测试只关心"是否触发截图"
    monkeypatch.setattr(automation_module, "cfg", SimpleNamespace(screenshot_interval=0.0))

    instance = automation_module.Automation.__new__(automation_module.Automation)
    instance._screenshot_lock = threading.RLock()
    instance._latest_screenshot = None
    instance._latest_screenshot_monotonic = 0.0
    instance.screenshot = None
    instance.last_screenshot_time = 0.0
    return instance


def test_default_never_reuses(driver, shot_counter):
    """max_age=0 时必须每次都重新截图。"""
    first = driver.take_screenshot()
    second = driver.take_screenshot()

    assert shot_counter["total"]() == 2
    assert first is not second


def test_reuse_returns_same_frame_without_capture(driver, shot_counter):
    """刚截到的一帧在 max_age 内可复用，且不产生新的截图。"""
    first = driver.take_screenshot()
    second = driver.take_screenshot(max_age=0.5)

    assert shot_counter["total"]() == 1
    assert second is first
    assert driver.screenshot is first


def test_reuse_requires_matching_color_mode(driver, shot_counter):
    """缓存是灰度帧时，请求彩色帧不能复用。"""
    driver.take_screenshot(gray=True)
    driver.take_screenshot(gray=False, max_age=0.5)

    assert shot_counter["gray"] == 1
    assert shot_counter["color"] == 1


def test_expired_frame_is_not_reused(driver, shot_counter):
    """超出 max_age 的帧必须重新截图。"""
    driver.take_screenshot()
    driver._latest_screenshot_monotonic -= 1.0

    driver.take_screenshot(max_age=0.2)

    assert shot_counter["total"]() == 2


def test_invalidate_cache_forces_capture(driver, shot_counter):
    """监控线程要求换帧时，复用不能挡住新截图。"""
    driver.take_screenshot()
    driver.invalidate_screenshot_cache()
    driver.take_screenshot(max_age=0.5)

    assert shot_counter["total"]() == 2


def test_find_regions_by_color_reuses_given_image(driver, shot_counter):
    """传入彩色帧时不该再自行截图（get_floor 的合并取帧依赖这一点）。"""
    image = np.zeros((20, 40, 3), dtype=np.uint8)
    image[5:15, 10:30] = (255, 0, 0)

    def mask_fn(roi):
        return np.where(roi[:, :, 0] > 200, 255, 0).astype(np.uint8)

    regions = driver.find_regions_by_color(
        None, mask_fn, min_area=1, min_dist=1, image=image
    )

    assert shot_counter["total"]() == 0
    assert regions and len(regions) == 1
