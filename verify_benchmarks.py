"""Export independent analytical references versus the shipped benchmark models."""

import argparse
import csv
import math
from pathlib import Path
import sys

from persistence import load_model


def evaluate_benchmarks():
    """Reference equations are hand derivations documented in README, not FE outputs."""
    rows = []

    def compare(case, response, unit, reference, computed):
        error = abs(computed - reference)
        limit = abs(reference) * 0.001 if reference else {"m": 1e-10, "N": 1e-6, "J": 1e-9}[unit]
        rows.append(
            {
                "benchmark": case,
                "response": response,
                "unit": unit,
                "reference": reference,
                "computed": float(computed),
                "absolute_error": error,
                "relative_error_percent": 100 * error / abs(reference) if reference else "",
                "absolute_error_limit": limit,
                "passed": math.isfinite(computed) and error < limit,
            }
        )

    examples = Path(__file__).parent / "examples"
    model, _ = load_model(examples / "benchmark_bar.json")
    result = model.solve()
    compare("axial_bar", "node_1_ux", "m", 1e-6, result["U"][2])
    compare("axial_bar", "member_1_force", "N", 1000.0, result["forces"][0])
    compare("axial_bar", "node_0_Rx", "N", -1000.0, result["R"][0])
    compare("axial_bar", "node_0_Ry", "N", 0.0, result["R"][1])
    compare("axial_bar", "strain_energy", "J", 0.0005, result["strain_energy"])
    EA, force = 2e9, 1000.0
    flexibility = (math.sqrt(2) + 0.5) / EA
    for redundant in (False, True):
        case = "redundant_triangle" if redundant else "determinate_triangle"
        filename = "benchmark_redundant.json" if redundant else "benchmark_triangle.json"
        model, _ = load_model(examples / filename)
        result = model.solve()
        q = force / (1 + EA * flexibility) if redundant else force
        apex = 2 * result["ix"][3]
        compare(case, "node_3_ux", "m", q / (2 * EA), result["U"][apex])
        compare(case, "node_3_uy", "m", -q * flexibility, result["U"][apex + 1])
        compare(case, "member_1_force", "N", q / 2, result["forces"][0])
        for index in (1, 2):
            compare(
                case, f"member_{index + 1}_force", "N", -q / math.sqrt(2), result["forces"][index]
            )
        for nid in (1, 2):
            compare(case, f"node_{nid}_Ry", "N", q / 2, result["R"][2 * result["ix"][nid] + 1])
        compare(case, "node_1_Rx", "N", 0.0, result["R"][2 * result["ix"][1]])
        compare(case, "strain_energy", "J", 0.5 * force * q * flexibility, result["strain_energy"])
        if redundant:
            compare(case, "member_4_force", "N", -(force - q), result["forces"][3])
            compare(case, "node_4_Ry", "N", force - q, result["R"][2 * result["ix"][4] + 1])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="CSV destination; default is standard output")
    args = parser.parse_args()
    rows = evaluate_benchmarks()
    if args.output:
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(
        f"Benchmark checks: {sum(row['passed'] for row in rows)}/{len(rows)} passed.",
        file=sys.stderr,
    )
    return 0 if all(row["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
