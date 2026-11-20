"""Educational design screening, not member buckling or code compliance."""

from copy import deepcopy
from itertools import product
import numpy as np
from bridge_model import Model
from moving_loads import envelope, deck_path
from solver import PreparedTruss


def _positive(values, name):
    values = np.asarray(values, float)
    if not values.size or not np.all(np.isfinite(values)) or np.any(values <= 0):
        raise ValueError(f"{name} must be finite and positive")
    return values


def volume(model):
    return sum(
        member.A * np.linalg.norm(np.array(model.nodes[member.b]) - model.nodes[member.a])
        for member in model.members
    )


def metrics(model, axles=None, density=7850.0):
    _positive([density], "Density")
    if axles is None:
        result = model.solve()
        u, n, stress = result["U"], result["forces"], result["stresses"]
        critical = int(np.argmax(np.abs(n)))
        uy = float(np.max(np.abs(u[1::2])))
        force, sigma, position = abs(n[critical]), float(np.max(np.abs(stress))), None
    else:
        result = envelope(model, axles)
        u = np.maximum(np.abs(result["U"]["min"]), np.abs(result["U"]["max"]))
        n = np.maximum(np.abs(result["forces"]["min"]), np.abs(result["forces"]["max"]))
        critical = int(np.argmax(n))
        bound = (
            "min"
            if abs(result["forces"]["min"][critical]) >= abs(result["forces"]["max"][critical])
            else "max"
        )
        position = float(result["forces"]["x_" + bound][critical])
        uy, force = float(np.max(u[1::2])), float(n[critical])
        sigma = float(
            max(
                np.max(np.abs(result["stresses"]["min"])), np.max(np.abs(result["stresses"]["max"]))
            )
        )
    return {
        "vertical_deflection_m": uy,
        "peak_force_N": float(force),
        "peak_stress_Pa": sigma,
        "critical_member": critical + 1,
        "front_x_m": position,
        "volume_m3": float(volume(model)),
        "mass_kg": float(volume(model) * density),
    }


def compare_trusses(reference, axles=None, density=7850.0):
    """Same geometry, supports, static/vehicle loads, uniform E and total volume."""
    if set(reference.nodes) != set(range(10)):
        raise ValueError("Preset comparison requires the ten-node preset geometry/IDs")
    if not reference.members:
        raise ValueError("Add members before comparing")
    if not all(np.isclose(m.E, reference.members[0].E) for m in reference.members):
        raise ValueError("Equal-volume preset comparison requires one elastic modulus")
    PreparedTruss(reference.to_solver())
    target = volume(reference)
    rows = []
    for kind in ("Pratt Truss", "Warren Truss", "Howe Truss"):
        candidate = Model(kind)
        candidate.nodes = deepcopy(reference.nodes)
        candidate.loads = deepcopy(reference.loads)
        candidate.fixed = deepcopy(reference.fixed)
        candidate.deck_nodes = list(reference.deck_nodes)
        length = sum(
            np.linalg.norm(np.array(candidate.nodes[m.b]) - candidate.nodes[m.a])
            for m in candidate.members
        )
        for member in candidate.members:
            member.E = reference.members[0].E
            member.A = target / length
        rows.append({"kind": kind, **metrics(candidate, axles, density)})
    return rows


def parameter_study(
    reference,
    heights,
    chord_scales,
    web_scales,
    displacement_limit,
    stress_limit,
    axles=None,
    density=7850.0,
):
    """Finite grid; no global optimality guarantee. Input model is not modified."""
    heights = _positive(heights, "Heights")
    chord_scales = _positive(chord_scales, "Chord area factors")
    web_scales = _positive(web_scales, "Web area factors")
    _positive([displacement_limit, stress_limit, density], "Limits and density")
    if len(heights) * len(chord_scales) * len(web_scales) > 500:
        raise ValueError("Limit the study to 500 candidates")
    deck, _ = deck_path(reference)
    base = reference.nodes[deck[0]][1]
    original_height = max(p[1] for p in reference.nodes.values()) - base
    if original_height <= 0 or any(p[1] < base for p in reference.nodes.values()):
        raise ValueError("Height study requires a deck at the lowest elevation and nodes above it")
    PreparedTruss(reference.to_solver())
    rows = []
    for height, chord, web in product(heights, chord_scales, web_scales):
        candidate = deepcopy(reference)
        candidate.results = None
        for nid, (x, y, z) in reference.nodes.items():
            candidate.nodes[nid] = (x, base + (y - base) * height / original_height, z)
        for member, original in zip(candidate.members, reference.members):
            horizontal = abs(reference.nodes[member.a][1] - reference.nodes[member.b][1]) < 1e-9
            member.A = original.A * (chord if horizontal else web)
        row = {"height_m": float(height), "chord_factor": float(chord), "web_factor": float(web)}
        try:
            row.update(metrics(candidate, axles, density))
            row["feasible"] = (
                row["vertical_deflection_m"] <= displacement_limit
                and row["peak_stress_Pa"] <= stress_limit
            )
        except ValueError as exc:
            row.update(feasible=False, error=str(exc))
        rows.append(row)
    feasible = [row for row in rows if row["feasible"]]
    for row in rows:
        row["pareto"] = row["feasible"] and not any(
            other["mass_kg"] <= row["mass_kg"]
            and other["vertical_deflection_m"] <= row["vertical_deflection_m"]
            and (
                other["mass_kg"] < row["mass_kg"]
                or other["vertical_deflection_m"] < row["vertical_deflection_m"]
            )
            for other in feasible
        )
    return {
        "candidates": rows,
        "limits": {"displacement_m": displacement_limit, "stress_Pa": stress_limit},
        "density_kg_m3": density,
        "loading": "static plus complete vehicle envelope" if axles is not None else "static only",
        "best": min(feasible, key=lambda row: row["mass_kg"]) if feasible else None,
        "limitations": "Finite grid; axial stress screening only. No buckling or code certification.",
    }
