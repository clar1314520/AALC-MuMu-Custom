r"""AALC 模板替换小工具（独立运行，不进入主程序、不参与打包）

用途：游戏更新后界面变了，识别模板会失效（例如新版把 Drive 界面的镜牢入口改成
两行字，旧模板相似度只有 0.5）。这个小工具用来从当前游戏画面里重新框选一张图，
按 AALC 的模板规范写回 assets/images。

用法：
    .venv\Scripts\python.exe tools\template_tool.py

规范（工具会自动满足，手动改图时必须遵守）：
1. 模板文件是 2560x1440 的黑底画布，图案留在它在 1440p 下应有的位置；
2. 带 `_assets.png` 后缀的文件会被 get_bbox() 裁出内容再匹配，
   其它 png 是整图直接匹配，两者不能混用；
3. 替换后需要重启 AALC（或让它清图片缓存）才生效。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "assets" / "images"
BACKUP = ROOT / "assets" / "images_backup"

CANVAS = (2560, 1440)  # AALC 的模板统一按 1440 高度绘制
ADB_CANDIDATES = (
    r"E:\MuMu\MuMuPlayer\nx_main\adb.exe",
    r"E:\MuMu\MuMuPlayer-12.0\shell\adb.exe",
    r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
)
ADB_PORT = "127.0.0.1:16384"


def list_templates() -> list[Path]:
    if not IMAGES.is_dir():
        return []
    return sorted(path for path in IMAGES.rglob("*.png") if path.is_file())


def content_size(image_path: Path) -> tuple[int, int]:
    """模板内容的实际尺寸（黑底画布去掉黑边），判断"这个模板到底多大"。"""
    try:
        from PIL import Image

        with Image.open(image_path) as image:
            box = image.convert("RGB").getbbox()
            if not box:
                return (0, 0)
            return (box[2] - box[0], box[3] - box[1])
    except Exception:  # noqa: BLE001 - 单张坏图不该影响列表
        return (0, 0)


def copies_of(relative: str) -> list[Path]:
    """同一个逻辑模板的所有语言/主题副本（zh_cn / en / share / dark ...）。"""
    name = Path(relative).name
    return sorted(path for path in IMAGES.rglob(name) if path.is_file())


def find_adb() -> str | None:
    found = shutil.which("adb")
    if found:
        return found
    for candidate in ADB_CANDIDATES:
        if Path(candidate).is_file():
            return candidate
    return None


def grab_from_emulator():
    """用 adb 抓一帧当前画面，返回 PIL.Image；失败返回 None。"""
    adb = find_adb()
    if adb is None:
        return None
    try:
        from io import BytesIO

        from PIL import Image

        subprocess.run([adb, "connect", ADB_PORT], capture_output=True, timeout=10, check=False)
        result = subprocess.run(
            [adb, "exec-out", "screencap", "-p"], capture_output=True, timeout=20, check=False
        )
        if result.returncode != 0 or not result.stdout:
            return None
        return Image.open(BytesIO(result.stdout)).convert("RGB")
    except Exception:  # noqa: BLE001 - 抓不到就让用户选文件
        return None


def build_template(frame, box: tuple[int, int, int, int]):
    """把框选区域按规范贴到 2560x1440 黑底画布上。"""
    from PIL import Image

    left, top, right, bottom = (int(value) for value in box)
    if right <= left or bottom <= top:
        raise ValueError("框选区域为空")

    ratio = CANVAS[1] / frame.height
    canvas = Image.new("RGB", CANVAS, (0, 0, 0))

    crop = frame.crop((left, top, right, bottom))
    target_size = (max(1, round(crop.width * ratio)), max(1, round(crop.height * ratio)))
    crop = crop.resize(target_size, Image.LANCZOS)
    canvas.paste(crop, (round(left * ratio), round(top * ratio)))
    return canvas


def backup_and_write(target: Path, canvas) -> Path | None:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = None
    if target.is_file():
        relative = target.relative_to(IMAGES)
        backup_path = BACKUP / stamp / relative
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, backup_path)
    canvas.save(target)
    return backup_path


def main() -> int:
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QDialog,
        QFileDialog,
        QHBoxLayout,
        QLabel,
        QListWidget,
        QListWidgetItem,
        QMessageBox,
        QPushButton,
        QRubberBand,
        QScrollArea,
        QVBoxLayout,
        QWidget,
    )

    class SelectDialog(QDialog):
        """在游戏画面上拖一个矩形，返回原始像素坐标。"""

        def __init__(self, image):
            super().__init__()
            from PySide6.QtGui import QImage

            self.setWindowTitle("在画面上框选要替换的图案")
            self.original = image
            self.selection: tuple[int, int, int, int] | None = None
            self.scale = min(1280 / image.width, 800 / image.height, 1.0)

            qimage = QImage(
                image.tobytes(), image.width, image.height, image.width * 3, QImage.Format_RGB888
            )
            self.label = QLabel()
            self.label.setPixmap(
                QPixmap.fromImage(qimage).scaled(
                    int(image.width * self.scale),
                    int(image.height * self.scale),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation,
                )
            )
            self.label.setCursor(Qt.CrossCursor)
            self.label.mousePressEvent = self._press
            self.label.mouseMoveEvent = self._move
            self.label.mouseReleaseEvent = self._release
            self.label.setMinimumSize(
                int(image.width * self.scale), int(image.height * self.scale)
            )

            # 用 QRubberBand 画选框，避免每次鼠标移动都复制整张位图
            self.band = QRubberBand(QRubberBand.Rectangle, self.label)
            self.origin = None

            hint = QLabel("按住鼠标拖动框选图案（只需框住要识别的部分，比旧模板略大一圈更稳）")
            scroll = QScrollArea()
            scroll.setWidget(self.label)
            layout = QVBoxLayout(self)
            layout.addWidget(hint)
            layout.addWidget(scroll)
            buttons = QHBoxLayout()
            ok = QPushButton("使用这个区域")
            cancel = QPushButton("取消")
            ok.clicked.connect(self.accept)
            cancel.clicked.connect(self.reject)
            buttons.addStretch(1)
            buttons.addWidget(ok)
            buttons.addWidget(cancel)
            layout.addLayout(buttons)

        def _native(self, point: QPoint) -> QPoint:
            return QPoint(round(point.x() / self.scale), round(point.y() / self.scale))

        def _press(self, event):
            self.origin = event.position().toPoint()
            self.band.setGeometry(QRect(self.origin, self.origin))
            self.band.show()

        def _move(self, event):
            if self.origin is None:
                return
            self.band.setGeometry(
                QRect(self.origin, event.position().toPoint()).normalized()
            )

        def _release(self, event):
            if self.origin is None:
                return
            rect = QRect(self.origin, event.position().toPoint()).normalized()
            self.origin = None
            self.band.hide()

            top_left = self._native(rect.topLeft())
            bottom_right = self._native(rect.bottomRight())
            left, right = sorted((top_left.x(), bottom_right.x()))
            top, bottom = sorted((top_left.y(), bottom_right.y()))
            if right - left < 4 or bottom - top < 4:
                QMessageBox.warning(self, "区域太小", "框选区域太小了，请重新拖一个范围。")
                return
            self.selection = (left, top, right, bottom)
            self.band.setGeometry(rect)
            self.band.show()

    class ToolWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("AALC 模板替换工具")
            self.resize(980, 640)
            self.frame = None
            self.targets: list[Path] = []

            self.search = QListWidget()
            self.search.setMinimumWidth(520)
            self.search.currentItemChanged.connect(self._on_select)
            self.preview = QLabel("选择左侧模板查看预览")
            self.preview.setAlignment(Qt.AlignCenter)
            self.preview.setMinimumSize(360, 260)
            self.preview.setStyleSheet("border:1px solid #888;")
            self.info = QLabel("")
            self.info.setWordWrap(True)

            self.replace_button = QPushButton("框选替换（从模拟器抓当前画面）")
            self.replace_button.clicked.connect(self.replace_from_emulator)
            self.file_button = QPushButton("从图片文件替换…")
            self.file_button.clicked.connect(self.replace_from_file)
            self.sync_copies = QCheckBox("同时替换其它语言/主题副本")
            self.sync_copies.setChecked(True)

            right = QVBoxLayout()
            right.addWidget(self.preview, 1)
            right.addWidget(self.info)
            right.addWidget(self.replace_button)
            right.addWidget(self.file_button)
            right.addWidget(self.sync_copies)

            layout = QHBoxLayout(self)
            layout.addWidget(self.search, 1)
            layout.addLayout(right, 1)
            self.reload()

        def reload(self):
            self.search.clear()
            for path in list_templates():
                relative = path.relative_to(IMAGES).as_posix()
                width, height = content_size(path)
                item = QListWidgetItem(f"{relative}   [{width}×{height}]")
                item.setData(Qt.UserRole, path)
                self.search.addItem(item)

        def current_path(self) -> Path | None:
            item = self.search.currentItem()
            return item.data(Qt.UserRole) if item else None

        def _on_select(self, current, _previous):
            path = current.data(Qt.UserRole) if current else None
            if path is None:
                return
            width, height = content_size(path)
            copies = copies_of(path.relative_to(IMAGES).as_posix())
            self.info.setText(
                f"内容尺寸 {width}×{height}（1440p 基准）\n"
                f"保存位置 {path.relative_to(ROOT)}\n"
                f"同名副本 {len(copies)} 份：" + "、".join(c.parent.parent.name for c in copies)
            )
            pixmap = QPixmap(str(path))
            if not pixmap.isNull():
                self.preview.setPixmap(
                    pixmap.scaled(self.preview.width(), self.preview.height(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        def replace_from_emulator(self):
            frame = grab_from_emulator()
            if frame is None:
                QMessageBox.warning(
                    self,
                    "抓不到画面",
                    "没有找到 adb 或模拟器未连接。\n可以用「从图片文件替换」手动选择一张截图。",
                )
                return
            self._do_replace(frame)

        def replace_from_file(self):
            path, _ = QFileDialog.getOpenFileName(self, "选择游戏画面截图", str(ROOT), "图片 (*.png *.jpg *.jpeg)")
            if not path:
                return
            from PIL import Image

            self._do_replace(Image.open(path).convert("RGB"))

        def _do_replace(self, frame):
            path = self.current_path()
            if path is None:
                QMessageBox.information(self, "先选模板", "请在左侧列表里选一个要替换的模板。")
                return

            dialog = SelectDialog(frame)
            if dialog.exec() != QDialog.Accepted or dialog.selection is None:
                return

            canvas = build_template(frame, dialog.selection)
            targets = [path]
            if self.sync_copies.isChecked():
                targets = copies_of(path.relative_to(IMAGES).as_posix()) or [path]

            backups = [backup_and_write(target, canvas) for target in targets]
            backup_text = "\n".join(str(b) for b in backups if b)
            QMessageBox.information(
                self,
                "已替换",
                f"已写入 {len(targets)} 个文件。\n"
                + (f"备份在：\n{backup_text}\n" if backup_text else "")
                + "\n请重启 AALC 让新模板生效，然后验证一次对应界面的识别是否正常。",
            )
            self._on_select(self.search.currentItem(), None)

    app = QApplication(sys.argv)
    window = ToolWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
