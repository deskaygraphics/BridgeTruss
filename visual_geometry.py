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
    for axle, x in enumerate((0.0, -spacing)):
        for side, z in ((-1, 0.82), (1, 3.18)):
            origin = (x, radius, z)
            # Geometry is centred on its axle; actor rotations produce visible wheel spin.
            parts.append(
                VehiclePart(
                    pv.Cylinder(
                        center=(0, 0, 0),
                        direction=(0, 0, 1),
                        radius=radius,
                        height=0.32,
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
                        center=(0, 0, side * 0.18),
                        direction=(0, 0, 1),
                        radius=0.23,
                        height=0.045,
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
                        bounds=(-0.19, 0.19, -0.035, 0.035, side * 0.21 - 0.01, side * 0.21 + 0.01)
                    ),
                    "#394a59",
                    axle,
                    origin,
                    "spoke",
                )
            )
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
