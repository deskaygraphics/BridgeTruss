"""Desktop Car/Bus geometry; numerical vehicle definitions live in traffic.py."""

import numpy as np
from visual_geometry import VehiclePart, make_truck

VEHICLE_TYPES = ("truck", "passenger", "bus")


def _add_wheels(pv, parts, spacing, radius, z_positions):
    """Wheels spin about their actual axle centres for every vehicle type."""
    scale = radius / 0.42
    for axle, x in enumerate((0.0, -spacing)):
        for side, z in zip((-1, 1), z_positions):
            origin = (x, radius, z)
            # Geometry is centred on its axle; actor rotations produce visible wheel spin.
            parts.append(
                VehiclePart(
                    pv.Cylinder(
                        center=(0, 0, 0),
                        direction=(0, 0, 1),
                        radius=radius,
                        height=0.32 * scale,
                        resolution=32,
                    ),
                    "#20252b",
                    axle,
                    origin,
                    "tire",
                )
            )
            parts.append(
                VehiclePart(
                    pv.Cylinder(
                        center=(0, 0, side * 0.18 * scale),
                        direction=(0, 0, 1),
                        radius=0.23 * scale,
                        height=0.045 * scale,
                        resolution=24,
                    ),
                    "#aab5bf",
                    axle,
                    origin,
                    "hub",
                )
            )
            parts.append(
                VehiclePart(
                    pv.Box(
                        bounds=tuple(
                            value * scale
                            for value in (
                                -0.19,
                                0.19,
                                -0.035,
                                0.035,
                                side * 0.21 - 0.01,
                                side * 0.21 + 0.01,
                            )
                        )
                    ),
                    "#394a59",
                    axle,
                    origin,
                    "spoke",
                )
            )


def make_vehicle(pv, spacing, kind="truck"):
    """Build a visual vehicle type without inventing axle forces or wheelbases."""
    kind = {"Truck": "truck", "Car": "passenger", "Bus": "bus"}.get(kind, kind)
    if kind == "truck":
        return make_truck(pv, spacing)
    if kind not in VEHICLE_TYPES:
        raise ValueError(f"Unknown vehicle type: {kind}")
    if not np.isfinite(spacing) or spacing < 0:
        raise ValueError("Axle spacing must be finite and nonnegative")
    parts = []

    def box(bounds, color, role):
        parts.append(VehiclePart(pv.Box(bounds=bounds), color, role=role))

    rear = -min(spacing, 12.0)
    if kind == "passenger":
        radius = 0.30
        cabin_back = min(rear + 0.2, -1.25)
        back = min(rear - 0.75, cabin_back - 0.35)
        box((back, 0.88, 0.38, 0.92, 1.12, 2.88), "#2678c9", "passenger_body")
        box((-0.36, 0.88, 0.92, 0.97, 1.13, 2.87), "#388bda", "hood")
        box((back, cabin_back, 0.92, 0.97, 1.13, 2.87), "#388bda", "trunk")
        # A sloping four-door cabin distinguishes the sedan from a box truck.
        profile = [
            (cabin_back, 0.92),
            (cabin_back + 0.45, 1.48),
            (-0.62, 1.48),
            (0.02, 0.92),
        ]
        points = np.array([(x, y, z) for z in (1.18, 2.82) for x, y in profile])
        faces = [
            4,
            0,
            3,
            2,
            1,
            4,
            4,
            5,
            6,
            7,
            4,
            0,
            1,
            5,
            4,
            4,
            1,
            2,
            6,
            5,
            4,
            2,
            3,
            7,
            6,
            4,
            3,
            0,
            4,
            7,
        ]
        parts.append(VehiclePart(pv.PolyData(points, faces), "#175a9e", role="passenger_cabin"))
        for z in (1.168, 2.832):
            box(
                (cabin_back + 0.5, -0.65, 1.05, 1.39, z - 0.008, z + 0.008),
                "#193747",
                "side_window",
            )
            box(
                (
                    (cabin_back - 0.15) / 2,
                    (cabin_back - 0.15) / 2 + 0.07,
                    1.01,
                    1.41,
                    z - 0.012,
                    z + 0.012,
                ),
                "#175a9e",
                "window_pillar",
            )
        # Slanted front glass follows the cabin face.
        glass = np.array(
            [
                (-0.60, 1.46, 1.25),
                (-0.60, 1.46, 2.75),
                (-0.03, 0.97, 2.75),
                (-0.03, 0.97, 1.25),
            ]
        )
        parts.append(VehiclePart(pv.PolyData(glass, [4, 0, 1, 2, 3]), "#193747", role="windshield"))
        box((0.88, 0.96, 0.42, 0.53, 1.05, 2.95), "#b7c3cb", "bumper")
        for z in (1.30, 2.70):
            box((0.885, 0.91, 0.67, 0.82, z - 0.13, z + 0.13), "#fff4c2", "headlight")
            box((back - 0.02, back, 0.65, 0.81, z - 0.14, z + 0.14), "#c62f39", "taillight")
        wheels = (1.05, 2.95)
    else:
        radius = 0.46
        back = rear - 1.35
        box((back, 1.45, 0.56, 2.80, 0.86, 3.14), "#efbe36", "bus_body")
        box((back - 0.04, 1.49, 2.80, 2.94, 0.82, 3.18), "#f5e5a1", "bus_roof")
        box((back, 1.45, 0.67, 0.82, 0.84, 3.16), "#46525a", "bus_trim")
        box((1.451, 1.47, 1.22, 2.61, 1.00, 3.00), "#183747", "windshield")
        box((1.47, 1.49, 2.63, 2.77, 1.20, 2.80), "#202c34", "destination_sign")
        edges = np.linspace(back + 0.22, 1.18, 6)
        for z in (0.845, 3.155):
            for a, b in zip(edges[:-1], edges[1:]):
                box((a + 0.06, b - 0.06, 1.42, 2.59, z - 0.008, z + 0.008), "#234857", "bus_window")
        box((0.30, 1.05, 0.85, 2.60, 3.166, 3.181), "#263c48", "bus_door")
        box((1.45, 1.55, 0.55, 0.72, 0.80, 3.20), "#aab6bf", "bumper")
        for z in (1.10, 2.90):
            box((1.47, 1.51, 0.89, 1.12, z - 0.12, z + 0.12), "#fff3bd", "headlight")
            box((back - 0.02, back, 0.88, 1.12, z - 0.12, z + 0.12), "#b62230", "taillight")
        wheels = (0.78, 3.22)
    if spacing > 12:
        box((-spacing - 0.65, -spacing + 0.65, 0.55, 0.75, 0.9, 3.1), "#aab6bf", "axle_platform")
    _add_wheels(pv, parts, spacing, radius, wheels)
    name = "passenger car" if kind == "passenger" else "bus"
    note = f"Illustrative {name}; wheel centres match the configured numerical axles."
    if spacing < 1.2 or spacing > 12:
        note += " Schematic body for an extreme axle spacing."
    return parts, radius, note
