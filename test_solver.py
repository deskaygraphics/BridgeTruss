from model import blank, add_node, add_member, preset
from solver import solve
import pytest


def test_single_bar_2d():
    m = blank(2)
    a = add_node(m, [0, 0, 0], fix=[True, True, False])
    b = add_node(m, [2, 0, 0], fix=[False, True, False], load=[1000, 0, 0])
    add_member(m, a, b, E=200e9, A=0.01)
    r = solve(m)
    assert abs(r["U"][b][0] - 1e-6) < 1e-12
    assert abs(r["members"][1]["force"] - 1000) < 1e-6


def test_single_bar_3d():
    m = blank(3)
    a = add_node(m, [0, 0, 0], fix=[True, True, True])
    b = add_node(m, [2, 0, 0], fix=[False, True, True], load=[1000, 0, 0])
    add_member(m, a, b, E=200e9, A=0.01)
    assert abs(solve(m)["members"][1]["force"] - 1000) < 1e-6


def test_presets_2d():
    for kind in ("Pratt", "Warren", "Howe"):
        r = solve(preset(kind, 2))
        assert r["members"]


def test_finite_inputs_that_overflow_recovery_are_rejected():
    m = blank(2)
    a = add_node(m, [0, 0, 0], fix=[True, True, False])
    b = add_node(m, [1, 0, 0], fix=[False, True, False], load=[1e308, 0, 0])
    add_member(m, a, b, E=1, A=1)
    with pytest.raises(ValueError, match="overflow|Nonfinite"):
        solve(m)
