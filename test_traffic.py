"""Simultaneous traffic is a load train, never duplicated static loading."""

import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from bridge_model import Model
from moving_loads import combined_loads, envelope, event_positions, vehicle_loads
from persistence import load_model, model_document, save_model, validate_document
from run_redundancy_study import main as study_cli
from traffic import positioned_vehicles, preset_vehicle, scenario_axles, validate_scenario


def profile(count=3, enabled=True):
    return {
        "enabled": enabled,
        "position_fraction": 0.5,
        "vehicles": [preset_vehicle("Truck"), preset_vehicle("Car", 3), preset_vehicle("Bus", 3)][
            :count
        ],
    }


def test_offsets_and_example_presets():
    s = profile()
    assert [v["front_offset_m"] for v in positioned_vehicles(s)] == [0, 7, 12.7]
    assert scenario_axles(s) == [
        (0, 80000),
        (4, 120000),
        (7, 8000),
        (9.7, 7000),
        (12.7, 50000),
        (18.7, 90000),
    ]
    assert preset_vehicle("Car")["front_N"] == 8000
    assert preset_vehicle("Bus")["spacing_m"] == 6
    with pytest.raises(ValueError):
        preset_vehicle([])


@pytest.mark.parametrize("count", [2, 3])
def test_complete_response_superposition_static_counted_once(count):
    model = Model()
    s = profile(count)
    lead = 21.0
    baseline = deepcopy(model).solve()
    expected = {k: baseline[k].copy() for k in ("U", "R", "F", "forces", "stresses")}
    for vehicle in positioned_vehicles(s):
        axles = [(0, vehicle["front_N"]), (vehicle["spacing_m"], vehicle["rear_N"])]
        result = deepcopy(model).solve(
            combined_loads(model, lead - vehicle["front_offset_m"], axles)
        )
        for key in expected:
            expected[key] += result[key] - baseline[key]
    actual = deepcopy(model).solve(combined_loads(model, lead, scenario_axles(s)))
    for key in expected:
        np.testing.assert_allclose(
            actual[key], expected[key], rtol=1e-10, atol=1e-12 if key == "U" else 1e-6
        )


@pytest.mark.parametrize("lead", [-10, 0, 1.2, 4, 7, 12.7, 21, 25, 43.7, 80])
def test_axle_transfer_preserves_force_and_moment(lead):
    model = Model()
    axles = scenario_axles(profile())
    loads = vehicle_loads(model, lead, axles)
    active = [(lead - offset, force) for offset, force in axles if 0 <= lead - offset <= 25]
    assert -sum(fy for _, fy in loads.values()) == pytest.approx(sum(f for _, f in active))
    assert -sum(model.nodes[n][0] * fy for n, (_, fy) in loads.items()) == pytest.approx(
        sum(x * f for x, f in active), abs=1e-7
    )


def test_convoy_event_positions_and_full_passage_bounds():
    model = Model()
    axles = scenario_axles(profile())
    positions = event_positions(model, axles)
    for n in model.deck_nodes:
        for offset, _ in axles:
            assert np.any(np.isclose(positions, model.nodes[n][0] + offset, atol=1e-10))
    assert vehicle_loads(model, positions[0], axles) == {}
    assert vehicle_loads(model, positions[-1], axles) == {}
    limits = envelope(model, axles)
    for x in np.linspace(positions[0], positions[-1], 101):
        r = deepcopy(model).solve(combined_loads(model, x, axles))
        for key in ("U", "R", "forces", "stresses"):
            assert np.all(r[key] >= limits[key]["min"] - 1e-5)
            assert np.all(r[key] <= limits[key]["max"] + 1e-5)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(vehicles=[]),
        lambda s: s["vehicles"].append(preset_vehicle("Car", 3)),
        lambda s: s["vehicles"][1].update(kind="Train"),
        lambda s: s["vehicles"][1].update(kind=[]),
        lambda s: s["vehicles"][1].update(front_N=-1),
        lambda s: s["vehicles"][1].update(front_N=float("nan")),
        lambda s: s["vehicles"][1].update(rear_N=float("inf")),
        lambda s: s["vehicles"][1].update(front_N=10**400),
        lambda s: s["vehicles"][1].update(front_N=True),
        lambda s: s["vehicles"][1].update(spacing_m=0),
        lambda s: s["vehicles"][1].update(gap_m=1.9),
        lambda s: s["vehicles"][0].update(gap_m=3),
        lambda s: s.update(position_fraction=1.1),
        lambda s: s.update(enabled=1),
        lambda s: s.update(unrecognized=True),
        lambda s: s["vehicles"][1].update(unrecognized=True),
    ],
)
def test_profile_validation_rejects_invalid_inputs_without_mutation(mutate):
    scenario = profile()
    mutate(scenario)
    snapshot = repr(scenario)
    with pytest.raises(ValueError):
        validate_scenario(scenario)
    assert repr(scenario) == snapshot


def test_v1_unchanged_and_v2_round_trip(tmp_path):
    model = Model()
    legacy = {
        "enabled": True,
        "front_N": 80000,
        "rear_N": 120000,
        "spacing_m": 4,
        "position_fraction": 0.5,
    }
    first = tmp_path / "old.json"
    save_model(first, model, legacy)
    assert json.loads(first.read_text())["schema_version"] == 1
    assert load_model(first)[1] == legacy
    assert scenario_axles(legacy) == [(0, 80000), (4, 120000)]
    second = tmp_path / "traffic.json"
    save_model(second, model, profile())
    data = json.loads(second.read_text())
    assert data["schema_version"] == 2
    loaded, state = load_model(second)
    assert state == profile()
    assert model_document(loaded, state) == data
    for bad_version in (1, 99, True):
        bad = deepcopy(data)
        bad["schema_version"] = bad_version
        with pytest.raises(ValueError):
            validate_document(bad)
    bad = json.loads(first.read_text())
    bad["schema_version"] = 2
    with pytest.raises(ValueError):
        validate_document(bad)


def test_cli_uses_all_traffic_axles(tmp_path):
    path = tmp_path / "traffic.json"
    model, _ = load_model(Path(__file__).parent / "examples/redundant_bridge.json")
    save_model(path, model, profile())
    output = tmp_path / "study"
    assert (
        study_cli(
            ["--model", str(path), "--member", "18", "--factors", "1,0", "--output", str(output)]
        )
        == 0
    )
    data = json.loads((output / "redundancy.json").read_text())
    assert data["axles_offset_m_force_N"] == [list(a) for a in scenario_axles(profile())]


def test_workspace_traffic_persistence_history_and_exports():
    pytest.importorskip("plotly")
    from web.workspace import Workspace

    w = Workspace()
    s = profile()
    w.configure_traffic(True, s["vehicles"], 0.5)
    s["vehicles"][1]["front_N"] = 1
    assert w.vehicles[1]["front_N"] == 8000
    for fraction in (0, 0.5, 1):
        w.set_position(fraction)
        expected = deepcopy(w.model).solve(combined_loads(w.model, w.position, w.axles))
        np.testing.assert_allclose(w.model.results["U"], expected["U"], atol=1e-13)
    assert not vehicle_loads(w.model, w.position, w.axles)
    w.set_position(0.5)
    w.compute_envelopes()
    w.explore([4], [1], [1], 50, 150, 7850)
    assert w.study["position_reference"].startswith("leading")
    w.play()
    w.tick(w._last_tick + 0.25)
    w.pause()
    assert w.history and w.envelopes
    data = w.model_json()
    other = Workspace()
    other.load_json(data)
    assert other.scenario == w.scenario
    other.analyze()
    np.testing.assert_allclose(other.model.results["U"], w.model.results["U"], atol=1e-13)
    with zipfile.ZipFile(io.BytesIO(w.bundle())) as archive:
        metadata = json.loads(archive.read("analysis.json"))
        assert len(metadata["traffic"]["vehicles"]) == 3
        assert metadata["traffic"]["axles_offset_m_force_N"] == [list(a) for a in w.axles]
        assert metadata["model"]["schema_version"] == 2
    old_scenario = deepcopy(w.scenario)
    bad = deepcopy(profile()["vehicles"])
    bad[1]["gap_m"] = 1
    with pytest.raises(ValueError):
        w.configure_traffic(True, bad, 0.5)
    assert w.scenario == old_scenario and w.history and w.envelopes
    updated = deepcopy(profile()["vehicles"])
    updated[1]["gap_m"] = 4
    w.configure_traffic(True, updated, 0.5)
    assert w.model.results is None and not w.history and w.envelopes is None
    w.configure_traffic(True, [preset_vehicle("Truck")], 0.5)
    assert "vehicles" not in w.scenario and json.loads(w.model_json())["schema_version"] == 1


def test_mixed_vehicle_meshes():
    pytest.importorskip("plotly")
    from web.plots import scene
    from web.workspace import Workspace

    w = Workspace()
    w.configure_traffic(True, profile()["vehicles"], 0.5)
    w.set_position(0.5)
    fig = scene(w)
    meshes = [t for t in fig.data if t.meta and t.meta.get("role") == "vehicle"]
    assert [m.meta["kind"] for m in meshes] == ["Truck", "Car", "Bus"]
    assert [m.meta["front_offset_m"] for m in meshes] == [0, 7, 12.7]
    assert [m.meta["wheel_radius"] for m in meshes] == [0.42, 0.32, 0.42]
