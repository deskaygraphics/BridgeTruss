"""Exercise application startup in fresh processes, including cloud hot updates."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("stale_traffic", [False, True])
def test_app_startup_refreshes_dependencies(stale_traffic):
    pytest.importorskip("streamlit")
    pytest.importorskip("plotly")
    script = """
import sys
from streamlit.testing.v1 import AppTest

if sys.argv[1] == "stale":
    import traffic
    del traffic.validate_control_precision
    traffic._bridge_loaded_stamp = -1

app = AppTest.from_file("web/app.py", default_timeout=30).run()
assert not app.exception, [error.message for error in app.exception]
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, "stale" if stale_traffic else "fresh"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
