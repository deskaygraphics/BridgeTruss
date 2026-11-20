"""Quasi-static downward axle loads on an explicitly selected horizontal deck."""

import numpy as np
from copy import deepcopy
from solver import PreparedTruss
from bridge_model import dashboard_result


class MovingResponse:
    """Exact linear superposition using one batched static/deck-unit-load solve."""

    def __init__(self, model):
        self.model = deepcopy(model)
        ids, _ = deck_path(self.model)
        self.deck_nodes = ids
        self.prepared = PreparedTruss(self.model.to_solver())
        forces = np.zeros((self.prepared.ndof, len(ids) + 1))
        forces[:, 0] = self.prepared.F
        for k, nid in enumerate(ids, start=1):
            forces[self.prepared.idx[nid] * 2 + 1, k] = -1.0
        results = self.prepared.solve_many(forces)
        self.displacements = np.column_stack(
            [np.array([r["U"][nid] for nid in self.prepared.ids]).ravel() for r in results]
        )

    def at(self, position, axles):
        moving = vehicle_loads(self.model, position, axles)
        weights = np.array([-moving.get(nid, (0.0, 0.0))[1] for nid in self.deck_nodes])
        u = self.displacements[:, 0] + self.displacements[:, 1:] @ weights
        force = self.prepared.F + self.prepared.load_vector(moving)
        return dashboard_result(self.prepared.recover(u, force))


def deck_path(model):
    ids = model.deck_nodes
    if len(ids) < 2 or len(set(ids)) != len(ids) or any(n not in model.nodes for n in ids):
        raise ValueError("Select at least two distinct existing deck nodes")
    ordered = sorted(ids, key=lambda n: model.nodes[n][0])
    points = np.array([model.nodes[n] for n in ordered], float)
    if not np.all(np.isfinite(points)) or np.ptp(points[:, 1]) > 1e-8:
        raise ValueError("Deck nodes must be finite and share a horizontal elevation")
    if np.any(np.diff(points[:, 0]) <= 1e-10):
        raise ValueError("Deck nodes must have distinct x coordinates")
    return ordered, points[:, 0]


def validate_axles(axles):
    values = np.asarray(axles, float)
    if values.ndim != 2 or values.shape[1] != 2 or not len(values):
        raise ValueError("Axles require (offset behind front, downward force) pairs")
    if not np.all(np.isfinite(values)) or np.any(values < 0):
        raise ValueError("Axle offsets and forces must be finite and nonnegative")
    if np.min(values[:, 0]) != 0:
        raise ValueError("At least one axle must have zero offset")
    return values


def vehicle_loads(model, position, axles):
    ids, xs = deck_path(model)
    axles = validate_axles(axles)
    if not np.isfinite(position):
        raise ValueError("Vehicle position must be finite")
    loads = {}
    for offset, force in axles:
        x = position - offset
        if x < xs[0] or x > xs[-1]:
            continue
        i = min(max(int(np.searchsorted(xs, x, side="right")) - 1, 0), len(xs) - 2)
        t = (x - xs[i]) / (xs[i + 1] - xs[i])
        for nid, weight in ((ids[i], 1 - t), (ids[i + 1], t)):
            loads[nid] = (0.0, loads.get(nid, (0.0, 0.0))[1] - force * weight)
    return loads


def combined_loads(model, position, axles):
    loads = dict(model.loads)
    for nid, (fx, fy) in vehicle_loads(model, position, axles).items():
        old = loads.get(nid, (0.0, 0.0))
        loads[nid] = (old[0] + fx, old[1] + fy)
    return loads


def travel_limits(model, axles):
    _, xs = deck_path(model)
    axles = validate_axles(axles)
    return float(xs[0]), float(xs[-1] + max(axles[:, 0]))


def event_positions(model, axles):
    """All piecewise-linear breakpoints and one-sided boundary states.

    Endpoint support reactions can jump as an axle enters/leaves the model.
    One-sided states therefore accompany the exact event positions.
    """
    _, xs = deck_path(model)
    axles = validate_axles(axles)
    lo, hi = travel_limits(model, axles)
    events = sorted({float(x + offset) for x in xs for offset, _ in axles} | {lo, hi})
    positions = set(events)
    # A small geometric epsilon resolves floating-point subtraction of offsets.
    epsilon = max(hi - lo, 1.0) * 1e-10
    positions.update((lo - epsilon, hi + epsilon))
    for x in events:
        positions.update((max(lo, x - epsilon), min(hi, x + epsilon)))
    return np.array(sorted(positions))


def influence_lines(model):
    """Responses to a unit downward N at each deck node; no static loads."""
    ids, xs = deck_path(model)
    prepared = PreparedTruss(model.to_solver())
    forces = np.zeros((prepared.ndof, len(ids)))
    for k, nid in enumerate(ids):
        forces[prepared.idx[nid] * 2 + 1, k] = -1.0
    results = [dashboard_result(r) for r in prepared.solve_many(forces)]
    return {
        "x": xs,
        "deck_nodes": ids,
        "ids": prepared.ids,
        "U": np.array([r["U"] for r in results]),
        "R": np.array([r["R"] for r in results]),
        "forces": np.array([r["forces"] for r in results]),
    }


def envelope(model, axles, positions=None):
    axles = validate_axles(axles)
    exact = positions is None
    positions = event_positions(model, axles) if exact else np.asarray(positions, float)
    if positions.ndim != 1 or not len(positions) or not np.all(np.isfinite(positions)):
        raise ValueError("Provide finite vehicle positions")
    prepared = PreparedTruss(model.to_solver())
    forces = np.column_stack(
        [prepared.load_vector(combined_loads(model, x, axles)) for x in positions]
    )
    results = [dashboard_result(r) for r in prepared.solve_many(forces)]
    output = {
        "positions": positions,
        "ids": prepared.ids,
        "method": "event-based with one-sided boundary states" if exact else "sampled",
        "includes_static": True,
    }
    for key in ("U", "R", "forces", "stresses"):
        values = np.array([r[key] for r in results])
        minimum, maximum = np.argmin(values, axis=0), np.argmax(values, axis=0)
        columns = np.arange(values.shape[1])
        output[key] = {
            "min": values[minimum, columns],
            "max": values[maximum, columns],
            "x_min": positions[minimum],
            "x_max": positions[maximum],
        }
    return output
