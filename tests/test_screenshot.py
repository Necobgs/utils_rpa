import sys
import types
from pathlib import Path

import pytest

import utils_rpa.screenshot as sc


class _FakeShot:
    rgb = b"fake-rgb-bytes"
    size = (10, 10)


class _FakeSct:
    monitors = [
        {"left": 0, "top": 0, "width": 200, "height": 100},  # 0 = todos
        {"left": 0, "top": 0, "width": 100, "height": 100},  # 1 = principal
    ]

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def grab(self, region):
        self.grabbed_region = region
        return _FakeShot()


@pytest.fixture
def fake_mss(monkeypatch):
    """Injeta módulos ``mss`` e ``mss.tools`` falsos para evitar display real."""
    captured = {}

    def _to_png(rgb, size, output):
        captured["rgb"] = rgb
        captured["size"] = size
        Path(output).write_bytes(b"\x89PNG-fake")

    tools_mod = types.ModuleType("mss.tools")
    tools_mod.to_png = _to_png

    fake_sct = _FakeSct()

    mss_mod = types.ModuleType("mss")
    mss_mod.mss = lambda: fake_sct
    mss_mod.tools = tools_mod

    monkeypatch.setitem(sys.modules, "mss", mss_mod)
    monkeypatch.setitem(sys.modules, "mss.tools", tools_mod)

    return {"captured": captured, "sct": fake_sct}


def test_capture_screen_uses_output_path(fake_mss, tmp_path):
    destino = tmp_path / "print.png"
    resultado = sc.capture_screen(destino)

    assert resultado == destino
    assert destino.exists()
    assert fake_mss["captured"]["rgb"] == _FakeShot.rgb


def test_capture_screen_all_monitors_by_default(fake_mss, tmp_path):
    sc.capture_screen(tmp_path / "print.png")
    assert fake_mss["sct"].grabbed_region is _FakeSct.monitors[sc.ALL_MONITORS]


def test_capture_screen_specific_monitor(fake_mss, tmp_path):
    sc.capture_screen(tmp_path / "print.png", monitor=1)
    assert fake_mss["sct"].grabbed_region is _FakeSct.monitors[1]


def test_capture_screen_generates_timestamped_name(fake_mss, tmp_path):
    result = sc.capture_screen(output_dir=tmp_path)

    assert result.parent == tmp_path
    assert result.name.startswith("screenshot_")
    assert result.suffix == ".png"
    assert result.exists()


def test_capture_screen_creates_output_dir(fake_mss, tmp_path):
    nested = tmp_path / "a" / "b"
    result = sc.capture_screen(output_dir=nested, file_name="s.png")

    assert result == nested / "s.png"
    assert result.exists()
