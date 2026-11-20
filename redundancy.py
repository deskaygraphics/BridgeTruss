"""Linear-elastic stiffness loss/removal studies, not progressive collapse."""

from copy import deepcopy
import numpy as np

from bridge_model import dashboard_result
from moving_loads import combined_loads, envelope, validate_axles
from persistence import model_document
from solver import PreparedTruss


LIMITATIONS = (
    "Independent linear-elastic reanalyses under unchanged prescribed loads; "
    "no damage evolution, progressive collapse, buckling, dynamics or code certification. "
    "Area reduction changes axial stiffness and stress, not automatic self-weight. "
    "Envelope extrema are not simultaneous; force diagrams use the same labeled load case. "
    "Rejected means disconnected, unstable or numerically ill-conditioned, not a capacity prediction."
)


def _expanded(values, member_ids, count):
    output = [None] * count
    for mid, value in zip(member_ids, values):
        output[mid - 1] = float(value)
    return output


def _response(model, member_ids, count, axles, position):
    loads = model.loads if axles is None else combined_loads(model, position, axles)
    prepared = PreparedTruss(model.to_solver(loads))
    result = dashboard_result(prepared.solve_many(prepared.F[:, None])[0])
    return {
        "forces_N": _expanded(result["forces"], member_ids, count),
        "stresses_Pa": _expanded(result["stresses"], member_ids, count),
        "U_m": result["U"].tolist(),
        "R_N": result["R"].tolist(),
        "F_N": result["F"].tolist(),
        "relative_residual": result["relative_residual"],
        "condition_number": result["condition_number"],
        "strain_energy_J": result["strain_energy"],
    }


def _case(model, member_ids, count, axles, position):
    snapshot = _response(model, member_ids, count, axles, position)
    ids = sorted(model.nodes)
    if axles is None:
        forces = np.array([snapshot["forces_N"][mid - 1] for mid in member_ids])
        u = np.array(snapshot["U_m"])[1::2]
        im = int(np.argmax(np.abs(forces)))
        iu = int(np.argmax(np.abs(u)))
        extremes = None
        force = float(forces[im])
        displacement = float(u[iu])
        force_x = displacement_x = None
    else:
        result = envelope(model, axles)
        extremes = {}
        for key, unit in (("forces", "N"), ("stresses", "Pa"), ("U", "m"), ("R", "N")):
            name = f"{key}_{unit}"
            extremes[name] = {
                bound: (
                    _expanded(values, member_ids, count)
                    if key in ("forces", "stresses")
                    else values.tolist()
                )
                for bound, values in result[key].items()
            }
        extremes["method"] = result["method"]
        extremes["positions_m"] = result["positions"].tolist()
        # Choose min before max for tied absolute extrema, consistently.
        forces = np.array([result["forces"][bound] for bound in ("min", "max")])
        u = np.array([result["U"][bound][1::2] for bound in ("min", "max")])
        bf, im = np.unravel_index(np.argmax(np.abs(forces)), forces.shape)
        bu, iu = np.unravel_index(np.argmax(np.abs(u)), u.shape)
        force, displacement = float(forces[bf, im]), float(u[bu, iu])
        force_x = float(result["forces"]["x_min" if bf == 0 else "x_max"][im])
        displacement_x = float(result["U"]["x_min" if bu == 0 else "x_max"][2 * iu + 1])
    return {
        "status": "stable",
        "member_ids": member_ids,
        "snapshot": snapshot,
        "envelopes": extremes,
        "peak_abs_force_N": abs(force),
        "governing_signed_force_N": force,
        "critical_member": member_ids[im],
        "force_front_x_m": force_x,
        "peak_abs_uy_m": abs(displacement),
        "governing_signed_uy_m": displacement,
        "critical_node": ids[iu],
        "deflection_front_x_m": displacement_x,
    }


def redundancy_study(reference, member_id, area_factors=(1, 0.75, 0.5, 0.25, 0), axles=None):
    """Preserve the reference, IDs and loads; factor zero physically deletes a bar.

    The baseline's governing absolute-force position is the common comparison
    case for vehicle studies. Each candidate also has its own complete envelope.
    """
    count = len(reference.members)
    if type(member_id) is not int or not 1 <= member_id <= count:
        raise ValueError("Select an existing one-based member ID")
    factors = np.asarray(area_factors, float)
    if (
        factors.ndim != 1
        or not 1 <= len(factors) <= 50
        or not np.all(np.isfinite(factors))
        or np.any(factors < 0)
        or np.any(factors > 1)
    ):
        raise ValueError("Provide 1–50 finite area factors between 0 and 1; zero means removal")
    factors = list(dict.fromkeys([1.0, *map(float, factors)]))
    original = deepcopy(reference)
    original.results = None
    original.display_loads = None
    PreparedTruss(original.to_solver())
    axles = None if axles is None else validate_axles(axles).tolist()
    position = None
    if axles is not None:
        base_envelope = envelope(original, axles)
        values = np.array([base_envelope["forces"][b] for b in ("min", "max")])
        bound, index = np.unravel_index(np.argmax(np.abs(values)), values.shape)
        position = float(base_envelope["forces"]["x_min" if bound == 0 else "x_max"][index])
    cases = []
    for factor in factors:
        candidate = deepcopy(original)
        member_ids = list(range(1, count + 1))
        if factor == 0:
            candidate.members.pop(member_id - 1)
            member_ids.remove(member_id)
        else:
            candidate.members[member_id - 1].A *= factor
        row = {
            "area_factor": factor,
            "removed": factor == 0,
            "member_count": len(candidate.members),
            "count_m_plus_r_minus_2j": (
                len(candidate.members)
                + sum(sum(v) for v in candidate.fixed.values())
                - 2 * len(candidate.nodes)
            ),
        }
        try:
            row.update(_case(candidate, member_ids, count, axles, position))
        except ValueError as exc:
            if factor == 1:
                raise
            row.update(status="rejected", reason=str(exc), member_ids=member_ids)
        cases.append(row)
    baseline = cases[0]
    for row in cases:
        if row["status"] != "stable":
            continue
        uy0 = baseline["peak_abs_uy_m"]
        row["peak_deflection_ratio"] = row["peak_abs_uy_m"] / uy0 if uy0 else None
        row["member_comparison"] = [
            {
                "member_id": mid,
                "node_i": m.a,
                "node_j": m.b,
                "present": mid in row["member_ids"],
                "baseline_force_N": baseline["snapshot"]["forces_N"][mid - 1],
                "candidate_force_N": row["snapshot"]["forces_N"][mid - 1],
                "delta_force_N": (
                    row["snapshot"]["forces_N"][mid - 1] - baseline["snapshot"]["forces_N"][mid - 1]
                    if mid in row["member_ids"]
                    else None
                ),
            }
            for mid, m in enumerate(original.members, 1)
        ]
    selected = original.members[member_id - 1]
    return {
        "schema_version": 1,
        "model": model_document(original),
        "selected_member": member_id,
        "selected_endpoints": [selected.a, selected.b],
        "original_area_m2": selected.A,
        "area_factors": factors,
        "node_ids": sorted(original.nodes),
        "axles_offset_m_force_N": axles,
        "loading": "static only" if axles is None else "static plus complete vehicle envelope",
        "comparison_front_x_m": position,
        "comparison_case": (
            "static loads"
            if axles is None
            else "baseline governing absolute-member-force front-axle position, shared by all cases"
        ),
        "cases": cases,
        "limitations": LIMITATIONS,
    }
