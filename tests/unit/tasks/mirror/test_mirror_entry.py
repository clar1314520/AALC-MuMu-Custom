"""镜牢入口识别的回归测试。

背景：新版游戏把 Drive 界面里的镜牢入口改成两行小字，旧的
``home/mirror_dungeons_assets.png`` 匹配不上，road_to_mir 会退回
"点 Window 图标"的兜底分支，结果在 Drive / Window 两个界面之间
来回跳，永远进不了镜牢。这里用一个最小的界面状态机复现该场景。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from module.automation import auto
from tasks.mirror import mirror as mirror_module
from tasks.mirror.mirror import MIRROR_ENTRY_ASSETS, Mirror
from utils.path_manager import path_manager

DRIVE_SCREEN = "drive"
WINDOW_SCREEN = "window"
TEAM_SCREEN = "team"

# 三种界面下"能看到"的元素
VISIBLE = {
    DRIVE_SCREEN: {
        "home/drive_assets.png",
        "home/window_assets.png",
        "home/inferno_bus_assets.png",
        "home/mirror_dungeons_v2_assets.png",
    },
    WINDOW_SCREEN: {
        "home/drive_assets.png",
        "home/window_assets.png",
    },
    TEAM_SCREEN: {
        "mirror/road_to_mir/select_team_stars_assets.png",
    },
}

# 点击后的界面跳转
TRANSITIONS = {
    (DRIVE_SCREEN, "home/mirror_dungeons_v2_assets.png"): TEAM_SCREEN,
    (WINDOW_SCREEN, "home/drive_assets.png"): DRIVE_SCREEN,
    (DRIVE_SCREEN, "home/window_assets.png"): WINDOW_SCREEN,
}


class FakeGame:
    def __init__(self, screen: str):
        self.screen = screen
        self.clicks: list[str] = []

    def has(self, target: str) -> bool:
        return target in VISIBLE[self.screen]

    def click(self, target: str):
        if not self.has(target):
            return None
        self.clicks.append(target)
        self.screen = TRANSITIONS.get((self.screen, target), self.screen)
        return (100, 100)


@pytest.fixture
def game(monkeypatch):
    """把 road_to_mir 依赖的交互全部替换成内存状态机。"""
    fake = FakeGame(DRIVE_SCREEN)
    counters = {"back_menu": 0}

    # road_to_mir 里会读 infinity_mirror_bbox.png，先把图片路径准备好
    path_manager.initialize_paths()
    path_manager.set_language("en")

    def back_init_menu(*args, **kwargs):
        counters["back_menu"] += 1

    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    monkeypatch.setattr(auto, "find_text_element", lambda *a, **k: None)
    monkeypatch.setattr(auto, "find_element", lambda target, *a, **k: (100, 100) if fake.has(target) else None)
    monkeypatch.setattr(auto, "click_element", lambda target, *a, **k: fake.click(target))
    monkeypatch.setattr(mirror_module, "retry", lambda *a, **k: None)
    monkeypatch.setattr(mirror_module, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(mirror_module, "back_init_menu", back_init_menu)

    fake.counters = counters
    return fake


def run_road_to_mir():
    """避开 Mirror 的构造依赖，只跑 road_to_mir 本身。"""
    instance = object.__new__(Mirror)
    instance.road_to_mir()


def test_click_mirror_entry_instead_of_bouncing(game):
    """Drive 界面上能认出镜牢入口时，必须直接点它，不能去点 Window。"""
    run_road_to_mir()

    assert "home/mirror_dungeons_v2_assets.png" in game.clicks
    assert "home/window_assets.png" not in game.clicks, "不应在 Drive/Window 之间来回跳"


def test_stuck_between_screens_still_exits(game):
    """即使模板全部失效，也要能兜底退出，而不是无限来回点。"""
    game.screen = WINDOW_SCREEN
    for visible in VISIBLE.values():
        visible.discard("home/mirror_dungeons_v2_assets.png")

    run_road_to_mir()

    assert game.counters["back_menu"] >= 1, "空转多轮后应调用 back_init_menu 兜底"


def test_entry_assets_stay_in_sync():
    """常量里必须同时保留新旧两份模板，且文件真实存在。"""
    root = Path(__file__).resolve().parents[4]
    assert MIRROR_ENTRY_ASSETS == (
        "home/mirror_dungeons_assets.png",
        "home/mirror_dungeons_v2_assets.png",
    )
    for name in MIRROR_ENTRY_ASSETS:
        assert (root / "assets" / "images" / "default" / "en" / name).is_file(), name
