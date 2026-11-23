"""Validate the standalone launcher's CLI and installation checks."""

import json
import os
import subprocess
import sys
from pathlib import Path

from app_version import VERSION


ROOT = Path(__file__).resolve().parent
LAUNCHER = ROOT / "packaging" / "desktop_launcher.py"


def test_launcher_version_from_unrelated_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", str(LAUNCHER), "--version"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == f"BridgeTruss {VERSION}"


def test_launcher_smoke_test_from_unrelated_directory(tmp_path):
    result = subprocess.run(
        [sys.executable, "-B", str(LAUNCHER), "--smoke-test"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert report["version"] == VERSION
    for key in ("icon", "project_round_trip", "examples"):
        assert report[key] == "ok"
