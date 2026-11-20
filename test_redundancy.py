"""Independent compatibility, stability and same-load-case study checks."""

from copy import deepcopy
from pathlib import Path
import csv
import json
import math
import numpy as np
import pytest

from bridge_model import Model, Member
from moving_loads import combined_loads, envelope
from persistence import load_model, export_results, export_redundancy
from redundancy import redundancy_study


def redundant_triangle():
    return load_model(Path(__file__).parent / "examples" / "benchmark_redundant.json")[0]


def braced_bridge():
    model = Model()
    model.members.append(Member(1, 7))
    return model


def test_triangle_area_factors_and_anchor_removal():
    model = redundant_triangle()
    before = deepcopy(model.to_solver())
    active = model.solve()
    study = redundancy_study(model, 4)
    EA, P = 2e9, 1000
    flexibility = (math.sqrt(2) + 0.5) / EA
    for row in study["cases"]:
        factor = row["area_factor"]
        q = P / (1 + factor * EA * flexibility)
        assert row["status"] == "stable"
        assert row["peak_abs_uy_m"] == pytest.approx(q * flexibility)
        assert row["snapshot"]["forces_N"][0] == pytest.approx(q / 2)
        for force in row["snapshot"]["forces_N"][1:3]:
            assert force == pytest.approx(-q / math.sqrt(2))
        if factor:
            assert row["snapshot"]["forces_N"][3] == pytest.approx(-(P - q))
        else:
            assert row["snapshot"]["forces_N"][3] is None
            assert row["member_ids"] == [1, 2, 3]
        assert sum(row["snapshot"]["R_N"][1::2]) == pytest.approx(P)
        assert row["snapshot"]["relative_residual"] < 1e-10
    assert model.to_solver() == before
    assert model.results is active
    assert study["cases"][-1]["peak_deflection_ratio"] == pytest.approx(1 + EA * flexibility)


def test_fully_restrained_orphan_keeps_load_and_reaction():
    model = redundant_triangle()
    anchor = model.members[3].a
    model.loads[anchor] = (321.0, -456.0)
    study = redundancy_study(model, 4, [0])
    result = study["cases"][-1]["snapshot"]
    i = study["node_ids"].index(anchor) * 2
    np.testing.assert_allclose(result["R_N"][i : i + 2], [-321, 456])
    np.testing.assert_allclose(result["F_N"][i : i + 2], [321, -456])


def test_stable_removal_mechanism_and_original_ids():
    stable = redundancy_study(braced_bridge(), 18, [0])
    assert stable["cases"][-1]["status"] == "stable"
    mechanism = redundancy_study(Model(), 1, [0])
    assert mechanism["cases"][-1]["status"] == "rejected"
    assert "Unstable" in mechanism["cases"][-1]["reason"]
    assert "snapshot" not in mechanism["cases"][-1]
    middle = redundancy_study(braced_bridge(), 15, [0])
    row = middle["cases"][-1]
    assert row["status"] == "stable"
    assert row["member_ids"] == [*range(1, 15), 16, 17, 18]
    assert row["snapshot"]["forces_N"][14] is None
    assert row["member_comparison"][17]["member_id"] == 18


def test_moving_envelopes_and_common_position():
    model = braced_bridge()
    axles = [(0, 80000), (4, 120000)]
    study = redundancy_study(model, 18, [0.5, 0], axles)
    common = study["comparison_front_x_m"]
    for row in study["cases"]:
        candidate = deepcopy(model)
        factor = row["area_factor"]
        if factor:
            candidate.members[17].A *= factor
        else:
            candidate.members.pop(17)
        direct = candidate.solve(combined_loads(candidate, common, axles))
        np.testing.assert_allclose(row["snapshot"]["U_m"], direct["U"], atol=1e-12)
        np.testing.assert_allclose(
            [n for n in row["snapshot"]["forces_N"] if n is not None], direct["forces"]
        )
        expected = envelope(candidate, axles)
        for key in ("min", "max", "x_min", "x_max"):
            np.testing.assert_allclose(
                [n for n in row["envelopes"]["forces_N"][key] if n is not None],
                expected["forces"][key],
            )
        assert row["force_front_x_m"] is not None
        assert row["deflection_front_x_m"] is not None
    assert study["cases"][-1]["snapshot"]["forces_N"][17] is None


@pytest.mark.parametrize("factors", [[], [-1], [1.1], [float("nan")], [[0.5]], [0.5] * 51])
def test_bad_factors(factors):
    with pytest.raises(ValueError):
        redundancy_study(Model(), 1, factors)


@pytest.mark.parametrize("member", [0, -1, 18, 1.0, True])
def test_bad_member_ids(member):
    with pytest.raises(ValueError):
        redundancy_study(Model(), member)


def test_zero_reference_and_deduplication():
    model = braced_bridge()
    model.loads.clear()
    study = redundancy_study(model, 18, [0, 0, 1])
    assert study["area_factors"] == [1, 0]
    assert study["cases"][-1]["peak_deflection_ratio"] is None
    assert study["cases"][-1]["peak_abs_uy_m"] == 0


def test_export_study_original_ids_and_rejected_case(tmp_path):
    model = braced_bridge()
    study = redundancy_study(model, 15, [0], [(0, 80000), (4, 120000)])
    export_results(tmp_path, model, model.solve(), redundancy=study)
    metadata = json.loads((tmp_path / "analysis.json").read_text())
    assert metadata["redundancy_study"] == study
    assert json.loads((tmp_path / "redundancy.json").read_text()) == study
    with (tmp_path / "redundancy_members.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    removed = [r for r in rows if r["area_factor"] == "0.0" and r["member_id"] == "15"][0]
    assert removed["present"] == "False"
    assert removed["candidate_force_N"] == ""
    assert rows[-1]["member_id"] == "18"
    with (tmp_path / "redundancy_envelopes.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert any(r["id"] == "member_18" for r in rows)
    assert not any(r["id"] == "member_15" and r["area_factor"] == "0.0" for r in rows)
    assert (tmp_path / "redundancy_factor_0.png").stat().st_size > 10000
    failed = redundancy_study(Model(), 1, [0])
    export_redundancy(tmp_path / "rejected", failed)
    with (tmp_path / "rejected" / "redundancy_summary.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert rows[-1]["status"] == "rejected"
    assert rows[-1]["peak_abs_uy_m"] == ""
    assert (tmp_path / "rejected" / "redundancy_factor_0.png").exists()


def test_determinate_forces_unchanged_and_rejected_ill_conditioning():
    study = redundancy_study(Model(), 1, [0.25, 1e-15, 0])
    baseline, weakened, tiny, removed = study["cases"]
    np.testing.assert_allclose(
        weakened["snapshot"]["forces_N"], baseline["snapshot"]["forces_N"], atol=1e-8
    )
    assert weakened["peak_abs_uy_m"] > baseline["peak_abs_uy_m"]
    assert tiny["status"] == "rejected"
    assert removed["status"] == "rejected"


def test_free_orphan_and_invalid_reference_are_not_hidden():
    model = redundant_triangle()
    anchor = model.members[3].a
    model.fixed[anchor] = (True, False)
    study = redundancy_study(model, 4, [0])
    assert study["cases"][-1]["status"] == "rejected"
    assert "Disconnected" in study["cases"][-1]["reason"]
    model.members[0].A = -1
    with pytest.raises(ValueError):
        redundancy_study(model, 4)


def test_shipped_bridge_and_report_equations():
    from run_redundancy_study import triangle_checks, interpretation

    model, state = load_model(Path(__file__).parent / "examples" / "redundant_bridge.json")
    assert model.to_solver() == braced_bridge().to_solver()
    assert state["enabled"]
    checks = triangle_checks(redundancy_study(redundant_triangle(), 4))
    assert len(checks) == 49
    assert all(row["passed"] for row in checks)
    study = redundancy_study(model, 18, [0], [(0, 80000), (4, 120000)])
    assert "COMMON load case" in interpretation(study)
    for row in study["cases"]:
        result = row["snapshot"]
        forces = np.array(result["R_N"]) + result["F_N"]
        assert np.max(np.abs(forces.reshape(-1, 2).sum(axis=0))) < 1e-7
        moment = sum(
            model.nodes[nid][0] * forces[2 * i + 1] - model.nodes[nid][1] * forces[2 * i]
            for i, nid in enumerate(study["node_ids"])
        )
        assert abs(moment) < 1e-6
