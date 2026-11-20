"""Bounded audience scenarios; import the original solver, never a reimplementation."""

from pathlib import Path
import numpy as np

from persistence import load_model
from redundancy import redundancy_study
from run_redundancy_study import triangle_checks


ROOT = Path(__file__).resolve().parents[1]
PRESETS = {
    "Redundant bridge — remove M18": ("redundant_bridge.json", 18),
    "Redundant triangle — analytical check": ("benchmark_redundant.json", 4),
    "Determinate bridge — essential M1": ("pratt_vehicle.json", 1),
}


def run_example(preset, remaining_percent=0, moving=True, front_kN=80, rear_kN=120, spacing_m=4):
    if preset not in PRESETS:
        raise ValueError("Choose a supplied example")
    values = np.asarray([remaining_percent, front_kN, rear_kN, spacing_m], float)
    if (
        not np.all(np.isfinite(values))
        or not 0 <= remaining_percent <= 100
        or not 0 <= front_kN <= 500
        or not 0 <= rear_kN <= 500
        or not 0 <= spacing_m <= 15
        or type(moving) is not bool
    ):
        raise ValueError("Use area 0–100%, axles 0–500 kN and spacing 0–15 m")
    filename, member = PRESETS[preset]
    model, _ = load_model(ROOT / "examples" / filename)
    # The triangle's independent reference is for its prescribed static apex load.
    if filename == "benchmark_redundant.json":
        moving = False
    axles = [(0, front_kN * 1000), (spacing_m, rear_kN * 1000)] if moving else None
    factors = list(dict.fromkeys([1, 0.75, 0.5, 0.25, 0, remaining_percent / 100]))
    study = redundancy_study(model, member, factors, axles)
    study["audience_inputs"] = {
        "preset": preset,
        "remaining_percent": remaining_percent,
        "moving": moving,
        "front_kN": front_kN,
        "rear_kN": rear_kN,
        "spacing_m": spacing_m,
    }
    return study


def verification_rows():
    model, _ = load_model(ROOT / "examples" / "benchmark_redundant.json")
    return triangle_checks(redundancy_study(model, 4))
