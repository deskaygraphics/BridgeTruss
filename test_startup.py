"""Startup configuration and terminal shutdown checks without VTK rendering."""

import os
from pathlib import Path
import subprocess
import sys

import pytest

import main


@pytest.mark.parametrize(
    "enabled,integration,expected",
    [
        (True, "none", None),
        (True, "xcb_egl", "xcb_egl"),
        (True, None, None),
        (False, "none", "none"),
    ],
)
def test_graphics_configuration(monkeypatch, enabled, integration, expected):
    monkeypatch.setattr(main, "HAS_3D", enabled)
    if integration is None:
        monkeypatch.delenv("QT_XCB_GL_INTEGRATION", raising=False)
    else:
        monkeypatch.setenv("QT_XCB_GL_INTEGRATION", integration)
    main.configure_graphics()
    assert os.environ.get("QT_XCB_GL_INTEGRATION") == expected


@pytest.mark.parametrize("disabled", ["0", "1"])
def test_ctrl_c_closes_application(disabled):
    code = """
import os
import signal
from PySide6.QtCore import QTimer
import main

original = main.Main
class Window(original):
    def show(self):
        super().show()
        assert self.model.results is not None
        QTimer.singleShot(100, lambda: os.kill(os.getpid(), signal.SIGINT))
main.Main = Window
previous = signal.getsignal(signal.SIGINT)
assert main.main() == 0
assert signal.getsignal(signal.SIGINT) == previous
print("CLEAN_SHUTDOWN")
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).parent,
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "BRIDGETRUSS_NO_3D": disabled},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "CLEAN_SHUTDOWN" in result.stdout
