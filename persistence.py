"""Versioned model files and auditable result bundles. Never deserialize code."""

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from bridge_model import Model, Member
from solver import PreparedTruss
from moving_loads import deck_path, validate_axles


def model_document(model, scenario=None):
    return {
        "schema_version": 1,
        "units": "SI: m, N, Pa",
        "dimension": 2,
        "kind": model.kind,
        "nodes": [{"id": nid, "xyz": list(xyz)} for nid, xyz in sorted(model.nodes.items())],
        "members": [
            {"id": i + 1, "i": m.a, "j": m.b, "E": m.E, "A": m.A}
            for i, m in enumerate(model.members)
        ],
        "supports": {str(n): list(v) for n, v in model.fixed.items()},
        "loads": {str(n): list(v) for n, v in model.loads.items()},
        "deck_nodes": list(model.deck_nodes),
        "scenario": scenario or {},
    }


def validate_document(doc):
    if doc["schema_version"] != 1 or doc["dimension"] != 2 or doc["units"] != "SI: m, N, Pa":
        raise ValueError("Only version 1 planar SI model files are supported")
    model = Model()
    model.clear()
    model.kind = str(doc["kind"])
    for node in doc["nodes"]:
        nid = node["id"]
        if type(nid) is not int or nid < 0 or nid in model.nodes:
            raise ValueError("Node IDs must be unique nonnegative integers")
        model.nodes[nid] = tuple(node["xyz"])
    for i, member in enumerate(doc["members"]):
        if member["id"] != i + 1:
            raise ValueError("Member IDs must be consecutive and start at 1")
        model.members.append(Member(member["i"], member["j"], member["A"], member["E"]))
    model.fixed = {int(n): tuple(v) for n, v in doc["supports"].items()}
    model.loads = {int(n): tuple(v) for n, v in doc["loads"].items()}
    if any(len(v) != 2 for v in (*model.fixed.values(), *model.loads.values())):
        raise ValueError("Planar loads and restraints require two components")
    model.deck_nodes = list(doc["deck_nodes"])
    # This deliberately rejects unstable/incomplete project files.
    PreparedTruss(model.to_solver())
    if model.deck_nodes:
        deck_path(model)
    scenario = doc.get("scenario", {})
    if not isinstance(scenario, dict):
        raise ValueError("Scenario must be an object")
    if scenario:
        if set(scenario) != {"enabled", "front_N", "rear_N", "spacing_m", "position_fraction"}:
            raise ValueError("Invalid vehicle scenario fields")
        validate_axles([(0, scenario["front_N"]), (scenario["spacing_m"], scenario["rear_N"])])
        fraction = scenario["position_fraction"]
        if (
            type(scenario["enabled"]) is not bool
            or not np.isfinite(fraction)
            or not 0 <= fraction <= 1
        ):
            raise ValueError("Invalid vehicle scenario state")
        if scenario["front_N"] > 1e8 or scenario["rear_N"] > 1e8 or scenario["spacing_m"] > 1000:
            raise ValueError("Vehicle exceeds dashboard input limits")
        if scenario["enabled"]:
            deck_path(model)
    return model, scenario


def save_model(path, model, scenario=None):
    doc = model_document(model, scenario)
    validate_document(doc)
    Path(path).write_text(json.dumps(doc, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def load_model(path):
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return validate_document(doc)
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError(f"Invalid model file: {exc}") from exc


def _plain(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def export_results(
    directory, model, result, scenario=None, envelopes=None, study=None, redundancy=None
):
    """Write a self-describing directory; caller chooses its destination."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    def write_csv(name, header, rows):
        with (directory / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(header)
            writer.writerows(rows)

    write_csv(
        "members.csv",
        ["member_id", "node_i", "node_j", "length_m", "force_N", "stress_Pa"],
        [
            (i + 1, m.a, m.b, result["lengths"][i], result["forces"][i], result["stresses"][i])
            for i, m in enumerate(model.members)
        ],
    )
    write_csv(
        "nodes.csv",
        ["node_id", "ux_m", "uy_m", "Rx_N", "Ry_N", "Fx_N", "Fy_N"],
        [
            (
                nid,
                *result["U"][2 * i : 2 * i + 2],
                *result["R"][2 * i : 2 * i + 2],
                *result["F"][2 * i : 2 * i + 2],
            )
            for i, nid in enumerate(result["ids"])
        ],
    )
    if envelopes is not None:
        rows = []
        for key, unit in (("U", "m"), ("R", "N"), ("forces", "N"), ("stresses", "Pa")):
            values = envelopes[key]
            for i in range(len(values["min"])):
                label = (
                    f"member_{i + 1}"
                    if key in ("forces", "stresses")
                    else f"node_{envelopes['ids'][i // 2]}_{'xy'[i % 2]}"
                )
                rows.append(
                    (
                        key,
                        label,
                        unit,
                        values["min"][i],
                        values["max"][i],
                        values["x_min"][i],
                        values["x_max"][i],
                    )
                )
        write_csv(
            "envelopes.csv",
            ["response", "id", "unit", "min", "max", "front_x_at_min_m", "front_x_at_max_m"],
            rows,
        )
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "model": model_document(model, scenario),
        "analysis": "linear elastic planar pin-jointed; quasi-static vehicle",
        "diagnostics": {
            key: result[key] for key in ("strain_energy", "relative_residual", "condition_number")
        },
        "envelopes": envelopes,
        "design_study": study,
        "redundancy_study": redundancy,
        "limitations": "No member buckling, dynamics, spatial stability or code certification.",
    }
    (directory / "analysis.json").write_text(
        json.dumps(metadata, indent=2, default=_plain, allow_nan=False) + "\n", encoding="utf-8"
    )
    if redundancy is not None:
        export_redundancy(directory, redundancy)


def export_redundancy(directory, study):
    """Export a standalone, reproducible study with original IDs and SI units."""
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from redundancy_plots import draw_comparison

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "redundancy.json").write_text(
        json.dumps(study, indent=2, default=_plain, allow_nan=False) + "\n", encoding="utf-8"
    )
    summary_fields = [
        "area_factor",
        "removed",
        "status",
        "reason",
        "member_count",
        "count_m_plus_r_minus_2j",
        "peak_abs_uy_m",
        "peak_deflection_ratio",
        "critical_node",
        "deflection_front_x_m",
        "peak_abs_force_N",
        "governing_signed_force_N",
        "critical_member",
        "force_front_x_m",
    ]
    with (directory / "redundancy_summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(summary_fields)
        writer.writerows([[row.get(key) for key in summary_fields] for row in study["cases"]])
    with (directory / "redundancy_members.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "area_factor",
                "comparison_front_x_m",
                "member_id",
                "node_i",
                "node_j",
                "present",
                "baseline_force_N",
                "candidate_force_N",
                "delta_force_N",
            ]
        )
        for row in study["cases"]:
            for member in row.get("member_comparison", []):
                writer.writerow(
                    [
                        row["area_factor"],
                        study["comparison_front_x_m"],
                        *[
                            member[k]
                            for k in (
                                "member_id",
                                "node_i",
                                "node_j",
                                "present",
                                "baseline_force_N",
                                "candidate_force_N",
                                "delta_force_N",
                            )
                        ],
                    ]
                )
    with (directory / "redundancy_nodes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "area_factor",
                "comparison_front_x_m",
                "node_id",
                "ux_m",
                "uy_m",
                "Rx_N",
                "Ry_N",
                "Fx_N",
                "Fy_N",
            ]
        )
        for row in study["cases"]:
            if row["status"] != "stable":
                continue
            snapshot = row["snapshot"]
            for i, nid in enumerate(study["node_ids"]):
                writer.writerow(
                    [
                        row["area_factor"],
                        study["comparison_front_x_m"],
                        nid,
                        *snapshot["U_m"][2 * i : 2 * i + 2],
                        *snapshot["R_N"][2 * i : 2 * i + 2],
                        *snapshot["F_N"][2 * i : 2 * i + 2],
                    ]
                )
    with (directory / "redundancy_envelopes.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            [
                "area_factor",
                "response",
                "id",
                "min",
                "max",
                "front_x_at_min_m",
                "front_x_at_max_m",
            ]
        )
        for row in study["cases"]:
            if not row.get("envelopes"):
                continue
            for key in ("forces_N", "stresses_Pa", "U_m", "R_N"):
                values = row["envelopes"][key]
                for i, minimum in enumerate(values["min"]):
                    if minimum is None:
                        continue
                    label = (
                        f"member_{i + 1}"
                        if key in ("forces_N", "stresses_Pa")
                        else f"node_{study['node_ids'][i // 2]}_{'xy'[i % 2]}"
                    )
                    writer.writerow(
                        [
                            row["area_factor"],
                            key,
                            label,
                            minimum,
                            values["max"][i],
                            values["x_min"][i],
                            values["x_max"][i],
                        ]
                    )
    for i, row in enumerate(study["cases"][1:], 1):
        figure = Figure(figsize=(13, 8))
        FigureCanvasAgg(figure)
        draw_comparison(figure, study, i)
        factor = repr(row["area_factor"]).removesuffix(".0").replace(".", "p")
        figure.savefig(directory / f"redundancy_factor_{factor}.png", dpi=160)
        figure.clear()
