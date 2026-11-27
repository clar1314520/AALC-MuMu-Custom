"""交互果断性：饰品确认框 / 商店离开确认 / 技能格索引

三处原本都是"死等"：
1. 选中饰品后无条件 `time.sleep(2)` 才去点 E.G.O Gift GET! 的 Confirm；
2. 点完商店 Leave 固定 `sleep(1)` 再回主循环找 "Leave the shop?" 确认；
3. 3 技能格下标少 +1，导致最左格漏选、其余格整体左移一格。

前两个改成有界轮询（出现即点、超时即放弃，不会更慢）；
第三个是纯逻辑修正，不增加任何截图或等待。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from module.automation import auto
from tasks.battle.battle import Battle
from tasks.mirror.mirror import Mirror
from tasks.mirror.in_shop import Shop


class Counter:
    def __init__(self, hit_at: int | None, result: bool = True):
        self.calls = 0
        self.hit_at = hit_at
        self.result = result

    def __call__(self, *args, **kwargs):
        self.calls += 1
        if self.hit_at is None:
            return False
        return self.result if self.calls >= self.hit_at else False


def test_ego_gift_confirm_clicks_as_soon_as_it_appears(monkeypatch):
    """确认框第 2 次就出现时，应该在 2 次轮询内点掉，而不是睡满 2 秒。"""
    click = Counter(hit_at=2)
    monkeypatch.setattr(auto, "click_element", click)

    assert Mirror._settle_ego_gift(Mirror.__new__(Mirror), timeout=3.0) is True
    assert click.calls == 2


def test_ego_gift_confirm_gives_up_on_timeout(monkeypatch):
    """一直不出现也要按超时退出，不能卡死流程。"""
    click = Counter(hit_at=None)
    monkeypatch.setattr(auto, "click_element", click)

    assert Mirror._settle_ego_gift(Mirror.__new__(Mirror), timeout=0.2) is False
    assert click.calls >= 1


def test_shop_leave_confirm_clicks_immediately(monkeypatch):
    """Leave 之后的二次确认：出现即点。"""
    click = Counter(hit_at=1)
    monkeypatch.setattr(auto, "click_element", click)

    shop = Shop.__new__(Shop)
    assert Shop._wait_leave_confirm(shop, timeout=2.0) is True
    assert click.calls == 1


def test_shop_leave_confirm_timeout(monkeypatch):
    click = Counter(hit_at=None)
    monkeypatch.setattr(auto, "click_element", click)

    shop = Shop.__new__(Shop)
    assert Shop._wait_leave_confirm(shop, timeout=0.2) is False


def test_skill3_snaps_to_nearest_slot():
    """匹配点要吸附到最近的技能格，且格号从 1 开始（skill_list[0] 是起点齿轮）。"""
    scale = 900 / 1440
    slots = [400 + 161 * scale * i for i in range(6)]

    assert Battle._snap_indexes_to_slots(slots, slots[:1]) == {1}
    assert Battle._snap_indexes_to_slots(slots, [slots[2], slots[5]]) == {3, 6}
    # 偏半格以内也要吸到正确格子（点击有抖动，不能因为几像素就跳到隔壁）
    assert Battle._snap_indexes_to_slots(slots, [slots[3] + 40 * scale]) == {4}
    # 离所有格子都超过半格（例如卡片外的杂色块）要丢掉，不能误判成边上那格
    assert Battle._snap_indexes_to_slots(slots, [slots[5] + 200 * scale]) == set()
    assert Battle._snap_indexes_to_slots([], [100]) == set()


def test_avoid_mode_keeps_skill3_slots():
    """避免模式应该把 3 技能格切到下层；优先模式反过来。"""
    assert Battle._get_lower_row_skill_indexes({1, 3}, 5, prioritize_skill_3=False) == {1, 3}
    assert Battle._get_lower_row_skill_indexes({1, 3}, 5, prioritize_skill_3=True) == {2, 4, 5}
