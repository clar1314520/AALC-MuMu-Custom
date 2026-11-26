"""流畅度优化：饰品升级两次即退 / 寻路确认即点 / 纯P战斗

三处原本的浪费：
1. 饰品升级每级固定 ``sleep(3)``，且升满两级后还会去点第三次；
2. 路线图选中节点后固定 ``sleep(1.25)`` 才点"进入"，看起来"犹豫一下"；
3. 战斗没有"只按P"的开关，想纯手操拼点只能关掉整个战斗逻辑。

这里只断言行为（点几下、点了哪个坐标、按了哪些键），不断言真实耗时。
"""

from __future__ import annotations

import pytest

from module.automation import auto
from module.config import cfg
from tasks.battle.battle import Battle
from tasks.mirror import in_shop as in_shop_module
from tasks.mirror.in_shop import Shop
from tasks.mirror.search_road import MirrorMap, _road_offset


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    """把各处 sleep 打掉，避免单测真的等下去。"""
    import importlib

    battle_module = importlib.import_module("tasks.battle.battle")
    search_road_module = importlib.import_module("tasks.mirror.search_road")
    monkeypatch.setattr(in_shop_module, "sleep", lambda *_: None)
    monkeypatch.setattr(battle_module, "sleep", lambda *_: None)
    monkeypatch.setattr(search_road_module, "sleep", lambda *_: None)


def _shop() -> Shop:
    return Shop.__new__(Shop)


def test_ego_gift_upgrade_stops_after_two(monkeypatch):
    """升满两次就要退出，绝不能再去点第三次。"""
    counts = {"power_up": 0, "confirm": 0}

    def click_element(target, *args, **kwargs):
        if target.endswith("power_up_assets.png"):
            counts["power_up"] += 1
            return [10, 10]
        if target.endswith("power_up_confirm_assets.png"):
            counts["confirm"] += 1
            return [10, 10]
        return False

    monkeypatch.setattr(auto, "click_element", click_element)
    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())
    monkeypatch.setattr(auto, "find_element", lambda *a, **k: None)
    monkeypatch.setattr(in_shop_module, "retry", lambda *a, **k: True)

    assert _shop().ego_gift_to_power_up() is True
    assert counts["power_up"] == 2
    assert counts["confirm"] == 2


def test_ego_gift_upgrade_exits_when_button_missing(monkeypatch):
    """没有升级按钮（已升满/不可升级）时应当立刻返回，不做第三次尝试。"""
    calls = []

    def click_element(target, *args, **kwargs):
        calls.append(target)
        return False

    monkeypatch.setattr(auto, "click_element", click_element)
    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())

    assert _shop().ego_gift_to_power_up() is True
    assert len(calls) == 1


def test_enter_next_node_blind_clicks_cached_bus(monkeypatch):
    """有缓存 Bus 坐标时直接用预判位置点节点，不再重新识别 Bus。"""
    mirror_map = MirrorMap(floor=1)
    mirror_map._bus_position = [100, 300]

    clicked = []
    monkeypatch.setattr(auto, "mouse_click", lambda x, y, **k: clicked.append((x, y)))
    monkeypatch.setattr(auto, "click_element", lambda target, **k: [5, 5] if "enter_assets" in target else False)

    def _no_bus(*args, **kwargs):
        raise AssertionError("盲点命中时不应该再找一次 Bus")

    monkeypatch.setattr(auto, "find_element", _no_bus)

    assert mirror_map.enter_next_node("M") is True
    offset = _road_offset("M")
    assert clicked == [(100 + offset[0], 300 + offset[1])]


def test_enter_next_node_falls_back_to_bus(monkeypatch):
    """盲点没命中要立刻回退到实时定位 Bus，而不是直接失败。"""
    mirror_map = MirrorMap(floor=1)
    mirror_map._bus_position = [100, 300]

    clicked = []
    monkeypatch.setattr(auto, "mouse_click", lambda x, y, **k: clicked.append((x, y)))

    state = {"bus_found": False}

    def click_element(target, *args, **kwargs):
        if "enter_assets" in target and state["bus_found"]:
            return [5, 5]
        return False

    def find_element(target, *args, **kwargs):
        if "legend_assets" in target:
            return [1, 1]
        if "mybus_default_distance" in target:
            state["bus_found"] = True
            return [120, 320]
        return None

    monkeypatch.setattr(auto, "click_element", click_element)
    monkeypatch.setattr(auto, "find_element", find_element)

    assert mirror_map.enter_next_node("U") is True
    offset = _road_offset("U")
    # 第一次盲点用的是旧 Bus 坐标，回退后按新识别到的 Bus 再点一次
    assert clicked[0] == (100 + offset[0], 300 + offset[1])
    assert clicked[-1] == (120 + offset[0], 320 + offset[1])
    assert mirror_map._bus_position == [120, 320]


def test_enter_next_node_keeps_map_when_already_entered(monkeypatch):
    """已经进入节点（路线图消失）时不要再去等 Bus。"""
    mirror_map = MirrorMap(floor=1)
    mirror_map._bus_position = [100, 300]

    monkeypatch.setattr(auto, "mouse_click", lambda x, y, **k: None)
    monkeypatch.setattr(auto, "click_element", lambda target, **k: False)
    monkeypatch.setattr(auto, "find_element", lambda target, **k: None)

    assert mirror_map.enter_next_node("M") is True


def test_refresh_floor_clears_bus_anchor():
    mirror_map = MirrorMap(floor=1)
    mirror_map._bus_position = [100, 690]
    mirror_map.refresh_floor(2)
    assert mirror_map._bus_position is None


def test_pure_p_only_presses_p(monkeypatch):
    """纯P模式：不划线、不防御，只按 P + Enter。"""
    monkeypatch.setattr(cfg, "battle_pure_p", True)

    battle = Battle()
    keys = []
    monkeypatch.setattr(auto, "mouse_click_blank", lambda *a, **k: None)
    monkeypatch.setattr(auto, "key_press", lambda key, *a, **k: keys.append(key))
    monkeypatch.setattr(auto, "find_element", lambda *a, **k: None)

    def _forbidden(*args, **kwargs):
        raise AssertionError("纯P模式不应该划线连技能或防御")

    monkeypatch.setattr(Battle, "_chain_battle", staticmethod(_forbidden))
    monkeypatch.setattr(Battle, "_defense_this_round", staticmethod(_forbidden))

    assert battle._battle_operation(first_turn=True, defense_first_round=True, avoid_skill_3=True) is False
    assert keys == ["p", "enter"]


def test_pure_p_off_keeps_chain_battle(monkeypatch):
    """关掉纯P后仍然走原来的划线逻辑（这里只验证分支没被写死）。"""
    monkeypatch.setattr(cfg, "battle_pure_p", False)

    battle = Battle()
    used = {"chain": False}

    monkeypatch.setattr(auto, "mouse_click_blank", lambda *a, **k: None)
    monkeypatch.setattr(auto, "key_press", lambda *a, **k: None)
    monkeypatch.setattr(auto, "find_element", lambda *a, **k: [10, 10])

    def _chain(prioritize_skill_3=False):
        used["chain"] = True
        return True

    monkeypatch.setattr(Battle, "_chain_battle", staticmethod(_chain))
    monkeypatch.setattr(auto, "click_element", lambda *a, **k: False)

    battle._battle_operation(first_turn=False, defense_first_round=False, avoid_skill_3=True)
    assert used["chain"] is True
