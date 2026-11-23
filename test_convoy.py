"""One-to-three-vehicle convoys must match both axle physics and displayed actors."""

import json
from pathlib import Path

import numpy as np
import pyvista as pv
import pytest
from PySide6.QtWidgets import QMessageBox, QFileDialog

from bridge_model import Model
from moving_loads import (
    convoy_axles,
    scenario_axles,
    vehicle_loads,
    combined_loads,
    travel_limits,
    MovingResponse,
    envelope,
)
from persistence import save_model, load_model
from scene3d import Scene3D
from test_scene3d import NoRenderPlotter
from test_gui import app as app, window as window


@pytest.mark.parametrize("count", [1, 2, 3])
def test_convoy_force_moment_and_response(count):
    model = Model()
    axles = convoy_axles(80000, 120000, 4, count, 4)
    assert len(axles) == 2 * count
    front = 22.0
    loads = vehicle_loads(model, front, axles)
    assert -sum(fy for fx, fy in loads.values()) == pytest.approx(count * 200000)
    assert -sum(model.nodes[nid][0] * fy for nid, (fx, fy) in loads.items()) == pytest.approx(
        sum((front - offset) * force for offset, force in axles)
    )
    direct = model.solve(combined_loads(model, front, axles))
    cached = MovingResponse(model).at(front, axles)
    for key in ("U", "R", "forces", "stresses"):
        np.testing.assert_allclose(cached[key], direct[key], rtol=1e-9, atol=1e-7)
    lo, hi = travel_limits(model, axles)
    assert hi == 29 + (count - 1) * 8
    assert all(fy == 0 for fx, fy in vehicle_loads(model, lo - 1e-6, axles).values())
    assert not vehicle_loads(model, hi + 1e-6, axles)


@pytest.mark.parametrize(
    "count,gap",
    [(0, 4), (4, 4), (True, 4), (1.5, 4), (3, -1), (2, float("nan")), (2, float("inf"))],
)
def test_reject_invalid_convoy(count, gap):
    with pytest.raises(ValueError):
        convoy_axles(80, 120, 4, count, gap)


def test_convoy_envelope_includes_last_vehicle():
    model = Model()
    axles = convoy_axles(80000, 120000, 4, 3, 4)
    result = envelope(model, axles)
    assert result["positions"][-1] > 45
    for position in (5, 12, 22, 30, 40):
        solved = model.solve(combined_loads(model, position, axles))
        for key in ("U", "R", "forces", "stresses"):
            assert np.all(solved[key] >= result[key]["min"] - 1e-6)
            assert np.all(solved[key] <= result[key]["max"] + 1e-6)


def test_convoy_and_legacy_persistence(tmp_path):
    model, legacy = load_model(Path(__file__).parent / "examples" / "pratt_vehicle.json")
    assert scenario_axles(legacy) == [(0, 80000), (4, 120000)]
    state = {**legacy, "vehicle_count": 3, "vehicle_gap_m": 5.5}
    path = tmp_path / "convoy.json"
    save_model(path, model, state)
    _, saved = load_model(path)
    assert saved == state
    assert scenario_axles(saved) == [
        (0, 80000),
        (4, 120000),
        (9.5, 80000),
        (13.5, 120000),
        (19, 80000),
        (23, 120000),
    ]
    for fault in (
        {"vehicle_count": 4},
        {"vehicle_count": True},
        {"vehicle_gap_m": -1},
        {"vehicle_gap_m": 1001},
        {"vehicle_gap_m": float("nan")},
    ):
        with pytest.raises(ValueError):
            save_model(path, model, {**state, **fault})


@pytest.mark.parametrize("count", [1, 2, 3])
def test_scene_builds_and_reuses_separate_vehicle_actors(count):
    scene = Scene3D(NoRenderPlotter(), pv, lambda entity: None)
    model = Model()
    vehicle = (22, 18, 80, 120, 0, 25, 0.18, count, 4)
    scene.render(model, vehicle=vehicle)
    generation = scene.generation
    cabs = [
        (actor, part)
        for actor, part in scene._vehicle_parts
        if part.role in ("cab", "passenger_body", "bus_body")
    ]
    assert scene._vehicle_types == ["truck", "passenger", "bus"][:count]
    assert len(cabs) == count
    assert [actor.position[0] for actor, _ in cabs] == [22 - 8 * i for i in range(count)]
    assert len(scene._vehicle_arrows) == 2 * count
    assert all(actor.visibility for actor in scene._vehicle_arrows)
    assert len({actor.GetAddressAsString("") for actor, _ in cabs}) == count
    scene.render(model, vehicle=(23, 19, 80, 120, 0, 25, 0.18, count, 4))
    assert scene.generation == generation
    assert [actor.position[0] for actor, _ in cabs] == [23 - 8 * i for i in range(count)]
    scene.update_vehicle((30, 26, 80, 120, 0, 25, 0.18, count, 4))
    assert not scene._vehicle_arrows[0].visibility
    assert not scene._vehicle_arrows[1].visibility
    if count > 1:
        assert all(actor.visibility for actor in scene._vehicle_arrows[2:])
    scene.render(model, vehicle=vehicle, show_vehicle=False, show_loads=False)
    assert not any(actor.visibility for actor in scene._groups["vehicle"])
    assert not any(actor.visibility for actor in scene._vehicle_arrows)


def test_count_change_rebuilds_and_follow_camera_works():
    selected = []
    scene = Scene3D(NoRenderPlotter(), pv, selected.append)
    model = Model()
    scene.render(model, vehicle=(22, 18, 80, 120, 0, 25, 0.18))
    generation = scene.generation
    scene.render(model, vehicle=(22, 18, 80, 120, 0, 25, 0.18, 3, 4))
    assert scene.generation == generation + 1
    scene._picked(scene._vehicle_arrows[-1])
    assert selected == [("axle", 1)]
    scene.set_camera("Follow vehicle")
    previous = scene.plotter.camera_position
    scene.update_vehicle((23, 19, 80, 120, 0, 25, 0.18, 3, 4))
    assert scene.plotter.camera_position != previous


def test_desktop_count_controls_physics_playback_and_exit(window, monkeypatch):
    w = window
    assert w.vehicle_count.minimum() == 1
    assert w.vehicle_count.maximum() == 3
    assert not w.vehicle_gap.isEnabled()
    w.vehicle_count.setValue(3)
    assert w.vehicle_gap.isEnabled()
    w.moving_toggle.setChecked(True)
    w.vehicle_position.setValue(489)  # all six axles are on the 25 m deck
    assert len(w.axles()) == 6
    assert w.vehicle_visual()[7:] == (3, 4)
    assert -sum(fy for fx, fy in w.vehicle_nodal_loads().values()) == pytest.approx(600000)
    direct = w.model.solve(combined_loads(w.model, w.front_position(), w.axles()))
    np.testing.assert_allclose(w.model.results["U"], direct["U"])
    clock = [100.0]
    monkeypatch.setattr("main.time.monotonic", lambda: clock[0])
    w.play_pause()
    assert w.play_timer.isActive()
    w.vehicle_gap.setValue(5)
    assert not w.play_timer.isActive()
    assert not w.displacement_history
    assert w.redundancy is None
    w.vehicle_position.setValue(999)
    w.play_pause()
    clock[0] += 100
    w.animate_vehicle()
    assert not w.play_timer.isActive()
    assert w.front_position() > 47
    assert not w.vehicle_nodal_loads()
    assert not w.test_errors


def test_desktop_convoy_roundtrip_and_legacy_reset(window, monkeypatch, tmp_path):
    w = window
    monkeypatch.setattr(QMessageBox, "question", lambda *args: QMessageBox.Yes)
    w.vehicle_count.setValue(3)
    w.vehicle_gap.setValue(6.25)
    w.moving_toggle.setChecked(True)
    path = tmp_path / "convoy.json"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *args: (str(path), ""))
    w.save_project()
    expected = w.scenario()
    w.vehicle_count.setValue(1)
    assert w.load_project(path)
    assert w.scenario() == expected
    assert len(w.axles()) == 6
    legacy = Path(__file__).parent / "examples" / "pratt_vehicle.json"
    assert w.load_project(legacy)
    assert w.vehicle_count.value() == 1
    assert w.vehicle_gap.value() == 4
    assert not w.vehicle_gap.isEnabled()
    assert not w.test_errors


def test_gap_precision_rejected_before_replacing_project(window, tmp_path):
    original = window.model
    path = tmp_path / "precision.json"
    save_model(path, original, {**window.scenario(), "vehicle_gap_m": 0.001})
    assert not window.load_project(path)
    assert window.model is original
    assert len(window.test_errors) == 1


def test_convoy_axle_edit_and_undo(window):
    w = window
    w.vehicle_count.setValue(3)
    w.vehicle_gap.setValue(5.5)
    before = w.scenario()
    w.change_axle_3d(0, 100, 6)
    assert all(force == 100000 for _, force in w.axles()[::2])
    w.undo_3d_edit()
    assert w.scenario() == before
    assert not w.test_errors


def test_cli_uses_saved_convoy(window, tmp_path):
    from run_redundancy_study import main

    path = tmp_path / "convoy.json"
    save_model(path, window.model, {**window.scenario(), "enabled": True, "vehicle_count": 3})
    output = tmp_path / "study"
    assert (
        main(["--model", str(path), "--member", "1", "--factors", "1", "--output", str(output)])
        == 0
    )
    study = json.loads((output / "redundancy.json").read_text())
    assert len(study["axles_offset_m_force_N"]) == 6
