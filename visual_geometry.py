"""Procedural illustrative assets. Dimensions never contribute stiffness or weight."""

from dataclasses import dataclass
import numpy as np


@dataclass
class VehiclePart:
    mesh: object
    color: str
    axle: int | None = None
    wheel_origin: tuple | None = None
    role: str = "body"


VEHICLE_TYPES = ("truck", "passenger", "bus")


def make_truck(pv, spacing):
    """Local x=0 is the front axle; local y=0 is the reference road surface."""
    if not np.isfinite(spacing) or spacing < 0:
        raise ValueError("Axle spacing must be finite and nonnegative")
    parts = []
    radius = 0.42
    note = "Illustrative two-axle truck; wheel centres match the numerical axles."
    if spacing < 1.2:
        note = (
            "Compact schematic: closely spaced/coincident axles are not a realistic road vehicle."
        )
    elif spacing > 12:
        note = "Schematic axle pair: spacing exceeds the detailed truck's 12 m visual range."

    def box(bounds, color, role="body"):
        parts.append(VehiclePart(pv.Box(bounds=bounds), color, role=role))

    # Safe compact cargo shape for coincident axles; long spacing uses separate platforms.
    rear = -min(spacing, 12.0)
    cargo_back = min(rear - 0.8, -1.35)
    box((cargo_back, 0.95, 0.6, 0.88, 0.9, 3.1), "#26333f", "chassis")
    box((cargo_back, -0.85, 1.02, 2.85, 0.95, 3.05), "#dce4e9", "cargo")
    box((-0.85, -0.79, 1.05, 2.83, 0.92, 3.08), "#b4c0cb", "cargo_trim")
    box((-0.7, 0.9, 0.87, 2.5, 0.95, 3.05), "#c64632", "cab")
    box((0.9, 1.15, 1.03, 1.6, 0.95, 3.05), "#ac3428", "hood")
    box((0.906, 0.925, 1.72, 2.32, 1.08, 2.92), "#213b51", "windshield")
    for z in (0.936, 3.064):
        box((-0.57, 0.72, 1.68, 2.32, z - 0.009, z + 0.009), "#29485f", "side_window")
        box((-0.62, 0.75, 1.1, 1.14, z - 0.018, z + 0.018), "#e6b3a0", "door_trim")
    box((1.14, 1.23, 0.87, 1.05, 0.83, 3.17), "#aab4bd", "bumper")
    box((1.153, 1.175, 1.11, 1.42, 1.4, 2.6), "#26333f", "grille")
    for z in (1.15, 2.85):
        box((1.154, 1.19, 1.26, 1.48, z - 0.14, z + 0.14), "#fff3bd", "headlight")
        box((cargo_back - 0.025, cargo_back, 1.1, 1.32, z - 0.12, z + 0.12), "#a71926", "taillight")
    # Raised cargo roof and rails give highlights without external textures.
    box((cargo_back - 0.04, -0.81, 2.85, 2.93, 0.9, 3.1), "#b6c1ca", "roof")
    if spacing > 12:
        box((-spacing - 0.65, -spacing + 0.65, 0.6, 0.85, 0.9, 3.1), "#dce4e9", "axle_platform")
    _add_wheels(pv, parts, spacing, radius, (0.82, 3.18))
    return parts, radius, note


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


def make_road(pv, xmin, xmax, deck_y, approach=7.0, support_positions=None):
    """Return decorative (mesh, material, group) assets for one horizontal lane."""
    top = deck_y + 0.18
    assets = []

    def box(bounds, color, group="deck"):
        assets.append((pv.Box(bounds=bounds), color, group))

    box((xmin, xmax, top - 0.18, top, 0.16, 3.84), "#3d454e")
    for a, b in ((xmin - approach, xmin), (xmax, xmax + approach)):
        box((a, b, top - 0.22, top - 0.008, 0.16, 3.84), "#525a60")
    for z in (0.48, 3.52):
        box(
            (xmin - approach, xmax + approach, top + 0.008, top + 0.013, z - 0.025, z + 0.025),
            "#e8e8d9",
        )
    for z in (0.22, 3.78):
        # Edge beams, posts and top rails: illustrative, not structural members.
        box((xmin, xmax, top, top + 0.12, z - 0.055, z + 0.055), "#9ba6ae")
        box((xmin, xmax, top + 0.65, top + 0.71, z - 0.04, z + 0.04), "#c3ccd2")
        count = min(100, max(2, int((xmax - xmin) / 2) + 1))
        for x in np.linspace(xmin, xmax, count):
            box((x - 0.035, x + 0.035, top + 0.1, top + 0.68, z - 0.035, z + 0.035), "#9daab5")
    for x in (xmin, xmax) if support_positions is None else sorted(set(support_positions)):
        box((x - 0.6, x + 0.6, deck_y - 2.0, deck_y - 0.28, -0.28, 4.28), "#a5a098", "supports")
        for z in (0.0, 4.0):
            box(
                (x - 0.28, x + 0.28, deck_y - 0.28, deck_y - 0.08, z - 0.22, z + 0.22),
                "#343e48",
                "supports",
            )
            box(
                (x - 0.32, x + 0.32, deck_y - 0.08, deck_y - 0.015, z - 0.26, z + 0.26),
                "#b4bec8",
                "supports",
            )
    box(
        (xmin - approach, xmax + approach, deck_y - 2.22, deck_y - 2.08, -3.0, 7.0),
        "#7a8d79",
        "ground",
    )
    return assets, top
