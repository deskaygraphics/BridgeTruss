import pytest
from verify_benchmarks import evaluate_benchmarks


def test_benchmark_report_matches_all_three_hand_solutions():
    rows = evaluate_benchmarks()
    assert {row["benchmark"] for row in rows} == {
        "axial_bar",
        "determinate_triangle",
        "redundant_triangle",
    }
    assert all(row["passed"] for row in rows)
    bar = next(row for row in rows if row["response"] == "node_1_ux")
    assert bar["reference"] == pytest.approx(1e-6)
    zeros = [row for row in rows if row["reference"] == 0]
    assert zeros and all(row["relative_error_percent"] == "" for row in zeros)
