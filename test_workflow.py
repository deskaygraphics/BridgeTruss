import json
from pathlib import Path
import numpy as np
import pytest
from bridge_model import Model
from design import compare_trusses, parameter_study, metrics, volume
from moving_loads import envelope, combined_loads
from persistence import save_model, load_model, export_results


@pytest.mark.parametrize(
    "name", ["benchmark_bar", "benchmark_triangle", "benchmark_redundant", "pratt_vehicle"]
)
def test_shipped_examples(name):
    model, state = load_model(Path(__file__).parent / "examples" / f"{name}.json")
    assert model.solve()["relative_residual"] < 1e-10
    if name == "benchmark_bar":
        assert model.results["U"][2] == pytest.approx(1e-6)
        assert model.results["R"][0] == pytest.approx(-1000)
    if state:
        assert state["enabled"]
        assert envelope(model, [(0, state["front_N"]), (state["spacing_m"], state["rear_N"])])


def test_model_roundtrip(tmp_path):
    model = Model("Howe Truss")
    scenario = {
        "enabled": True,
        "front_N": 80000,
        "rear_N": 120000,
        "spacing_m": 4,
        "position_fraction": 0.4,
    }
    path = tmp_path / "model.json"
    save_model(path, model, scenario)
    loaded, state = load_model(path)
    assert state == scenario
    assert loaded.deck_nodes == model.deck_nodes
    np.testing.assert_allclose(model.solve()["U"], loaded.solve()["U"])


@pytest.mark.parametrize(
    "fault",
    ["version", "nonfinite", "duplicate_id", "restraint", "dimension", "scenario", "planarity"],
)
def test_reject_corrupt_file(tmp_path, fault):
    path = tmp_path / "model.json"
    save_model(path, Model())
    doc = json.loads(path.read_text())
    if fault == "version":
        doc["schema_version"] = 99
    elif fault == "nonfinite":
        doc["members"][0]["E"] = float("nan")
    elif fault == "duplicate_id":
        doc["nodes"].append(doc["nodes"][0])
    elif fault == "restraint":
        doc["supports"]["0"] = [1, 1]
    elif fault == "dimension":
        doc["dimension"] = 3
    elif fault == "scenario":
        doc["scenario"] = {"enabled": True}
    else:
        doc["nodes"][0]["xyz"][2] = 1
    path.write_text(json.dumps(doc))
    with pytest.raises(ValueError):
        load_model(path)


def test_complete_export(tmp_path):
    model = Model()
    e = envelope(model, [(0, 1000), (4, 2000)])
    export_results(tmp_path, model, model.solve(), envelopes=e)
    assert {p.name for p in tmp_path.iterdir()} == {
        "members.csv",
        "nodes.csv",
        "envelopes.csv",
        "analysis.json",
    }
    doc = json.loads((tmp_path / "analysis.json").read_text())
    assert doc["envelopes"]["includes_static"]
    assert doc["diagnostics"]["relative_residual"] < 1e-10
    assert (tmp_path / "members.csv").read_text().splitlines()[1].startswith("1,")


def test_equal_volume_and_common_load_comparison():
    model = Model()
    rows = compare_trusses(model)
    for row in rows:
        assert row["volume_m3"] == pytest.approx(volume(model))
    axles = [(0, 80000), (4, 120000)]
    moving = compare_trusses(model, axles)
    assert all(
        a["vertical_deflection_m"] > b["vertical_deflection_m"] for a, b in zip(moving, rows)
    )
    model.loads = {6: (0, -1000000)}
    changed = compare_trusses(model)
    assert changed[0]["vertical_deflection_m"] != rows[0]["vertical_deflection_m"]


def test_design_study_and_model_preservation():
    model = Model()
    before = model.to_solver()
    study = parameter_study(model, [3, 4, 5], [1, 2], [1, 2], 0.1, 250e6)
    assert len(study["candidates"]) == 12
    assert study["best"] is not None
    assert model.to_solver() == before
    assert any(row["pareto"] for row in study["candidates"])
    failed = parameter_study(model, [4], [1], [1], 1e-12, 1.0)
    assert failed["best"] is None
    with pytest.raises(ValueError):
        parameter_study(model, [0], [1], [1], 0.1, 250e6)
    base = metrics(model)
    for member in model.members:
        member.A *= 2
    larger = metrics(model)
    assert larger["mass_kg"] == pytest.approx(2 * base["mass_kg"])
    assert larger["vertical_deflection_m"] == pytest.approx(0.5 * base["vertical_deflection_m"])


def test_design_study_preserves_active_moving_results():
    model = Model()
    axles = [(0, 80000), (4, 120000)]
    active = model.solve(combined_loads(model, 12, axles))
    displacement = active["U"].copy()
    static_loads = dict(model.loads)
    parameter_study(model, [3, 4], [1], [1], 0.1, 250e6, axles=axles)
    assert model.results is active
    np.testing.assert_array_equal(model.results["U"], displacement)
    assert model.loads == static_loads
