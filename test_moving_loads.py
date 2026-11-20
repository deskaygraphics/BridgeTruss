import numpy as np
import pytest
from bridge_model import Model
from moving_loads import (
    MovingResponse,
    vehicle_loads,
    combined_loads,
    envelope,
    influence_lines,
    travel_limits,
    event_positions,
)


@pytest.mark.parametrize("position", [-0.1, 0.0, 2.5, 11.0, 25.0, 27.0, 29.1])
def test_cached_response_matches_direct_analysis(position):
    model = Model()
    cache = MovingResponse(model)
    axles = [(0, 80000), (4, 120000)]
    cached = cache.at(position, axles)
    direct = model.solve(combined_loads(model, position, axles))
    for field in ("U", "R", "F", "forces", "stresses"):
        np.testing.assert_allclose(cached[field], direct[field], rtol=1e-9, atol=1e-6)
    assert cached["strain_energy"] == pytest.approx(direct["strain_energy"])
    assert cached["relative_residual"] < 1e-10


AXLES = [(0.0, 80000.0), (4.0, 120000.0)]


@pytest.mark.parametrize("position", [0.0, 2.5, 4.0, 15.1, 25.0, 27.0, 29.0])
def test_transfer_conserves_force_and_moment(position):
    m = Model()
    loads = vehicle_loads(m, position, AXLES)
    on_bridge = [(position - o, p) for o, p in AXLES if 0 <= position - o <= 25]
    assert -sum(fy for fx, fy in loads.values()) == pytest.approx(sum(p for x, p in on_bridge))
    assert -sum(m.nodes[n][0] * fy for n, (fx, fy) in loads.items()) == pytest.approx(
        sum(x * p for x, p in on_bridge)
    )


def test_full_exit_and_static_load_preservation():
    m = Model()
    before = dict(m.loads)
    assert travel_limits(m, AXLES) == (0.0, 29.0)
    assert sum(p[1] for p in vehicle_loads(m, 27.0, AXLES).values()) == -120000
    assert vehicle_loads(m, 29.1, AXLES) == {}
    envelope(m, AXLES)
    assert m.loads == before
    assert m.results is None


def test_influence_line_superposition():
    m = Model()
    line = influence_lines(m)
    loads = vehicle_loads(m, 11.0, AXLES)
    weights = np.array([-loads.get(n, (0.0, 0.0))[1] for n in line["deck_nodes"]])
    static = m.solve()["U"].copy()
    direct = m.solve(combined_loads(m, 11.0, AXLES))["U"]
    np.testing.assert_allclose(static + weights @ line["U"], direct, atol=1e-12)
    np.testing.assert_allclose(line["R"][:, 1], (25 - line["x"]) / 25, atol=1e-12)


def test_event_envelope_against_dense_sampling():
    m = Model()
    event = envelope(m, AXLES)
    dense = envelope(
        m, AXLES, np.unique(np.r_[np.linspace(0, 29, 2001), event_positions(m, AXLES)])
    )
    for key in ("U", "R", "forces", "stresses"):
        for bound in ("min", "max"):
            np.testing.assert_allclose(event[key][bound], dense[key][bound], rtol=1e-8, atol=1e-7)
    assert np.all(event["forces"]["min"] <= event["forces"]["max"])


@pytest.mark.parametrize("fault", ["missing", "elevation", "duplicate_x", "negative_axle"])
def test_bad_deck_or_axles(fault):
    m = Model()
    axles = AXLES
    if fault == "missing":
        m.deck_nodes = [0, 99]
    elif fault == "elevation":
        m.deck_nodes = [0, 6]
    elif fault == "duplicate_x":
        m.nodes[1] = m.nodes[0]
    else:
        axles = [(0, -1)]
    with pytest.raises(ValueError):
        envelope(m, axles)
