import numpy as np
import pyvista as pv
import pytest
from visual_geometry import make_truck, make_road, make_vehicle
from bridge_model import Model
from test_scene3d import NoRenderPlotter
from scene3d import Scene3D


@pytest.mark.parametrize("spacing", [0.0, 0.1, 4.0, 15.0, 1000.0])
def test_truck_axles_and_fallbacks(spacing):
    parts, radius, note = make_truck(pv, spacing)
    tires = [part for part in parts if part.role == "tire"]
    assert len(tires) == 4
    assert {part.wheel_origin[0] for part in tires} == {0.0, -spacing}
    assert all(part.wheel_origin[1] == radius for part in tires)
    assert all(np.all(np.isfinite(part.mesh.points)) for part in parts)
    if spacing < 1.2 or spacing > 12:
        assert "schematic" in note.lower()
    assert {"cab", "windshield", "cargo", "headlight", "hub", "spoke"} <= {p.role for p in parts}


def test_road_elevation_and_support_placement():
    assets, top = make_road(pv, 0, 25, 2.0, support_positions=[5])
    assert top == pytest.approx(2.18)
    slab = assets[0][0]
    assert slab.bounds[3] == pytest.approx(top)
    supports = [mesh for mesh, color, group in assets if group == "supports"]
    assert supports and all(abs(mesh.center[0] - 5) < 1e-6 for mesh in supports)


def test_scene_reuse_motion_wheel_spin_and_visibility():
    model = Model()
    plotter = NoRenderPlotter()
    scene = Scene3D(plotter, pv, lambda entity: None)
    scene.render(model, vehicle=(12, 8, 80, 120, 0, 25, 0.18))
    generation = scene.generation
    bridge_actor = scene.actors[("member", 0)][0][0]
    wheel, part = next((a, p) for a, p in scene._vehicle_parts if p.role == "tire")
    old_orientation = wheel.orientation
    scene.render(model, vehicle=(13, 9, 80, 120, 0, 25, 0.18))
    assert scene.generation == generation
    assert scene.actors[("member", 0)][0][0] is bridge_actor
    assert wheel.position == pytest.approx(
        (13 + part.wheel_origin[0], 0.18 + 0.42, part.wheel_origin[2])
    )
    assert wheel.orientation != old_orientation
    scene.render(
        model,
        vehicle=(27, 23, 80, 120, 0, 25, 0.18),
        show_deck=False,
        show_vehicle=False,
        show_loads=True,
    )
    assert not any(a.visibility for a in scene._groups["deck"])
    assert not any(a.visibility for a in scene._groups["vehicle"])
    assert scene._vehicle_arrows[1].visibility
    assert not scene._vehicle_arrows[0].visibility
    assert scene.generation == generation
    scene.render(model, vehicle=(-1, -5, 80, 120, 0, 25, 0.18))
    assert all(a.visibility for a in scene._groups["vehicle"])
    assert not any(a.visibility for a in scene._vehicle_arrows)
    assert scene.generation == generation


def test_cache_invalidation_camera_and_colors():
    model = Model()
    scene = Scene3D(NoRenderPlotter(), pv, lambda entity: None)
    scene.render(model, vehicle=(12, 8, 80, 120, 0, 25, 0.18))
    initial = scene.generation
    model.solve()
    scene.render(model, vehicle=(13, 9, 80, 120, 0, 25, 0.18), color_by="Steel")
    assert scene.generation == initial
    assert scene.actors[("member", 0)][0][0].prop.color == pv.Color("#758b9a")
    camera = [(1, 2, 3), (4, 5, 6), (0, 1, 0)]
    scene.plotter.camera_position = camera
    scene.render(model, vehicle=(14, 10, 80, 120, 0, 25, 0.18))
    assert scene.plotter.camera_position == camera
    scene.render(model, vehicle=(15, 11, 80, 120, 0, 25, 0.18), camera_mode="Follow vehicle")
    followed = scene.plotter.camera_position
    scene.update_vehicle((16, 12, 80, 120, 0, 25, 0.18))
    assert scene.plotter.camera_position != followed
    model.members[0].A *= 2
    scene.render(model, vehicle=(16, 12, 80, 120, 0, 25, 0.18))
    assert scene.generation == initial + 1
    scene.render(model, vehicle=(16, 11, 80, 120, 0, 25, 0.18))
    assert scene.generation == initial + 2


@pytest.mark.parametrize("kind", ["passenger", "bus"])
@pytest.mark.parametrize("spacing", [0.0, 0.1, 4.0, 15.0, 1000.0])
def test_other_vehicle_types_match_axles_and_remain_finite(kind, spacing):
    parts, radius, note = make_vehicle(pv, spacing, kind)
    tires = [part for part in parts if part.role == "tire"]
    assert len(tires) == 4
    assert {part.wheel_origin[0] for part in tires} == {0, -spacing}
    assert all(part.wheel_origin[1] == radius for part in tires)
    assert all(np.all(np.isfinite(part.mesh.points)) for part in parts)
    assert all(part.mesh.n_points > 0 for part in parts)
    assert all(
        part.mesh.bounds[index] <= part.mesh.bounds[index + 1]
        for part in parts
        for index in (0, 2, 4)
    )
    roles = {part.role for part in parts}
    assert {"windshield", "headlight", "tire", "hub", "spoke"} <= roles
    assert ("passenger_body" if kind == "passenger" else "bus_body") in roles
    if spacing < 1.2 or spacing > 12:
        assert "schematic" in note.lower()


def test_passenger_car_and_bus_have_distinct_profiles():
    car, car_radius, _ = make_vehicle(pv, 4, "passenger")
    bus, bus_radius, _ = make_vehicle(pv, 4, "bus")
    assert max(part.mesh.bounds[3] for part in car) < max(part.mesh.bounds[3] for part in bus)
    assert car_radius < bus_radius
    assert len([part for part in bus if part.role == "bus_window"]) == 10
    assert "cargo" not in {part.role for part in car + bus}
    with pytest.raises(ValueError, match="Unknown vehicle"):
        make_vehicle(pv, 4, "unknown")


def test_mixed_convoy_wheel_spin_and_axle_alignment():
    scene = Scene3D(NoRenderPlotter(), pv, lambda entity: None)
    scene.render(Model(), vehicle=(22, 18, 80, 120, 0, 25, 0.18, 3, 4))
    generation = scene.generation
    tires = [(actor, part) for actor, part in scene._vehicle_parts if part.role == "tire"]
    assert len(tires) == 12
    old = [(actor, actor.orientation[2]) for actor, _ in tires]
    assert {round(actor.position[1] - 0.18, 2) for actor, _ in tires} == {0.30, 0.42, 0.46}
    assert sorted({round(actor.position[0], 6) for actor, _ in tires}) == [2, 6, 10, 14, 18, 22]
    scene.update_vehicle((23, 19, 80, 120, 0, 25, 0.18, 3, 4))
    assert scene.generation == generation
    for (actor, part), (_, angle) in zip(tires, old):
        radius = part.wheel_origin[1]
        assert (actor.orientation[2] - angle) % 360 == pytest.approx(-np.degrees(1 / radius) % 360)
        assert actor.position[1] == pytest.approx(0.18 + radius)


def test_numpy_deck_bounds_are_safe_vtk_visibility_flags():
    scene = Scene3D(NoRenderPlotter(), pv, lambda entity: None)
    scene.render(Model(), vehicle=(12.0, 8.0, 80.0, 120.0, np.float64(0), np.float64(25), 0.18))
    assert all(actor.visibility for actor in scene._vehicle_arrows)
    scene.update_vehicle((27.0, 23.0, 80.0, 120.0, np.float64(0), np.float64(25), 0.18))
    assert not scene._vehicle_arrows[0].visibility
    assert scene._vehicle_arrows[1].visibility
