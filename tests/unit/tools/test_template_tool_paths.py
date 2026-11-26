"""模板替换工具：打包成 exe 后的目录定位

exe 双击运行时 __file__ 指向 PyInstaller 的解包临时目录，必须按 sys.executable
定位。工具要改的是 AALC 自己的 assets/images，所以定位规则是：
1. 上次选过的目录（记在 exe 旁边的 template_tool.json）；
2. exe 同级 / 上一级 / 上两级，以及这些目录下的常见子目录；
3. 都找不到才提示用户手选。

这里钉住"能找到"和"找不到时不会假装成功"两件事。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tools import template_tool as tool


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    """把配置文件重定向到临时目录，并在用例结束后还原模块级路径。"""
    monkeypatch.setattr(tool, "_config_file", lambda: tmp_path / "template_tool.json")
    original = (tool.ROOT, tool.IMAGES, tool.BACKUP)
    yield
    tool.ROOT, tool.IMAGES, tool.BACKUP = original


def make_aalc(root: Path) -> Path:
    (root / "assets" / "images" / "default" / "share").mkdir(parents=True)
    return root


def test_set_root_rejects_dir_without_images(tmp_path):
    before = tool.IMAGES
    assert tool.set_root(tmp_path) is False
    assert tool.IMAGES == before, "选错目录时不能把工作目录改坏"


def test_set_root_switches_and_persists(tmp_path):
    root = make_aalc(tmp_path / "AALC")

    assert tool.set_root(root) is True
    assert tool.IMAGES == root.resolve() / "assets" / "images"

    tool.save_root(root)
    assert tool._saved_root() == root.resolve()


def test_resolve_root_prefers_saved_dir(tmp_path, monkeypatch):
    saved = make_aalc(tmp_path / "旧版本")
    nearby = make_aalc(tmp_path / "同名新版本")
    tool.save_root(saved)
    monkeypatch.setattr(tool, "app_dir", lambda: nearby)

    assert tool.resolve_root() == saved.resolve()


def test_resolve_root_falls_back_to_parent_of_exe(tmp_path, monkeypatch):
    """exe 放在 工具/ 子目录里，AALC 在它的上一级 —— 最常见的手动放置方式。"""
    aalc = make_aalc(tmp_path / "AALC")
    exe_dir = tmp_path / "工具"
    exe_dir.mkdir()
    monkeypatch.setattr(tool, "app_dir", lambda: exe_dir)

    assert tool.resolve_root() == aalc.resolve()


def test_resolve_root_finds_exe_itself(tmp_path, monkeypatch):
    """exe 直接丢进 AALC 根目录：同级就有 assets/images。"""
    aalc = make_aalc(tmp_path / "AALC")
    monkeypatch.setattr(tool, "app_dir", lambda: aalc)

    assert tool.resolve_root() == aalc.resolve()


def test_resolve_root_ignores_stale_saved_entry(tmp_path, monkeypatch):
    """记着的目录被删/改名后，不能就此报废，要继续往后找。"""
    gone = tmp_path / "已删除"
    tool.save_root(gone)
    aalc = make_aalc(tmp_path / "AALC")
    monkeypatch.setattr(tool, "app_dir", lambda: aalc)

    assert tool.resolve_root() == aalc.resolve()


def test_app_dir_uses_executable_when_frozen(monkeypatch, tmp_path):
    exe = tmp_path / "工具" / "模板替换工具.exe"
    exe.parent.mkdir(parents=True)
    monkeypatch.setattr(tool.sys, "frozen", True, raising=False)
    monkeypatch.setattr(tool.sys, "executable", str(exe))

    assert tool.app_dir() == exe.parent
