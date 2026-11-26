"""奖励卡页 / 饰品选择页的快路径与打点

钉住三件事：
1. 楼层奖励卡页不再"回主循环一轮一轮看"：选卡 + 点 Confirm 一步到位，且成功时
   不调用 retry()（retry 一轮就要一次截图 + 十几次匹配）；
2. 饰品选择页送进 OCR 的只有卡片名称带（饰品名 + Owned 徽章），不含下方效果描述；
3. 单饰品直给页仍然只做两次匹配就确认。
"""

from __future__ import annotations

import pytest
from PIL import Image

from module.automation import auto
from module.config import cfg
from tasks.mirror import reward_card as reward_module
from tasks.mirror.reward_card import EGO_GIFT_CONFIRM, get_reward_card

SCREEN_W, SCREEN_H = 1600, 900


@pytest.fixture()
def screen_900(monkeypatch):
    monkeypatch.setattr(cfg.config, "set_win_size", SCREEN_H)
    monkeypatch.setattr(auto, "screenshot", Image.new("L", (SCREEN_W, SCREEN_H), 0))
    monkeypatch.setattr(auto, "take_screenshot", lambda *a, **k: object())
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    return None


def test_reward_card_selects_and_confirms_without_loop(monkeypatch, screen_900):
    """一张卡 + 直接 Confirm：整个过程不应该走 retry()。"""
    card_position = (520, 360)
    clicks = []

    def fake_find_element(target, *args, **kwargs):
        if target == EGO_GIFT_CONFIRM:
            return None  # 不是单饰品直给页
        if target.endswith("gain_ego_resource.png"):
            return card_position
        return None

    def fake_click_element(target, *args, **kwargs):
        return "get_reward_card_confirm_assets" in target

    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(auto, "click_element", fake_click_element)
    monkeypatch.setattr(auto, "mouse_click", lambda x, y, *a, **k: clicks.append((x, y)))

    def _forbidden(*args, **kwargs):
        raise AssertionError("快路径命中时不该再走 retry()/主循环")

    monkeypatch.setattr(reward_module, "retry", _forbidden)

    # reward_cards_select=0 → gain_starlight 起头，这里只有 gain_ego_resource 能命中
    assert get_reward_card(0) is True
    assert clicks == [card_position], "应当先点中奖励卡"


def test_reward_card_confirm_poll_gives_up(monkeypatch, screen_900):
    """确认按钮一直不出现时要能退出快路径，落到轮询流程而不是卡死。"""
    monkeypatch.setattr(
        auto,
        "find_element",
        lambda target, *a, **k: (520, 360) if target.endswith("gain_starlight.png") else None,
    )
    monkeypatch.setattr(auto, "click_element", lambda *a, **k: False)
    monkeypatch.setattr(auto, "mouse_click", lambda *a, **k: None)

    state = {"retried": False}

    def fake_retry(*args, **kwargs):
        state["retried"] = True
        return False  # 让轮询循环直接退出

    monkeypatch.setattr(reward_module, "retry", fake_retry)

    assert get_reward_card(0) is False
    assert state["retried"] is True


def test_ocr_only_reads_card_title_band(monkeypatch, screen_900):
    """饰品选择页只把名称带送进 OCR，整卡（含效果描述）不再识别。"""
    from tasks.mirror.mirror import Mirror

    crops_seen = []
    markers = [(400, 700), (800, 700), (1200, 700)]
    marker = markers[1]
    scale = SCREEN_H / 1440

    def fake_find_element(target, *args, **kwargs):
        if kwargs.get("find_type") == "image_with_multiple_targets":
            return markers
        if target.endswith("refuse_gift_assets.png"):
            return None
        return None

    def fake_ocr_text_groups(crops, *a, **k):
        crops_seen.extend(crops)
        return [[] for _ in crops]

    monkeypatch.setattr(auto, "find_element", fake_find_element)
    monkeypatch.setattr(auto, "ocr_text_groups", fake_ocr_text_groups)
    monkeypatch.setattr(auto, "match_language_text", lambda *a, **k: False)
    monkeypatch.setattr(auto, "click_element", lambda target, *a, **k: False)
    monkeypatch.setattr(auto, "mouse_click", lambda *a, **k: None)
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    import tasks.mirror.mirror as mirror_module

    monkeypatch.setattr(mirror_module, "retry", lambda *a, **k: True)
    # "Select 0/1" 计数区模板在测试机上都按固定框返回，避免走真实的取图逻辑
    monkeypatch.setattr(
        mirror_module.ImageUtils,
        "get_bbox",
        staticmethod(lambda image: (1400, 1200, 1700, 1300)),
    )

    mirror = Mirror.__new__(Mirror)
    mirror.system = "burn"
    mirror.second_system = False
    Mirror.acquire_ego_gift(mirror, type=1)

    assert crops_seen, "应当至少识别一次"
    # 第一组 crop 是卡片名称带（三张卡各一条），最后一条是 "Select 0/1" 计数区
    assert len(crops_seen) >= 3
    for crop in crops_seen[:3]:
        assert crop[3] - crop[1] < 650 * scale * 0.5
    top, bottom = crops_seen[0][1], crops_seen[0][3]
    band_height = bottom - top
    full_card_height = 650 * scale
    assert band_height < full_card_height * 0.5, (
        f"名称带高度 {band_height:.0f} 应远小于整卡 {full_card_height:.0f}，否则描述文字又被送进 OCR 了"
    )
    # 名称行在卡框标记上方约 170px(1440 基准)，必须落在名称带里；整卡下半部分的
    # 效果描述区（标记下方）一定不能在带内。
    name_row_y = marker[1] - 170 * scale
    assert top <= name_row_y <= bottom, "名称带必须覆盖卡框标记上方的名称行"
    assert bottom < marker[1] - 60 * scale, "名称带不能延伸到图标/描述区域"
