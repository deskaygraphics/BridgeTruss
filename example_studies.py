"""Shared desktop/web examples and independent triangle verification."""

from pathlib import Path
import numpy as np

from persistence import load_model
from redundancy import redundancy_study
from run_redundancy_study import triangle_checks
from moving_loads import convoy_axles


ROOT = Path(__file__).resolve().parent
PRESETS = {
    "Redundant bridge — remove M18": ("redundant_bridge.json", 18),
    "Redundant triangle — analytical check": ("benchmark_redundant.json", 4),
    "Determinate bridge — essential M1": ("pratt_vehicle.json", 1),
}


def vehicle_example(
    preset, moving=True, front_kN=80, rear_kN=120, spacing_m=4, vehicle_count=1, vehicle_gap_m=4
):
    """Load a supplied reference and its full convoy axle list, without modifying it."""
    if preset not in PRESETS:
        raise ValueError("Choose a supplied example")
    values = np.asarray([front_kN, rear_kN, spacing_m, vehicle_gap_m], float)
    if (
        not np.all(np.isfinite(values))
        or not 0 <= front_kN <= 500
        or not 0 <= rear_kN <= 500
        or not 0 <= spacing_m <= 15
        or not 0 <= vehicle_gap_m <= 1000
        or type(moving) is not bool
    ):
        raise ValueError("Use axles 0–500 kN, spacing 0–15 m and vehicle gap 0–1000 m")
    axles = convoy_axles(front_kN * 1000, rear_kN * 1000, spacing_m, vehicle_count, vehicle_gap_m)
    filename, _ = PRESETS[preset]
    model, _ = load_model(ROOT / "examples" / filename)
    # The triangle's independent reference is for its prescribed static apex load.
    if filename == "benchmark_redundant.json":
        moving = False
    return model, axles if moving else None


def run_example(
    preset,
    remaining_percent=0,
    moving=True,
    front_kN=80,
    rear_kN=120,
    spacing_m=4,
    vehicle_count=1,
    vehicle_gap_m=4,
):
    if not np.isfinite(remaining_percent) or not 0 <= remaining_percent <= 100:
        raise ValueError("Use area remaining 0–100%")
    model, axles = vehicle_example(
        preset, moving, front_kN, rear_kN, spacing_m, vehicle_count, vehicle_gap_m
    )
    member = PRESETS[preset][1]
    factors = list(dict.fromkeys([1, 0.75, 0.5, 0.25, 0, remaining_percent / 100]))
    study = redundancy_study(model, member, factors, axles)
    study["audience_inputs"] = {
        "preset": preset,
        "remaining_percent": remaining_percent,
        "moving": axles is not None,
        "front_kN": front_kN,
        "rear_kN": rear_kN,
        "spacing_m": spacing_m,
        "vehicle_count": vehicle_count,
        "vehicle_gap_m": vehicle_gap_m,
    }
    return study


def verification_rows():
    model, _ = load_model(ROOT / "examples" / "benchmark_redundant.json")
    return triangle_checks(redundancy_study(model, 4))
