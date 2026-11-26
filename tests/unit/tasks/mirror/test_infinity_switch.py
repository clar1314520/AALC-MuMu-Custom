"""无限镜牢开关识别：把 4.2 秒的整帧 OCR 换掉

`road_to_mir` 每轮都要判断无限镜牢入口旁的 "off" 字样。那块区域只有 170x31，
用整帧 OCR 引擎（Det.limit_type=min）会被放大到短边 736，实测单次 4.2 秒，
循环看起来就是"卡在 Drive 界面没反应"。

这里钉住：换成小区域识别后判据不变（有 off → 关闭）、异常不会把任务带崩。
"""

from __future__ import annotations

import numpy as np
import pytest

from module.automation import auto
from module.config import cfg
from tasks.mirror.mirror import Mirror
from utils.path_manager import path_manager

SCREEN_W, SCREEN_H = 1600, 900


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setattr(cfg.config, "set_win_size", SCREEN_H)
    path_manager.initialize_paths()
    path_manager.set_language("en")
    monkeypatch.setattr(auto, "screenshot", np.zeros((SCREEN_H, SCREEN_W), dtype=np.uint8))
    return None


def _stub_ocr(monkeypatch, texts, record=None):
    def fake(crops, fast_ocr=True):
        if record is not None:
            record.append((list(crops), fast_ocr))
        return [texts for _ in crops]

    monkeypatch.setattr(auto, "ocr_text_groups", fake)


def test_off_text_means_switch_is_off(monkeypatch, env):
    record = []
    _stub_ocr(monkeypatch, ["OFF"], record)

    assert Mirror._infinity_mirror_off(Mirror.__new__(Mirror)) is True
    assert record, "应该走一次识别"
    crops, fast = record[0]
    assert fast is True, "必须使用小区域快识别"
    left, top, right, bottom = crops[0]
    assert right - left < 400 and bottom - top < 100, f"只该识别那块小区域，实际 {crops[0]}"


def test_no_off_text_means_switch_available(monkeypatch, env):
    _stub_ocr(monkeypatch, ["ON"])

    assert Mirror._infinity_mirror_off(Mirror.__new__(Mirror)) is False


def test_ocr_exception_is_swallowed(monkeypatch, env):
    def boom(crops, fast_ocr=True):
        raise RuntimeError("onnx 崩了")

    monkeypatch.setattr(auto, "ocr_text_groups", boom)

    assert Mirror._infinity_mirror_off(Mirror.__new__(Mirror)) is False


def test_missing_bbox_template_returns_false(monkeypatch, env):
    from utils.image_utils import ImageUtils

    monkeypatch.setattr(ImageUtils, "get_bbox", staticmethod(lambda _img: None))

    assert Mirror._infinity_mirror_off(Mirror.__new__(Mirror)) is False
