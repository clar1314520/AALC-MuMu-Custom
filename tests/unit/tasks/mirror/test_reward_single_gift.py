"""奖励界面：单饰品直给页的快通道

打关后有两种奖励界面：
1. 三选一（Select Encounter Reward Card）：要认 5 种奖励卡模板，再点领取；
2. 单饰品直给：屏幕上只有一张饰品卡 + 一个确认按钮，没得挑。

单饰品页完全不该走"识别饰品名 → 判断已持有 → 比较 EGO 体系"那套流程。
这里钉住三件事：
1. 单饰品页只做两次模板匹配就确认，且不触发任何 OCR；
2. 三选一页行为不变，选的还是配置里排第一的那张卡；
3. 界面带"拒绝"入口的单饰品页仍保留白棉花判断（不能被快通道绕过）。
"""

from __future__ import annotations

import pytest
from PIL import Image

from module.automation import auto
from module.config import cfg
from tasks.mirror import mirror as mirror_module
from tasks.mirror import reward_card as reward_module
from tasks.mirror.mirror import Mirror
from tasks.mirror.reward_card import (
    EGO_GIFT_CARD_MARKER,
    EGO_GIFT_CONFIRM,
    get_reward_card,
)

SCREEN_W, SCREEN_H = 1600, 900


@pytest.fixture()
def screen_900(monkeypatch):
    monkeypatch.setattr(cfg.config, "set_win_size", SCREEN_H)
    monkeypatch.setattr(auto, "screenshot", Image.new("L", (SCREEN_W, SCREEN_H), 0))
    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    return None


def test_single_gift_page_confirms_without_reward_card_matching(monkeypatch, screen_900):
    """单饰品直给：确认按钮 + 只有一个卡框 → 直接点确认，不碰奖励卡模板。"""
    calls = {"match": [], "click_element": [], "clicks": []}

    def fake_find_element(target, *args, **kwargs):
        calls["match"].append((target, kwargs.get("find_type", "image")))
        if target == EGO_GIFT_CONFIRM:
            return (752, 666)
        if target == EGO_GIFT_CARD_MARKER:
            return [(520, 700)]  # 只有一张饰品卡
        return None

    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(
        auto, "click_element", lambda target, *a, **k: calls["click_element"].append(target) or False
    )
    monkeypatch.setattr(auto, "mouse_click", lambda x, y, *a, **k: calls["clicks"].append((x, y)))

    assert get_reward_card() is True

    assert calls["clicks"] == [(752, 666)], "应直接点在确认按钮上"
    assert not [t for t in calls["click_element"] if "get_reward_card/gain" in t], (
        "单饰品页不该再匹配三选一的奖励卡模板"
    )
    assert len(calls["match"]) <= 2, f"只允许确认按钮 + 卡框两次匹配，实际 {calls['match']}"


def test_three_choice_page_still_picks_configured_card(monkeypatch, screen_900):
    """三选一页行为不变：按配置优先级点第一张能命中的奖励卡。"""
    page = {"state": "choice"}

    def fake_find_element(target, *args, **kwargs):
        if target == "mirror/road_in_mir/legend_assets.png" and page["state"] == "claimed":
            return (100, 100)
        return None

    def fake_click_element(target, *args, **kwargs):
        if target == "mirror/get_reward_card/gain_cost_and_ego.png":
            page["state"] = "claimed"
            return True
        return False

    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(auto, "click_element", fake_click_element)
    monkeypatch.setattr(auto, "mouse_click", lambda *a, **k: None)

    # reward_cards_select=3 → 顺序以 gain_ego 开头
    assert get_reward_card(3) is True
    assert page["state"] == "claimed"


def _fake_acquire_env(monkeypatch, *, refuse_available: bool):
    record = {"ocr": 0, "click_element": [], "clicks": []}

    def fake_find_element(target, *args, **kwargs):
        if kwargs.get("find_type") == "image_with_multiple_targets":
            return [(520, 700)]
        if target == "mirror/road_in_mir/refuse_gift_assets.png":
            return (200, 300) if refuse_available else None
        return None

    def fake_ocr_text_groups(crops, *a, **k):
        record["ocr"] += 1
        return [[] for _ in crops]

    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(auto, "ocr_text_groups", fake_ocr_text_groups)
    monkeypatch.setattr(auto, "match_language_text", lambda *a, **k: False)
    monkeypatch.setattr(auto, "mouse_click", lambda x, y, *a, **k: record["clicks"].append((x, y)))
    def fake_click_element(target, *a, **k):
        record["click_element"].append(target)
        # 循环开头的"确认"是另一条路径，这里让它不命中，逼流程走到饰品分支
        return target != "mirror/road_in_mir/ego_gift_get_confirm_assets.png"

    monkeypatch.setattr(auto, "click_element", fake_click_element)
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    monkeypatch.setattr(mirror_module.time, "sleep", lambda *a, **k: None)
    monkeypatch.setattr(mirror_module, "retry", lambda *a, **k: True)
    return record


def test_forced_single_gift_skips_ocr(monkeypatch, screen_900):
    """没有"拒绝"入口的单饰品页：拿上就走，一次 OCR 都不做。"""
    record = _fake_acquire_env(monkeypatch, refuse_available=False)
    Mirror.acquire_ego_gift(Mirror.__new__(Mirror))

    assert record["ocr"] == 0, "直给页不该识别饰品名"
    assert record["clicks"] == [(520, 700)], "应点在那张饰品卡上"
    assert "mirror/road_in_mir/acquire_ego_gift_select_assets.png" in record["click_element"]


def test_single_gift_with_refuse_keeps_white_gossypium_check(monkeypatch, screen_900):
    """能拒绝的单饰品页仍要识别一次，白棉花判断不能被快通道绕过。"""
    record = _fake_acquire_env(monkeypatch, refuse_available=True)
    Mirror.acquire_ego_gift(Mirror.__new__(Mirror))

    assert record["ocr"] >= 1, "存在拒绝入口时必须保留白棉花识别"


def test_reward_module_exports_stable_targets():
    """模板路径是常量，别在改动中被悄悄改错。"""
    assert reward_module.EGO_GIFT_CONFIRM.endswith("ego_gift_get_confirm_assets.png")
    assert reward_module.EGO_GIFT_CARD_MARKER.endswith("acquire_ego_gift_card.png")
