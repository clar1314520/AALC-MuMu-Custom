"""脑啡肽兑换开关的行为测试

旧实现里 `skip_enkephalin` 只拦住「体力换饼」，`lunacy_to_enkephalin` 用两处硬编码
`skip=False` 把「狂气换体」放了过去；而且下拉框选「不换」时仍会开面板白跑一次换饼。

这里钉住拆分后的行为：
1. `skip_stamina_exchange` 只拦体力换饼；
2. `skip_lunacy_exchange` 只拦狂气换体；
3. 次数为 0 时整段兑换直接返回；
4. 禁止体力换饼时，狂气换体仍能把面板打开（converted=False），但不会点「全部换入」；
5. 旧配置项按「体力换饼」语义迁移。
"""

from __future__ import annotations

import pytest
from PIL import Image

from module.automation import auto
from module.config import cfg
from tasks.base import make_enkephalin_module as enkephalin_module

PANEL_MARKER = "enkephalin/use_lunacy_assets.png"
ALL_IN = "enkephalin/all_in_assets.png"
CANCEL = "enkephalin/enkephalin_cancel_assets.png"


@pytest.fixture()
def fake_auto(monkeypatch):
    calls = {"clicked": [], "screenshots": 0}

    def fake_click(target, *args, **kwargs):
        calls["clicked"].append(target)
        return True

    def fake_find(target, *args, **kwargs):
        # 面板已打开：仅命中狂气页签标记
        return (1, 1) if target == PANEL_MARKER else None

    def fake_take_screenshot(gray: bool = True, max_age: float = 0.0):
        calls["screenshots"] += 1
        auto.screenshot = Image.new("L", (8, 6))
        return auto.screenshot

    monkeypatch.setattr(auto, "click_element", fake_click)
    monkeypatch.setattr(auto, "find_element", fake_find)
    monkeypatch.setattr(auto, "take_screenshot", fake_take_screenshot)
    monkeypatch.setattr(auto, "mouse_to_blank", lambda *a, **k: None)
    monkeypatch.setattr(enkephalin_module, "sleep", lambda *_: None)
    monkeypatch.setattr(enkephalin_module, "retry", lambda *a, **k: None)
    return calls


@pytest.fixture()
def switches(monkeypatch):
    def apply(lunacy: bool = False, stamina: bool = False):
        monkeypatch.setattr(cfg.config, "skip_lunacy_exchange", lunacy)
        monkeypatch.setattr(cfg.config, "skip_stamina_exchange", stamina)

    return apply


def test_stamina_switch_blocks_module_conversion(fake_auto, switches):
    switches(stamina=True)

    enkephalin_module.make_enkephalin_module()

    assert fake_auto["clicked"] == []
    assert fake_auto["screenshots"] == 0


def test_stamina_switch_can_be_bypassed_explicitly(fake_auto, switches):
    """工具页的自动生产会显式传 skip=False，仍应正常换饼。"""
    switches(stamina=True)

    assert enkephalin_module.make_enkephalin_module(skip=False) is True
    assert ALL_IN in fake_auto["clicked"]


def test_panel_only_mode_does_not_convert(fake_auto, switches):
    """禁止体力换饼时，狂气换体仍需要面板，但不允许点「全部换入」。"""
    switches(stamina=True)

    assert enkephalin_module.make_enkephalin_module(cancel=False, skip=False, convert=False) is True

    assert ALL_IN not in fake_auto["clicked"]
    assert CANCEL not in fake_auto["clicked"]


def test_lunacy_switch_skips_whole_exchange(fake_auto, switches):
    switches(lunacy=True)

    enkephalin_module.lunacy_to_enkephalin(times=2)

    assert fake_auto["clicked"] == []
    assert fake_auto["screenshots"] == 0


def test_zero_times_does_nothing(fake_auto, switches):
    """下拉框选「不换」：不允许再开面板白跑一次体力换饼。"""
    switches()

    enkephalin_module.lunacy_to_enkephalin(times=0)

    assert fake_auto["clicked"] == []
    assert fake_auto["screenshots"] == 0


def test_legacy_skip_enkephalin_migrates_to_stamina_switch():
    legacy = {"skip_enkephalin": True}

    cfg._old_version_cfg_upgrade(1795737599, legacy)

    assert legacy["skip_stamina_exchange"] is True
    assert legacy["skip_lunacy_exchange"] is False
    assert "skip_enkephalin" not in legacy
