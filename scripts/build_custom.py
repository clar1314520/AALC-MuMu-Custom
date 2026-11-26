"""本地定制版打包脚本（不参与官方更新流程）

用法：
    uv run --no-sync python scripts/build_custom.py                # 完整构建
    uv run --no-sync python scripts/build_custom.py --post-only    # 复用已有 dist/AALC
    uv run --no-sync python scripts/build_custom.py --version 1.6.3
    uv run --no-sync python scripts/build_custom.py --sync-config  # 用源码目录的配置覆盖产物

与官方 scripts/build.py 的差异：
1. 不压缩 7z，直接产出可运行的 dist/AALC 目录；
2. 不构建 AALC Updater.exe —— 避免误点「检查更新」把定制版覆盖掉，更新请走 git 重新打包；
3. 只从源码目录向产物目录单向复制，绝不回写或删除源码目录的 config.yaml / assets。
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
APP_DIR = DIST / "AALC"

# 官方 build.py 里裁剪的冗余文件，路径相对 dist/AALC/_internal
REDUNDANT_FILES = [
    "PySide6/translations",
    "PySide6/Qt6Qml.dll",
    "PySide6/Qt6Quick.dll",
    "PySide6/Qt6QmlModels.dll",
    "PySide6/Qt6QmlWorkerScript.dll",
    "PySide6/Qt6QmlMeta.dll",
    "PySide6/Qt6OpenGL.dll",
    "PySide6/opengl32sw.dll",
    "PySide6/Qt6Pdf.dll",
    "PySide6/Qt6Network.dll",
    "PySide6/QtNetwork.pyd",
    "rapidocr/models/ch_PP-OCRv5_rec_mobile_infer.onnx",
    "rapidocr/models/ch_PP-OCRv5_mobile_det.onnx",
    "cv2/opencv_videoio_ffmpeg4110_64.dll",
]

# 运行时文件：只在产物目录里不存在时复制，避免覆盖你在产物里改过的配置
RUNTIME_FILES = ("config.yaml", "theme_pack_list.yaml")
RUNTIME_DIRS = ("theme_pack_weight", "config_backup")


def default_version() -> str:
    """取最近的上游 tag 作为版本号，取不到就退回 dev。"""
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip().lstrip("Vv") or "dev"
    except Exception:
        return "dev"


def run_pyinstaller() -> None:
    from PyInstaller.__main__ import run

    shutil.rmtree(DIST, ignore_errors=True)
    run(["main.spec", "--noconfirm"])


def lrelease_exe() -> str:
    bundled = Path(sys.executable).with_name("pyside6-lrelease.exe")
    if bundled.exists():
        return str(bundled)
    found = shutil.which("pyside6-lrelease")
    if not found:
        raise SystemExit("未找到 pyside6-lrelease，请确认 PySide6 已正确安装")
    return found


def copy_payload(version: str) -> None:
    for name in ("README.md", "LICENSE"):
        if (ROOT / name).exists():
            shutil.copy(ROOT / name, APP_DIR / name)

    shutil.copytree(ROOT / "assets", APP_DIR / "assets", dirs_exist_ok=True)

    i18n_dir = APP_DIR / "i18n"
    i18n_dir.mkdir(parents=True, exist_ok=True)
    for ts_file in sorted((ROOT / "i18n").glob("*.ts")):
        target = i18n_dir / f"{ts_file.stem}.qm"
        subprocess.run([lrelease_exe(), str(ts_file), "-qm", str(target)], check=True)
        print(f"生成翻译文件: {target.relative_to(ROOT)}")

    (APP_DIR / "assets" / "config").mkdir(parents=True, exist_ok=True)
    (APP_DIR / "assets" / "config" / "version.txt").write_text(version, encoding="utf-8")
    print(f"版本号: {version}")


def copy_runtime_state(sync_config: bool) -> None:
    for name in RUNTIME_FILES:
        source = ROOT / name
        if not source.exists():
            continue
        target = APP_DIR / name
        if target.exists() and not sync_config:
            print(f"保留产物里已有的 {name}（加 --sync-config 可覆盖）")
            continue
        shutil.copy2(source, target)
        print(f"复制运行时文件: {name}")

    for name in RUNTIME_DIRS:
        source = ROOT / name
        if source.is_dir():
            shutil.copytree(source, APP_DIR / name, dirs_exist_ok=True)
            print(f"复制运行时目录: {name}")


def trim_redundant() -> None:
    internal = APP_DIR / "_internal"
    for rel_path in REDUNDANT_FILES:
        path = internal / rel_path
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.is_file():
            path.unlink()
        else:
            print(f"警告: 未找到 {path.relative_to(ROOT)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="构建本地定制版 AALC")
    parser.add_argument("--version", default=None, help="写入 assets/config/version.txt 的版本号")
    parser.add_argument("--post-only", action="store_true", help="跳过 PyInstaller，只做产物后处理")
    parser.add_argument("--sync-config", action="store_true", help="用源码目录的配置覆盖产物里的配置")
    args = parser.parse_args()

    version = args.version or default_version()
    if not args.post_only:
        run_pyinstaller()
    elif not APP_DIR.exists():
        raise SystemExit(f"未找到 {APP_DIR}，请先执行完整构建")

    copy_payload(version)
    copy_runtime_state(args.sync_config)
    trim_redundant()

    exe = APP_DIR / "AALC.exe"
    if not exe.exists():
        raise SystemExit("构建结束但未找到 AALC.exe，请检查 PyInstaller 输出")
    print(f"构建完成: {exe}")


if __name__ == "__main__":
    main()
