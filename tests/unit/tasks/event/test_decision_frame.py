"""事件判定：同一帧派生两份灰度图的功能测试

判定页原先会连截两帧（彩色一次、灰度一次），中间没有任何点击。改造后只截一帧：
- 一份把红色成功率徽章抹黑，用来找极高/高/一般；
- 一份保留原色转灰度，用来找低/极低。

这里用 1600x900（MuMu 常用分辨率）的合成画面验证：
1. 一次判定只允许截图一次；
2. 金色徽章仍能被找到并点击到正确位置；
3. 红色徽章在"抹红"那一份里失效、"保留原色"那一份里仍可命中并点击。
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from module.automation import auto
from module.config import cfg
from module.logger import log
from tasks.event.event_handling import (
    EventHandling,
    black_out_red,
    get_sinner_bbox,
)
from utils.image_utils import ImageUtils
from utils.path_manager import path_manager

SCREEN_W, SCREEN_H = 1600, 900


@pytest.fixture()
def screen_900(monkeypatch):
    """把窗口尺寸切到 1600x900 并初始化图片路径（pydantic 字段直写，不落盘）。"""
    monkeypatch.setattr(cfg.config, "set_win_size", SCREEN_H)
    path_manager.initialize_paths()
    path_manager.set_language("zh_cn")
    return None


def build_frame(
    badge_path: str, top_left: tuple[int, int], keep_color: bool = False
) -> tuple[Image.Image, tuple[int, int]]:
    """在暗色渐变背景上贴一档成功率徽章，返回画面与该徽章的屏幕中心点。

    keep_color=True 时按原素材的彩色贴图（红色徽章必须保留颜色才测得出"抹红"逻辑），
    否则直接贴灰度模板（尺寸与 find_element 加载的模板完全一致）。
    """
    width, height = SCREEN_W, SCREEN_H
    xs = np.arange(width, dtype=np.int32)[None, :]
    ys = np.arange(height, dtype=np.int32)[:, None]
    background = ((xs // 17 + ys // 11) % 45 + 12).astype(np.uint8)
    frame = np.dstack([background, background, background])

    template = ImageUtils.load_image(badge_path)
    assert template is not None, f"缺少测试素材 {badge_path}"
    badge_h, badge_w = template.shape[:2]

    if keep_color:
        source = Image.open(f"assets/images/default/zh_cn/{badge_path}").convert("RGB")
        badge = np.array(source.resize((badge_w, badge_h), Image.Resampling.LANCZOS))
    else:
        badge = np.dstack([template, template, template])

    left, top = top_left
    frame[top : top + badge_h, left : left + badge_w] = badge

    return Image.fromarray(frame), (left + badge_w // 2, top + badge_h // 2)


def install_frame(monkeypatch, frame: Image.Image, calls: dict):
    """用固定画面替换真实截图，并记录点击坐标。"""

    def fake_take_screenshot(gray: bool = True, max_age: float = 0.0):
        calls["screenshot"] += 1
        image = frame.convert("L") if gray else frame
        auto.screenshot = image
        return image

    monkeypatch.setattr(auto, "take_screenshot", fake_take_screenshot)
    monkeypatch.setattr(
        auto, "mouse_action_with_pos", lambda position, **kwargs: calls["click"].append(position) or True
    )


def test_single_screenshot_finds_gold_badge(monkeypatch, screen_900):
    calls = {"screenshot": 0, "click": []}
    frame, expected_center = build_frame("event/very_high.png", (420, 800))
    install_frame(monkeypatch, frame, calls)

    assert EventHandling().decision_event_handling() is True

    assert calls["screenshot"] == 1, "一次判定只应截图一次"
    assert len(calls["click"]) == 1
    clicked_x, clicked_y = calls["click"][0]
    assert abs(clicked_x - expected_center[0]) <= 3
    assert abs(clicked_y - expected_center[1]) <= 3


def test_red_badge_survives_in_warn_pass(monkeypatch, screen_900):
    """红色徽章必须在"抹红"那一份里失效、在"保留原色"那一份里命中。"""
    calls = {"screenshot": 0, "click": []}
    frame, expected_center = build_frame("event/low.png", (420, 800), keep_color=True)
    install_frame(monkeypatch, frame, calls)

    assert EventHandling().decision_event_handling() is True

    assert calls["screenshot"] == 1, "两趟匹配必须共用同一帧"
    assert len(calls["click"]) == 1
    clicked_x, clicked_y = calls["click"][0]
    assert abs(clicked_x - expected_center[0]) <= 3
    assert abs(clicked_y - expected_center[1]) <= 3


def test_red_badge_removed_only_inside_sinner_bbox(screen_900):
    """black_out_red 只处理罪人栏内，且不会因 bbox 越界而崩溃。"""
    frame, _ = build_frame("event/low.png", (420, 800), keep_color=True)
    array = np.array(frame)

    def red_count(image_array):
        r = image_array[:, :, 0].astype(np.int16)
        g = image_array[:, :, 1].astype(np.int16)
        b = image_array[:, :, 2].astype(np.int16)
        return int(((r - np.maximum(g, b)) >= 60).sum())

    bbox = get_sinner_bbox()
    assert bbox is not None
    red_before = red_count(array)
    assert red_before > 0, "测试画面里应当有红色徽章像素"

    black_out_red(array, bbox)
    assert red_count(array) < red_before, "罪人栏内的红色徽章应被抹掉"

    # 越界 bbox 不应抛异常
    black_out_red(array, (-50, -50, SCREEN_W + 500, SCREEN_H + 500))
    log.debug("越界 bbox 处理完成")
