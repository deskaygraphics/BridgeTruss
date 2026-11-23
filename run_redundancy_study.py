"""Generate reproducible redundancy case studies without launching the GUI."""

import argparse
import csv
import math
from pathlib import Path

from persistence import export_redundancy, load_model
from redundancy import redundancy_study
from moving_loads import scenario_axles


EXAMPLES = Path(__file__).resolve().parent / "examples"
DEFAULT_FACTORS = [1, 0.75, 0.5, 0.25, 0]


def triangle_checks(study):
    """Independent force-method equations for the shipped unit-height triangle."""
    rows = []
    EA, P, L = 2e9, 1000.0, 1.0
    f = (math.sqrt(2) + 0.5) * L / EA
    ids = study["node_ids"]
    for case in study["cases"]:
        alpha = case["area_factor"]
        q = P / (1 + alpha * EA / L * f)
        result = case["snapshot"]
        references = [
            ("apex_ux", "m", q * L / (2 * EA), result["U_m"][2 * ids.index(3)]),
            ("apex_uy", "m", -q * f, result["U_m"][2 * ids.index(3) + 1]),
            ("tie_force", "N", q / 2, result["forces_N"][0]),
            ("left_diagonal_force", "N", -q / math.sqrt(2), result["forces_N"][1]),
            ("right_diagonal_force", "N", -q / math.sqrt(2), result["forces_N"][2]),
            ("left_Ry", "N", q / 2, result["R_N"][2 * ids.index(1) + 1]),
            ("right_Ry", "N", q / 2, result["R_N"][2 * ids.index(2) + 1]),
            ("anchor_Ry", "N", P - q, result["R_N"][2 * ids.index(4) + 1]),
            ("strain_energy", "J", 0.5 * P * q * f, result["strain_energy_J"]),
        ]
        if alpha:
            references.append(("redundant_force", "N", -(P - q), result["forces_N"][3]))
        for response, unit, expected, actual in references:
            error = abs(actual - expected)
            tolerance = max(abs(expected) * 1e-9, {"m": 1e-14, "N": 1e-7, "J": 1e-12}[unit])
            rows.append(
                {
                    "area_factor": alpha,
                    "response": response,
                    "unit": unit,
                    "reference": expected,
                    "computed": actual,
                    "absolute_error": error,
                    "absolute_tolerance": tolerance,
                    "passed": math.isfinite(actual) and error <= tolerance,
                }
            )
    return rows


def interpretation(study):
    baseline = study["cases"][0]
    lines = [
        f"Selected member: M{study['selected_member']} {study['selected_endpoints']}",
        f"Loading: {study['loading']}",
        f"Common force-comparison front x (m): {study['comparison_front_x_m']}",
        "Critical-member and critical-node positions below belong to separate extrema.",
        "Status 'stable' means accepted by the linear stiffness check, not safe by a design code.",
        "",
    ]
    for row in study["cases"]:
        factor = row["area_factor"]
        if row["status"] != "stable":
            lines.append(f"A/A0={factor:g}: REJECTED — {row['reason']}")
            continue
        ratio = row["peak_deflection_ratio"]
        ratio_text = f"{ratio:.6g}" if ratio is not None else "undefined (zero baseline)"
        lines.append(
            f"A/A0={factor:g}: stable; peak |uy|={row['peak_abs_uy_m'] * 1000:.9g} mm "
            f"at N{row['critical_node']}, front x={row['deflection_front_x_m']}; "
            f"deflection ratio={ratio_text}; peak |N|={row['peak_abs_force_N'] / 1000:.9g} kN "
            f"at M{row['critical_member']}, front x={row['force_front_x_m']}."
        )
        if factor != 1:
            remaining = [m for m in row["member_comparison"] if m["present"]]
            largest = max(remaining, key=lambda m: abs(m["delta_force_N"]))
            lines.append(
                f"  Largest remaining-member signed change at the COMMON load case: "
                f"M{largest['member_id']}, delta N={largest['delta_force_N'] / 1000:.9g} kN."
            )
    lines += [
        "",
        "Engineering interpretation:",
        "Joint equilibrium must hold before and after modification. In an indeterminate model, "
        "equilibrium alone does not determine all member forces: compatible joint movements and "
        "N=EA/L times axial extension determine how parallel load paths share the load.",
        "Reducing one path's area changes its axial stiffness, so remaining paths can attract "
        "additional load. A stable removal demonstrates an alternative path for these loads; "
        "it does not establish adequate remaining capacity.",
        "In a stable determinate truss, changing area changes displacements but not member forces "
        "under unchanged prescribed loads. Removing an essential member can create a mechanism.",
        "The count m+r-2j is descriptive, not proof of stability; a fully restrained orphan "
        "anchor can also affect that count without adding a free mechanism.",
        f"Baseline peak deflection: {baseline['peak_abs_uy_m']:.12g} m.",
        "",
        study["limitations"],
    ]
    return "\n".join(lines) + "\n"


def write_case(directory, model, member, factors, axles=None):
    study = redundancy_study(model, member, factors, axles)
    export_redundancy(directory, study)
    (directory / "interpretation.txt").write_text(interpretation(study), encoding="utf-8")
    return study


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path, help="New directory (must not exist)")
    parser.add_argument("--model", type=Path, help="Optional versioned model JSON")
    parser.add_argument("--member", type=int, help="One-based member ID for --model")
    parser.add_argument("--static", action="store_true", help="Ignore saved vehicle scenario")
    parser.add_argument("--factors", default="1,0.75,0.5,0.25,0")
    args = parser.parse_args(argv)
    if args.model is not None and args.member is None:
        parser.error("--model requires --member")
    if args.member is not None and args.model is None:
        parser.error("--member requires --model")
    try:
        factors = [float(value.strip()) for value in args.factors.split(",")]
        # Validate before creating any outputs.
        probe, _ = load_model(args.model or EXAMPLES / "benchmark_redundant.json")
        redundancy_study(probe, args.member if args.model else 4, factors)
        args.output.mkdir(parents=True, exist_ok=False)
        if args.model:
            model, scenario = load_model(args.model)
            axles = (
                scenario_axles(scenario) if scenario.get("enabled") and not args.static else None
            )
            write_case(args.output, model, args.member, factors, axles)
            print(f"Study exported: {args.output}")
            return 0
        triangle, _ = load_model(EXAMPLES / "benchmark_redundant.json")
        study = write_case(args.output / "triangle", triangle, 4, factors)
        checks = triangle_checks(study)
        with (args.output / "triangle" / "analytical_checks.csv").open(
            "w", newline="", encoding="utf-8"
        ) as stream:
            writer = csv.DictWriter(stream, fieldnames=list(checks[0]))
            writer.writeheader()
            writer.writerows(checks)
        bridge, scenario = load_model(EXAMPLES / "redundant_bridge.json")
        axles = None if args.static else scenario_axles(scenario)
        write_case(args.output / "redundant_bridge", bridge, 18, factors, axles)
        determinate, _ = load_model(EXAMPLES / "pratt_vehicle.json")
        write_case(args.output / "determinate_bridge", determinate, 1, factors, axles)
        passed = sum(row["passed"] for row in checks)
        print(f"Triangle analytical checks: {passed}/{len(checks)} passed.")
        print(f"Three case studies exported: {args.output}")
        return 0 if passed == len(checks) else 1
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Study generation failed: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
