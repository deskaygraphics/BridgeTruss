"""Independent analytical benchmarks; all quantities use SI."""

import math
import numpy as np
import pytest
from model import blank, add_node, add_member
from solver import solve, PreparedTruss
from bridge_model import Model


def triangle(redundant=False):
    m = blank(2)
    a = add_node(m, [-1, 0, 0], [True, True, False])
    b = add_node(m, [1, 0, 0], [False, True, False])
    c = add_node(m, [0, 1, 0], load=[0, -1000, 0])
    add_member(m, a, b, E=200e9, A=0.01)
    add_member(m, a, c, E=200e9, A=0.01)
    add_member(m, b, c, E=200e9, A=0.01)
    if redundant:
        # A fourth bar adds one redundant axial load path to the grounded model.
        d = add_node(m, [0, 0, 0], [True, True, False])
        add_member(m, d, c, E=200e9, A=0.01)
    return m, c


@pytest.mark.parametrize("redundant", [False, True])
def test_analytical_triangle(redundant):
    m, c = triangle(redundant)
    r = solve(m)
    EA, P = 2e9, 1000.0
    # Virtual work: lateral pair plus bottom tie compliance:
    # apex flexibility f = (sqrt(2) + 1/2)/EA.
    f = (math.sqrt(2) + 0.5) / EA
    pair_load = P / (1 + EA * f) if redundant else P
    assert r["U"][c][1] == pytest.approx(-pair_load * f, rel=1e-10)
    assert r["members"][1]["force"] == pytest.approx(pair_load / 2)
    for mid in (2, 3):
        assert r["members"][mid]["force"] == pytest.approx(-pair_load / math.sqrt(2))
    if redundant:
        assert r["members"][4]["force"] == pytest.approx(-(P - pair_load))
    assert r["R"][1][1] == pytest.approx(pair_load / 2)
    assert r["R"][2][1] == pytest.approx(pair_load / 2)
    assert r["strain_energy"] == pytest.approx(0.5 * P * abs(r["U"][c][1]))
    assert r["relative_residual"] < 1e-12
    totals = sum((np.array(r["R"][nid]) + m["nodes"][nid]["load"][:2] for nid in r["ids"]))
    np.testing.assert_allclose(totals, 0, atol=1e-9)
    moment = sum(
        m["nodes"][nid]["xyz"][0] * (r["R"][nid][1] + m["nodes"][nid]["load"][1])
        - m["nodes"][nid]["xyz"][1] * (r["R"][nid][0] + m["nodes"][nid]["load"][0])
        for nid in r["ids"]
    )
    assert abs(moment) < 1e-9


@pytest.mark.parametrize("kind", ["Pratt Truss", "Warren Truss", "Howe Truss"])
def test_dashboard_shared_solver(kind):
    model = Model(kind)
    direct = solve(model.to_solver())
    adapted = model.solve()
    np.testing.assert_allclose(adapted["U"], np.array(list(direct["U"].values())).ravel())
    assert sum(adapted["R"][1::2]) == pytest.approx(200000)


@pytest.mark.parametrize(
    "fault", ["nan", "zero_area", "duplicate", "missing_node", "mechanism", "isolated"]
)
def test_invalid_models(fault):
    m, _ = triangle()
    if fault == "nan":
        m["nodes"][1]["xyz"][0] = float("nan")
    elif fault == "zero_area":
        m["members"][1]["A"] = 0
    elif fault == "duplicate":
        m["members"][4] = dict(m["members"][1])
    elif fault == "missing_node":
        m["members"][1]["i"] = 99
    elif fault == "mechanism":
        m["nodes"][1]["fix"] = [False] * 3
    else:
        add_node(m, [4, 4, 0])
    with pytest.raises(ValueError):
        solve(m)


def test_batch_loads_and_failed_result_invalidation():
    model = Model()
    prepared = PreparedTruss(model.to_solver())
    results = prepared.solve_many(np.column_stack([prepared.F, 2 * prepared.F]))
    np.testing.assert_allclose(results[1]["U"][6], 2 * np.array(results[0]["U"][6]))
    model.solve()
    model.members[0].A = -1
    with pytest.raises(ValueError):
        model.solve()
    assert model.results is None


def test_rotated_translated_symmetric_triangle():
    m, c = triangle()
    original = solve(m)
    angle = 0.37
    rotation = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
    # Fully restrain both base nodes: rotation-invariant supports, redundant tie has zero strain.
    m["nodes"][2]["fix"] = [True, True, False]
    baseline = solve(m)
    for node in m["nodes"].values():
        node["xyz"][:2] = rotation @ node["xyz"][:2] + [8, -3]
        node["load"][:2] = rotation @ node["load"][:2]
    rotated = solve(m)
    np.testing.assert_allclose(rotated["U"][c], rotation @ baseline["U"][c], atol=1e-14)
    for mid in baseline["members"]:
        assert rotated["members"][mid]["force"] == pytest.approx(
            baseline["members"][mid]["force"], abs=1e-9
        )
    assert original["strain_energy"] > baseline["strain_energy"]
