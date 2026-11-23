"""Offscreen integration checks; intentionally do not test VTK/OpenGL rendering."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["BRIDGETRUSS_NO_3D"] = "1"
import numpy as np
import pytest
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from main import Main
from persistence import save_model
from editing import member_edit, load_edit
from moving_loads import combined_loads
from PySide6.QtWidgets import QDialog, QComboBox, QDoubleSpinBox, QPushButton


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(app, monkeypatch):
    errors = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: errors.append(args[-1]))
    instance = Main()
    instance.test_errors = errors
    yield instance
    instance.stop_vehicle()
    instance.close()
    app.processEvents()


def test_traffic_project_requires_confirmation_then_loads_on_desktop(window, monkeypatch, tmp_path):
    from traffic import preset_vehicle

    w = window
    original_model = w.model
    original_scenario = w.scenario()
    path = tmp_path / "traffic.json"
    save_model(
        path,
        w.model,
        {
            "enabled": True,
            "position_fraction": 0.5,
            "vehicles": [preset_vehicle("Truck"), preset_vehicle("Car", 3)],
        },
    )
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    questions = []
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args: questions.append(args) or QMessageBox.No
    )
    w.open_project()
    assert w.model is original_model
    assert w.scenario() == original_scenario
    assert len(questions) == 1
    assert not w.test_errors
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.open_project()
    assert w.model is not original_model
    assert [vehicle["kind"] for vehicle in w.traffic_vehicles()] == ["Truck", "Car"]
    assert len(w.axles()) == 4
    assert w.model.results is not None
    assert not w.test_errors


def test_analysis_tabs_and_failure_invalidation(window):
    w = window
    assert w.model.results is not None
    assert w.members_table.rowCount() == 17
    w.compute_influence()
    assert w.influence_selector.count() > 17
    w.influence_selector.setCurrentIndex(18)
    w.scan_envelope()
    assert w.envelope_table.rowCount() == 74
    w.run_study()
    assert w.study_table.rowCount() == 27
    assert not w.test_errors
    w.model.members[0].A = 0
    w.analyze()
    assert w.model.results is None
    assert w.members_table.rowCount() == 0
    assert w.envelope_table.rowCount() == 0
    assert w.study is None
    assert len(w.test_errors) == 1


def test_moving_load_help_is_read_only_and_reusable(window):
    w = window
    before_model = w.model.to_solver()
    before_scenario = w.scenario()
    before_results = w.model.results
    w.moving_help_button.click()
    dialog = w._moving_help_dialog
    assert dialog.isVisible()
    assert not dialog.isModal()
    assert w.moving_help_text.isReadOnly()
    text = w.moving_help_text.toPlainText()
    for phrase in (
        "Select Deck Nodes",
        "Clear Static Loads",
        "80 kN",
        "120 kN",
        "4 m",
        "Enable moving loads",
        "Play",
        "Reset",
        "Compute Signed Envelopes",
        "quasi-static",
        "not a dynamic simulation",
    ):
        assert phrase in text
    dialog.close()
    w.moving_help_button.click()
    assert w._moving_help_dialog is dialog
    assert dialog.isVisible()
    dialog.close()
    assert w.model.to_solver() == before_model
    assert w.scenario() == before_scenario
    assert w.model.results is before_results
    assert not w.play_timer.isActive()
    assert not w.test_errors


def test_moving_load_setup_tooltips(window):
    w = window
    for widget in (
        w.moving_help_button,
        w.moving_toggle,
        w.axle_front,
        w.axle_rear,
        w.axle_spacing,
        w.vehicle_step,
        w.vehicle_position,
        w.play_button,
        w.envelope_button,
    ):
        assert widget.toolTip()
    assert "downward" in w.axle_front.toolTip()
    assert "not vehicle speed" in w.vehicle_step.toolTip()
    assert "including static loads" in w.envelope_button.toolTip()
    buttons = {button.text(): button for button in w.findChildren(QPushButton)}
    for label in ("Select Deck Nodes", "Clear Static Loads", "Reset"):
        assert buttons[label].toolTip()


def test_interpolated_playback_and_pause_sync(window, monkeypatch):
    w = window
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    w.play_pause()
    assert w.play_timer.isActive()
    assert w.play_timer.interval() == 33
    clock[0] = 100.065
    w.animate_vehicle()
    assert w._visual_fraction > w.vehicle_position.value() / 1000
    assert "tables:" in w.position_label.text()
    visible = w._visual_fraction
    w.stop_vehicle()
    assert w._visual_fraction is None
    assert w.vehicle_position.value() == round(visible * 1000)
    paused = w.model.results["U"].copy()
    direct = w.model.solve(combined_loads(w.model, w.front_position(), w.axles()))
    np.testing.assert_allclose(paused, direct["U"])
    assert not w.test_errors


def test_moving_response_cache_invalidates_on_edits(window):
    w = window
    w.moving_toggle.setChecked(True)
    initial = w._moving_response
    w.vehicle_position.setValue(500)
    assert w._moving_response is initial
    w.axle_front.setValue(100)
    assert w._moving_response is initial  # Unit responses do not depend on axle weight.
    w.model.members[0].A *= 2
    w.analyze()
    assert w._moving_response is not initial
    changed = w._moving_response
    w.model.loads[6] = (0.0, -100000.0)
    w.analyze()
    assert w._moving_response is not changed
    assert not w.test_errors


def test_animation_end_and_visual_options(window, monkeypatch):
    w = window
    monkeypatch.setattr("main.time.monotonic", lambda: 100.0)
    w.moving_toggle.setChecked(True)
    w.vehicle_position.setValue(999)
    w.play_pause()
    monkeypatch.setattr("main.time.monotonic", lambda: 101.0)
    w.animate_vehicle()
    assert w.vehicle_position.value() == 1000
    assert not w.play_timer.isActive()
    assert w._visual_fraction is None
    for control in (w.show_deck3d, w.show_vehicle3d, w.show_loads3d):
        control.setChecked(False)
    assert w.camera3d.count() == 4
    assert "Steel" in [w.color.itemText(i) for i in range(w.color.count())]
    assert not w.test_errors


def test_full_exit_playback_and_comparison_preserves_result(window):
    w = window
    w.moving_toggle.setChecked(True)
    w.vehicle_position.setValue(500)
    active = w.model.results["U"].copy()
    w._comparison_key = None
    w.populate_comparison()
    np.testing.assert_allclose(w.model.results["U"], active)
    w.vehicle_position.setValue(999)
    w.advance_vehicle()
    assert w.vehicle_position.value() == 1000
    assert w.front_position() > 29
    assert w.vehicle_nodal_loads() == {}
    assert not w.play_timer.isActive()
    w.scan_envelope()
    w.axle_front.setValue(90)
    assert w.envelopes is None
    assert not w.test_errors


@pytest.mark.parametrize(
    "key,value", [("front_N", 1.0), ("spacing_m", 0.001), ("position_fraction", 0.5004)]
)
def test_open_rejects_unrepresentable_scenario_before_replacing(
    window, monkeypatch, tmp_path, key, value
):
    w = window
    original = w.model
    previous = w.scenario()
    state = {
        "enabled": True,
        "front_N": 80000,
        "rear_N": 120000,
        "spacing_m": 4,
        "position_fraction": 0.5,
    }
    state[key] = value
    path = tmp_path / "fine_precision.json"
    save_model(path, w.model, state)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    w.open_project()
    assert w.model is original
    assert w.scenario() == previous
    assert len(w.test_errors) == 1
    assert "precision" in w.test_errors[0] or "increments" in w.test_errors[0]


def test_load_and_export_workflow(window, monkeypatch, tmp_path):
    w = window
    path = tmp_path / "model.json"
    state = {
        "enabled": True,
        "front_N": 100000,
        "rear_N": 150000,
        "spacing_m": 5,
        "position_fraction": 0.5,
    }
    save_model(path, w.model, state)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.open_project()
    assert w.axle_front.value() == 100
    assert w.moving_enabled
    w.scan_envelope()
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args: str(tmp_path))
    w.export_bundle()
    bundles = list(tmp_path.glob("bridge_results_*"))
    assert len(bundles) == 1
    assert (bundles[0] / "envelopes.csv").exists()
    w.new_project()
    assert not w.model.nodes
    assert w.model.results is None
    assert w.envelopes is None
    assert not w.moving_enabled
    assert not w.test_errors


def test_3d_selection_edit_and_undo(window):
    w = window
    w.select_3d(("member", 0))
    assert w.edit3d.isEnabled()
    assert "M1" in w.selection3d.text()
    assert w.apply_3d_edit(lambda: member_edit(w.model, 0, 1, 0.01, 2e11, 0))
    assert w.model.members[0].A == 0.01
    assert w.selected_3d is None
    assert w.undo3d.isEnabled()
    w.undo_3d_edit()
    assert w.model.members[0].A == 0.005
    assert w.kind.currentText() == "Pratt Truss"
    assert not w.undo3d.isEnabled()
    w.select_3d(("node", 1))
    assert not w.remove3d.isEnabled()
    w.select_3d(("load", 6))
    assert w.remove3d.isEnabled()
    w.select_3d(("member", 999))
    assert w.selected_3d is None


def test_3d_member_dialog_reconnect(window, monkeypatch):
    w = window

    def accept(dialog):
        endpoints = dialog.findChildren(QComboBox)
        endpoints[1].setCurrentIndex(endpoints[1].findData(2))
        dialog.findChildren(QDoubleSpinBox)[0].setValue(0.0075)
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    w.select_3d(("member", 0))
    w.edit_selected_3d()
    member = w.model.members[0]
    assert (member.a, member.b, member.A) == (0, 2, 0.0075)
    w.undo_3d_edit()
    assert w.model.members[0].b == 1
    assert w.model.results is not None


def test_3d_load_target_replace_can_cancel(window, monkeypatch):
    w = window

    def accept(dialog):
        combo = dialog.findChildren(QComboBox)[0]
        combo.setCurrentIndex(combo.findData(7))
        dialog.findChildren(QDoubleSpinBox)[1].setValue(-1)
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    w.select_3d(("load", 6))
    w.edit_selected_3d()
    assert w.model.loads[6] == (0, -50000)
    assert w.model.loads[7] == (0, -50000)
    assert w._undo_3d is None


def test_3d_queued_pick_is_discarded_after_scene_changes(window, app):
    class Scene:
        generation = 1

        def highlight(self, *args, **kwargs):
            pass

    w = window
    w.scene3d = Scene()
    w.queue_3d_selection(("member", 0))
    w.scene3d.generation += 1
    app.processEvents()
    assert w.selected_3d is None
    w.queue_3d_selection(("node", 1))
    app.processEvents()
    assert w.selected_3d == ("node", 1)
    w.scene3d = None


def test_3d_remove_unstable_member_and_restore(window, monkeypatch):
    w = window
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.select_3d(("member", 0))
    w.remove_selected_3d()
    assert len(w.model.members) == 16
    assert w.model.results is None
    assert w.undo3d.isEnabled()
    assert w.test_errors
    w.undo_3d_edit()
    assert len(w.model.members) == 17
    assert w.model.results is not None


def test_3d_attach_two_nodes_and_reject_duplicate(window):
    w = window
    w.toggle_attach_3d(True)
    w.select_3d(("member", 0))
    assert w.attach_anchor is None
    w.select_3d(("node", 0))
    w.select_3d(("node", 1))
    assert len(w.model.members) == 17
    assert w.attach_anchor == 0
    assert len(w.test_errors) == 1
    w.select_3d(("node", 2))
    assert len(w.model.members) == 18
    assert not w.attach3d.isChecked()
    w.undo_3d_edit()
    assert len(w.model.members) == 17


def test_3d_remove_load_and_axle_undo(window, monkeypatch):
    w = window
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.select_3d(("load", 6))
    w.remove_selected_3d()
    assert 6 not in w.model.loads
    assert 6 in w.model.nodes
    w.undo_3d_edit()
    assert w.model.loads[6] == (0, -50000)
    w.moving_toggle.setChecked(True)
    w.vehicle_position.setValue(500)
    w.select_3d(("axle", 1))
    w.remove_selected_3d()
    assert w.axle_rear.value() == 0
    w.undo_3d_edit()
    assert w.axle_rear.value() == 120
    assert w.vehicle_position.value() == 500
    assert w.moving_enabled
    assert not w.test_errors


def test_3d_dialog_prefill_cancel_and_reassign(window, monkeypatch):
    w = window

    def cancel(dialog):
        if "member" in dialog.windowTitle():
            assert dialog.findChildren(QDoubleSpinBox)[0].value() == 0.005
        else:
            assert dialog.findChildren(QDoubleSpinBox)[1].value() == -50
        return QDialog.Rejected

    monkeypatch.setattr(QDialog, "exec", cancel)
    w.select_3d(("member", 0))
    w.edit_selected_3d()
    w.select_3d(("load", 6))
    w.edit_selected_3d()
    assert w._undo_3d is None

    def accept(dialog):
        combo = dialog.findChildren(QComboBox)[0]
        combo.setCurrentIndex(combo.findData(1))
        dialog.findChildren(QDoubleSpinBox)[1].setValue(-75)
        return QDialog.Accepted

    monkeypatch.setattr(QDialog, "exec", accept)
    w.edit_selected_3d()
    assert 6 not in w.model.loads
    assert w.model.loads[1] == (0, -75000)
    assert not w.test_errors


def test_3d_cancel_removal_and_invalidate_on_model_change(window, monkeypatch):
    w = window
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.No)
    w.select_3d(("member", 0))
    w.remove_selected_3d()
    assert len(w.model.members) == 17
    assert w._undo_3d is None
    w.apply_3d_edit(lambda: load_edit(w.model, 6, 6, 0, -1000))
    w.kind.setCurrentText("Howe Truss")
    assert w._undo_3d is None
    assert w.selected_3d is None
    assert not w.undo3d.isEnabled()
