import csv

import numpy as np
import pytest

from moving_loads import travel_limits
from test_gui import app as app, window as window
from PySide6.QtWidgets import QFileDialog, QMessageBox


def test_timestamps_match_solved_displacements_and_not_visual_frames(window, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    window.play_pause()
    count = len(window.model.nodes)
    assert len(window.displacement_history) == count
    assert window._result_time == 0.0
    clock[0] += 0.065
    window.animate_vehicle()
    assert window._playback_time == pytest.approx(0.065)
    assert window._result_time == 0.0
    assert len(window.displacement_history) == count
    clock[0] = 100.2
    window.animate_vehicle()
    assert window._playback_time == pytest.approx(0.2)
    assert window._result_time == pytest.approx(0.13)
    assert "0.200 s" in window.playback_label.text()
    assert "0.130 s" in window.displacement_time_label.text()
    assert len(window.displacement_history) == 2 * count
    for index, sample in enumerate(window.displacement_history[-count:]):
        timestamp, position, nid, ux, uy = sample
        assert timestamp == pytest.approx(0.13)
        assert position == window.front_position()
        assert nid == window.model.results["ids"][index]
        np.testing.assert_allclose(
            [ux, uy], window.model.results["U"][2 * index : 2 * index + 2] * 1000
        )
    assert window.history_table.rowCount() == 2 * count
    assert not window.test_errors


def test_pause_resume_excludes_pause_and_reset_clears_history(window, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    window.play_pause()
    clock[0] = 100.2
    window.animate_vehicle()
    window.play_pause()
    assert not window.play_timer.isActive()
    assert window._result_time == pytest.approx(0.2)
    paused_rows = len(window.displacement_history)
    clock[0] = 200.0
    window.play_pause()
    assert len(window.displacement_history) == paused_rows
    clock[0] = 200.14
    window.animate_vehicle()
    assert window._playback_time == pytest.approx(0.34)
    assert window._result_time == pytest.approx(0.33)
    times = [sample[0] for sample in window.displacement_history]
    assert times == sorted(times)
    window.reset_vehicle()
    assert not window.displacement_history
    assert window.history_table.rowCount() == 0
    assert window._playback_time == 0.0
    assert window._result_time is None
    assert window.vehicle_position.value() == 0


@pytest.mark.parametrize("change", ["slider", "step", "load", "model", "invalid", "disable"])
def test_input_changes_invalidate_history(window, monkeypatch, change):
    monkeypatch.setattr("main.time.monotonic", lambda: 100.0)
    window.play_pause()
    assert window.displacement_history
    if change == "slider":
        window.vehicle_position.setValue(300)
    elif change == "step":
        window.vehicle_step.setValue(0.75)
    elif change == "load":
        window.axle_front.setValue(90)
    elif change == "disable":
        window.moving_toggle.setChecked(False)
    else:
        window.model.members[0].A = 0 if change == "invalid" else 0.01
        window.analyze()
    assert not window.play_timer.isActive()
    assert not window.displacement_history
    assert window._result_time is None


def test_completion_caps_timestamp_at_end_of_passage(window, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    window.moving_toggle.setChecked(True)
    window.vehicle_position.setValue(990)
    window.play_pause()
    lo, hi = travel_limits(window.model, window.axles())
    duration = 0.01 * (hi - lo) / window.vehicle_step.value() * 0.13
    clock[0] += 100
    window.animate_vehicle()
    assert not window.play_timer.isActive()
    assert window.vehicle_position.value() == 1000
    assert window._result_time == pytest.approx(duration)
    assert window._playback_time == pytest.approx(duration)
    assert window.displacement_history[-1][0] == pytest.approx(duration)


def test_export_history_preserves_values(window, monkeypatch, tmp_path):
    monkeypatch.setattr("main.time.monotonic", lambda: 100.0)
    window.play_pause()
    window.stop_vehicle()
    path = tmp_path / "history.csv"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), "CSV"))
    window.export_displacement_history()
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == len(window.displacement_history)
    for row, sample in zip(rows, window.displacement_history):
        np.testing.assert_allclose(
            [float(row[key]) for key in ("playback_time_s", "front_x_m", "node", "ux_mm", "uy_mm")],
            sample,
        )
    assert not window.test_errors


def test_new_project_clears_history(window, monkeypatch):
    monkeypatch.setattr("main.time.monotonic", lambda: 100.0)
    window.play_pause()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.new_project()
    assert not window.displacement_history
    assert "Static" in window.displacement_time_label.text()
