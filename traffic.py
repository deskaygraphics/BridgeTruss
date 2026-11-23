"""Fixed-spacing, same-direction traffic; axle forces remain quasi-static inputs."""

from copy import deepcopy
from math import isfinite, isclose
from numbers import Real


PRESETS = {
    "Truck": {"front_N": 80000.0, "rear_N": 120000.0, "spacing_m": 4.0},
    "Car": {"front_N": 8000.0, "rear_N": 7000.0, "spacing_m": 2.7},
    "Bus": {"front_N": 50000.0, "rear_N": 90000.0, "spacing_m": 6.0},
}
LEGACY_FIELDS = {"enabled", "front_N", "rear_N", "spacing_m", "position_fraction"}
TRAFFIC_FIELDS = {"enabled", "position_fraction", "vehicles"}
VEHICLE_FIELDS = {"kind", "front_N", "rear_N", "spacing_m", "gap_m"}


def traffic_scenario(scenario):
    return isinstance(scenario, dict) and "vehicles" in scenario


def bounded(value, name, low, high):
    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
        or not low <= value <= high
        or not isfinite(value)
    ):
        raise ValueError(f"{name} must be finite and between {low:g} and {high:g}")


def preset_vehicle(kind="Car", gap_m=0.0):
    if not isinstance(kind, str) or kind not in PRESETS:
        raise ValueError("Choose Car, Bus or Truck")
    return {"kind": kind, **PRESETS[kind], "gap_m": float(gap_m)}


def validate_scenario(scenario):
    """Validate without mutating inputs or coercing malformed JSON."""
    if not isinstance(scenario, dict):
        raise ValueError("Scenario must be an object")
    if not scenario:
        return {}
    fields = TRAFFIC_FIELDS if traffic_scenario(scenario) else LEGACY_FIELDS
    if set(scenario) != fields:
        raise ValueError("Invalid vehicle scenario fields")
    if type(scenario["enabled"]) is not bool:
        raise ValueError("Moving-load enabled state must be boolean")
    bounded(scenario["position_fraction"], "Position fraction", 0, 1)
    if not traffic_scenario(scenario):
        bounded(scenario["front_N"], "Front axle force (N)", 0, 1e8)
        bounded(scenario["rear_N"], "Rear axle force (N)", 0, 1e8)
        bounded(scenario["spacing_m"], "Axle spacing (m)", 0, 1000)
        return deepcopy(scenario)
    vehicles = scenario["vehicles"]
    if not isinstance(vehicles, list) or not 1 <= len(vehicles) <= 3:
        raise ValueError("Traffic requires one, two or three vehicles")
    for i, vehicle in enumerate(vehicles):
        if not isinstance(vehicle, dict) or set(vehicle) != VEHICLE_FIELDS:
            raise ValueError(f"Vehicle {i + 1}: invalid fields")
        if not isinstance(vehicle["kind"], str) or vehicle["kind"] not in PRESETS:
            raise ValueError(f"Vehicle {i + 1}: choose Car, Bus or Truck")
        bounded(vehicle["front_N"], f"Vehicle {i + 1} front force (N)", 0, 1e8)
        bounded(vehicle["rear_N"], f"Vehicle {i + 1} rear force (N)", 0, 1e8)
        bounded(vehicle["spacing_m"], f"Vehicle {i + 1} wheelbase (m)", 1.2, 1000)
        bounded(
            vehicle["gap_m"],
            f"Vehicle {i + 1} rear-to-front axle gap (m)",
            0 if i == 0 else 2,
            0 if i == 0 else 1000,
        )
    return deepcopy(scenario)


def validate_control_precision(scenario):
    """Reject settings that either UI would otherwise silently round."""
    if not scenario:
        return
    groups = (
        [(f"Vehicle {i + 1} ", vehicle) for i, vehicle in enumerate(scenario["vehicles"])]
        if traffic_scenario(scenario)
        else [("", scenario)]
    )
    for prefix, values in [("", {"position_fraction": scenario["position_fraction"]}), *groups]:
        for key, divisor, decimals in [
            ("front_N", 1000, 2),
            ("rear_N", 1000, 2),
            ("spacing_m", 1, 2),
            ("gap_m", 1, 2),
            ("position_fraction", 1, 3),
        ]:
            if key not in values:
                continue
            value = values[key] / divisor
            if not isclose(value, round(value, decimals), rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"{prefix}{key} exceeds control precision; adjust it explicitly")


def positioned_vehicles(scenario):
    """Vehicle fronts trail the leading front by accumulated wheelbases + gaps."""
    validate_scenario(scenario)
    if not scenario:
        return []
    vehicles = (
        scenario["vehicles"]
        if traffic_scenario(scenario)
        else [
            {
                "kind": "Truck",
                "front_N": scenario["front_N"],
                "rear_N": scenario["rear_N"],
                "spacing_m": scenario["spacing_m"],
                "gap_m": 0.0,
            }
        ]
    )
    output = []
    offset = 0.0
    for i, vehicle in enumerate(vehicles):
        if i:
            offset += vehicles[i - 1]["spacing_m"] + vehicle["gap_m"]
        output.append({**deepcopy(vehicle), "front_offset_m": float(offset)})
    return output


def scenario_axles(scenario):
    """Flatten the complete traffic into the existing moving_loads axle contract."""
    return [
        (vehicle["front_offset_m"] + offset, vehicle[key])
        for vehicle in positioned_vehicles(scenario)
        for offset, key in ((0.0, "front_N"), (vehicle["spacing_m"], "rear_N"))
    ]
