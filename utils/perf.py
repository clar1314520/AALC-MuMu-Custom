"""按阶段累计耗时，用于定位镜牢里"卡一下"的具体来源。

截图受 screenshot_interval 节流、模板匹配是纯 CPU、OCR 又是另一个量级，
只看总耗时无法判断瓶颈在哪。各阶段把耗时写进同一个计数器，页面处理完输出一次
分布即可：

    选卡包页 耗时分布: 截图 1.70s/2次 · 匹配 0.42s/13次 · OCR 0.70s/1次 · 合计 2.82s

计数器是全局单例，用 report_and_reset() 取走并清零，避免跨页面串味。
"""

from __future__ import annotations

import time
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

STAGE_SCREENSHOT = "截图"
STAGE_MATCH = "匹配"
STAGE_OCR = "OCR"


class StageTimer:
    """按阶段累计耗时（秒）与调用次数。"""

    def __init__(self) -> None:
        self._elapsed: dict[str, float] = defaultdict(float)
        self._counts: dict[str, int] = defaultdict(int)

    def add(self, stage: str, seconds: float, count: int = 1) -> None:
        self._elapsed[stage] += seconds
        self._counts[stage] += count

    @contextmanager
    def track(self, stage: str) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.add(stage, time.perf_counter() - start)

    def reset(self) -> None:
        self._elapsed.clear()
        self._counts.clear()

    def total(self) -> float:
        return sum(self._elapsed.values())

    def format(self, title: str) -> str:
        parts = [
            f"{stage} {self._elapsed[stage]:.2f}s/{self._counts[stage]}次"
            for stage in sorted(self._elapsed, key=lambda name: -self._elapsed[name])
        ]
        detail = " · ".join(parts) if parts else "无采样"
        return f"{title} 耗时分布: {detail} · 合计 {self.total():.2f}s"

    def report_and_reset(self, title: str) -> str:
        message = self.format(title)
        self.reset()
        return message


perf = StageTimer()
