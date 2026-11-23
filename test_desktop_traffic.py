"""Qt/web parity for independent mixed-vehicle traffic profiles."""

import json
from copy import deepcopy
from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtWidgets import QFileDialog, QMessageBox, QDialog

from desktop_traffic import TrafficDialog
from persistence import save_model, model_document
from scene3d import Scene3D
from test_gui import app as app, window as window
from test_scene3d import NoRenderPlotter
from test_traffic import profile
from traffic import positioned_vehicles, preset_vehicle
from web.workspace import Workspace


@pytest.mark.parametrize("count", [1, 2, 3])
def test_identical_desktop_web_current_position_response(window, count):
    desktop = window
    vehicles = profile(count)["vehicles"]
    desktop.configure_traffic(vehicles)
    desktop.moving_toggle.setChecked(True)
    web = Workspace()
    web.configure_traffic(True, vehicles, 0.5)
    assert desktop.axles() == web.axles
    for fraction in (0, 0.125, 0.5, 0.9, 1):
        desktop.vehicle_position.setValue(round(fraction * 1000))
        desktop.analyze()
        web.set_position(fraction)
        assert desktop.front_position() == pytest.approx(web.position, abs=1e-12)
        for key in ("U", "R", "F", "forces", "stresses"):
            np.testing.assert_allclose(
                desktop.model.results[key], web.model.results[key], rtol=1e-10, atol=1e-7
            )
    assert not desktop.vehicle_nodal_loads()
    assert not desktop.test_errors


def test_count_control_uses_distinct_presets_and_static_loads_once(window):
    window.vehicle_count.setValue(3)
    window.moving_toggle.setChecked(True)
    window.vehicle_position.setValue(481)
    assert window.scenario()["vehicles"] == profile()["vehicles"]
    assert len(window.axles()) == 6
    assert sum(force for _, force in window.axles()) == 355000
    assert -sum(fy for _, fy in window.vehicle_nodal_loads().values()) == pytest.approx(355000)
    assert sum(window.model.results["R"][1::2]) == pytest.approx(555000)
    assert [item["front_offset_m"] for item in window.traffic_vehicles()] == [0, 7, 12.7]
    assert not window.test_errors


def test_custom_profile_envelope_and_studies_match_web(window):
    from bridge_model import Member

    window.model.members.append(Member(1, 7))
    window.analyze()
    vehicles = profile()["vehicles"]
    vehicles[1].update(front_N=9000, spacing_m=3.3, gap_m=5.5)
    window.configure_traffic(vehicles)
    window.moving_toggle.setChecked(True)
    window.vehicle_position.setValue(500)
    web = Workspace()
    web.model = deepcopy(window.model)
    web.configure_traffic(True, vehicles, 0.5)
    web.set_position(0.5)
    window.scan_envelope()
    expected = web.compute_envelopes()
    for key in ("forces", "stresses", "U", "R"):
        for bound in ("min", "max", "x_min", "x_max"):
            np.testing.assert_allclose(window.envelopes[key][bound], expected[key][bound])
    panel = window.redundancy_panel
    panel.member.setValue(18)
    panel.factors.setEditText("1,0")
    panel.run()
    assert window.redundancy["cases"] == web.study_member(18, [1, 0])["cases"]
    window.study_heights.setEditText("4")
    window.study_chords.setEditText("1")
    window.study_webs.setEditText("1")
    window.run_study()
    expected_study = web.explore([4], [1], [1], 50, 150, 7850)
    assert window.study["candidates"] == expected_study["candidates"]
    expected_comparison = web.compare()
    for index, row in enumerate(expected_comparison):
        assert float(window.comparison.item(index, 1).text()) == pytest.approx(
            row["vertical_deflection_m"] * 1000, abs=0.001
        )
    assert not window.test_errors


def test_round_trip_from_web_to_desktop_and_back(window, monkeypatch, tmp_path):
    web = Workspace()
    vehicles = profile()["vehicles"]
    vehicles[2].update(front_N=60000, gap_m=4.5)
    web.configure_traffic(True, vehicles, 0.5)
    web.set_position(0.4)
    source = tmp_path / "web-traffic.json"
    source.write_bytes(web.model_json())
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    assert window.load_project(source)
    assert window.scenario() == web.scenario
    np.testing.assert_allclose(window.model.results["U"], web.model.results["U"])
    target = tmp_path / "desktop-traffic.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(target), ""))
    window.save_project()
    assert json.loads(target.read_text())["schema_version"] == 2
    reopened = Workspace()
    reopened.load_json(target.read_bytes())
    reopened.analyze()
    assert reopened.scenario == window.scenario()
    np.testing.assert_allclose(reopened.model.results["forces"], window.model.results["forces"])
    assert window.load_project(Path(__file__).parent / "examples/pratt_vehicle.json")
    assert window.vehicle_count.value() == 1
    assert "vehicles" not in window.scenario()
    assert window.axle_spacing.minimum() == 0
    assert not window.test_errors


def test_traffic_precision_and_invalid_settings_do_not_replace_state(window, tmp_path):
    before = window.scenario()
    state = profile()
    state["vehicles"][2]["gap_m"] = 3.001
    path = tmp_path / "fine-precision.json"
    save_model(path, window.model, state)
    assert not window.load_project(path)
    assert window.scenario() == before
    assert len(window.test_errors) == 1
    state = profile()
    state["vehicles"][1]["gap_m"] = 1
    with pytest.raises(ValueError):
        window.configure_traffic(state["vehicles"])
    assert window.scenario() == before


def test_selected_vehicle_axle_changes_and_undo_are_independent(window, monkeypatch):
    window.configure_traffic(profile()["vehicles"])
    window.moving_toggle.setChecked(True)
    before = window.scenario()
    window.change_axle_3d(3, 11, 3.5)
    actual = window.scenario()["vehicles"]
    assert actual[1]["rear_N"] == 11000 and actual[1]["spacing_m"] == 3.5
    assert actual[0] == before["vehicles"][0]
    assert actual[2] == before["vehicles"][2]
    window.undo_3d_edit()
    assert window.scenario() == before
    window.select_3d(("axle", 5))
    assert "Vehicle 3 (Bus)" in window.selection3d.text()
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    window.remove_selected_3d()
    assert window.scenario()["vehicles"][2]["rear_N"] == 0
    assert window.scenario()["vehicles"][2]["spacing_m"] == 6
    assert window.scenario()["vehicles"][1] == before["vehicles"][1]
    window.undo_3d_edit()
    assert window.scenario() == before
    assert not window.test_errors


def test_traffic_changes_clear_playback_and_stale_results(window, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    window.configure_traffic(profile()["vehicles"])
    window.play_pause()
    assert window.play_timer.isActive() and window.displacement_history
    vehicles = window.scenario()["vehicles"]
    vehicles[2]["front_N"] += 1000
    window.configure_traffic(vehicles)
    assert not window.play_timer.isActive()
    assert not window.displacement_history
    assert window.envelopes is None and window.redundancy is None
    window.vehicle_position.setValue(999)
    window.play_pause()
    clock[0] += 100
    window.animate_vehicle()
    assert not window.play_timer.isActive()
    assert window.vehicle_position.value() == 1000
    assert window.front_position() == pytest.approx(44.7)
    assert not window.vehicle_nodal_loads()
    assert not window.test_errors


def test_desktop_editor_drafts_presets_apply_and_cancel(window, monkeypatch):
    before = window.scenario()
    dialog = TrafficDialog(window.traffic_vehicles(), window)
    dialog.count.setValue(3)
    assert window.scenario() == before
    dialog.rows[1]["kind"].setCurrentText("Bus")
    assert dialog.rows[1]["front"].value() == 8
    dialog.rows[1]["preset"].click()
    assert dialog.rows[1]["front"].value() == 50
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    assert window.scenario() == before
    monkeypatch.setattr(TrafficDialog, "exec", lambda self: QDialog.Rejected)
    window.edit_traffic()
    assert window.scenario() == before
    window.configure_traffic(dialog.vehicles)
    assert [vehicle["kind"] for vehicle in window.traffic_vehicles()] == ["Truck", "Bus", "Bus"]
    assert window.scenario()["vehicles"][1]["front_N"] == 50000
    assert not window.test_errors


def test_scene_uses_per_vehicle_geometry_wheelbases_and_axle_picking(window):
    window.configure_traffic(profile()["vehicles"])
    window.moving_toggle.setChecked(True)
    window.vehicle_position.setValue(481)
    selected = []
    scene = Scene3D(NoRenderPlotter(), pv, selected.append)
    visual = window.vehicle_visual()
    scene.render(window.model, vehicle=visual)
    assert scene._vehicle_types == ["Truck", "Car", "Bus"]
    front = visual[0]
    specs = positioned_vehicles(window.scenario())
    expected_x = [
        front - vehicle["front_offset_m"] - offset
        for vehicle in specs
        for offset in (0, vehicle["spacing_m"])
    ]
    assert [actor.position[0] for actor in scene._vehicle_arrows] == pytest.approx(expected_x)
    for index, actor in enumerate(scene._vehicle_arrows):
        scene._picked(actor)
        assert selected[-1] == ("axle", index)
    generation = scene.generation
    window.vehicle_position.setValue(490)
    scene.render(window.model, vehicle=window.vehicle_visual())
    assert scene.generation == generation
    assert len(scene._vehicle_arrows) == 6
    assert model_document(window.model)["members"]


def test_single_car_profile_and_invalid_count_transition_preserve_legacy(window):
    car = preset_vehicle("Car")
    window.configure_traffic([car])
    window.moving_toggle.setChecked(True)
    web = Workspace()
    web.configure_traffic(True, [car], 0.5)
    web.set_position(0.5)
    window.vehicle_position.setValue(500)
    assert window.scenario()["vehicles"] == [car]
    assert window.front_position() == pytest.approx(web.position)
    np.testing.assert_allclose(window.model.results["U"], web.model.results["U"])
    window.configure_traffic([preset_vehicle("Truck")])
    assert "vehicles" not in window.scenario()
    window.axle_spacing.setValue(0)
    original = window.scenario()
    window.vehicle_count.setValue(3)
    assert window.vehicle_count.value() == 1
    assert window.scenario() == original
    assert len(window.test_errors) == 1


def test_normalize_inherited_graphics_override(monkeypatch):
    import main

    monkeypatch.setattr(main, "HAS_3D", True)
    monkeypatch.setenv("QT_XCB_GL_INTEGRATION", "none")
    main.configure_graphics()
    assert "QT_XCB_GL_INTEGRATION" not in main.os.environ
    monkeypatch.setenv("QT_XCB_GL_INTEGRATION", "xcb_egl")
    main.configure_graphics()
    assert main.os.environ["QT_XCB_GL_INTEGRATION"] == "xcb_egl"
