"""批量 OCR 分组与关键词匹配的测试。

选卡包原先每张卡各自 OCR 一次（每张 0.8~1s），改成整排一次识别后按坐标归属，
这里用假的 OCR 结果钉住"一次识别 + 按 x 归属"和"多行拼接后再匹配"这两点。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from PIL import Image

from module.automation import TextMatchResult, auto


def fake_ocr_result(items):
    """items: [(text, (cx, cy))] -> 伪造 RapidOCROutput 需要的字段。"""
    txts = [text for text, _ in items]
    boxes = []
    for _, (cx, cy) in items:
        boxes.append([[cx - 5, cy - 5], [cx + 5, cy - 5], [cx + 5, cy + 5], [cx - 5, cy + 5]])
    return SimpleNamespace(txts=txts, boxes=boxes)


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setattr(auto, "screenshot", Image.new("L", (1600, 900), 0), raising=False)
    return None


def test_groups_split_by_card_position(screen, monkeypatch):
    calls = {"count": 0}

    def fake_ocr(image, fast_ocr=False):
        calls["count"] += 1
        # 坐标是"并集裁剪图"内的局部坐标；并集从 (400,500) 开始
        return fake_ocr_result(
            [
                ("The Outcast", (100, 60)),
                ("The Unloving", (400, 60)),
                ("Clear Bonus", (20, 200)),
            ]
        )

    monkeypatch.setattr(auto, "_timed_ocr", fake_ocr)
    crops = [(400, 500, 700, 800), (700, 500, 1000, 800)]

    groups = auto.ocr_text_groups(crops)

    assert calls["count"] == 1, "两张卡只允许识别一次"
    assert groups[0] == ["The Outcast", "Clear Bonus"]
    assert groups[1] == ["The Unloving"]


def test_groups_handle_empty_result(screen, monkeypatch):
    monkeypatch.setattr(auto, "_timed_ocr", lambda image, fast_ocr=False: SimpleNamespace(txts=None, boxes=None))
    assert auto.ocr_text_groups([(0, 0, 100, 100)]) == [[]]


def test_empty_crops_do_not_call_ocr(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("没有裁剪区域时不应触发 OCR")

    monkeypatch.setattr(auto, "_timed_ocr", fail)
    assert auto.ocr_text_groups([]) == []


def test_match_language_text_joins_multiline_name(screen, monkeypatch):
    """卡包名被 OCR 拆成两行时，长关键词仍要能命中。"""
    monkeypatch.setattr(auto, "clear_img_cache", lambda: None)
    from utils.path_manager import path_manager

    monkeypatch.setattr(path_manager, "current_language", "en")

    keywords = {"nest, workshop, and technology": 3}
    result = auto.match_language_text(keywords, keywords, ["Nest, Workshop, and", "Technology"])

    assert isinstance(result, TextMatchResult)
    assert result.value == 3


def test_match_language_text_returns_false_without_text(screen):
    assert auto.match_language_text({"a": 1}, {"a": 1}, []) is False
