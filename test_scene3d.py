"""Real VTK meshes/actors with a no-render plotter for portable unit tests."""

import numpy as np
import pyvista as pv
import pytest
import os
from bridge_model import Model
from scene3d import Scene3D, actor_key


class NoRenderPlotter:
    def __init__(self):
        self.meshes = []
        self.camera_position = [(1, 2, 3), (0, 0, 0), (0, 1, 0)]

    def enable_mesh_picking(self, **kwargs):
        self.picking = kwargs

    def add_mesh(self, mesh, color, pickable, **kwargs):
        actor = pv.Actor()
        actor.pickable = pickable
        actor.prop.color = color
        self.meshes.append((mesh, actor, color))
        return actor

    def clear(self):
        self.meshes.clear()

    def render(self):
        pass

    def reset_camera(self, **kwargs):
        pass

    def add_axes(self):
        pass

    def set_background(self, color):
        pass


def test_actor_mapping_highlights_and_rebuild():
    p = NoRenderPlotter()
    selected = []
    scene = Scene3D(p, pv, selected.append)
    m = Model()
    scene.render(m, reset_camera=True)
    assert p.picking["use_actor"] and not p.picking["left_clicking"]
    assert len(scene.actors[("member", 0)]) == 2
    assert len(scene.actors[("node", 6)]) == 2
    assert len(scene.actors[("load", 6)]) == 2
    actor, original = scene.actors[("member", 0)][0]
    scene._picked(actor)
    assert selected == [("member", 0)]
    scene.highlight(("member", 0), ("node", 1))
    for actor, color in scene.actors[("member", 0)]:
        assert actor.prop.color == pv.Color("#ffd84d")
    scene.highlight()
    assert scene.actors[("member", 0)][0][0].prop.color == pv.Color(original)
    stale = scene.actors[("member", 0)][0][0]
    m.members.pop()
    scene.render(m)
    assert actor_key(stale) not in scene.entities
    scene._picked(stale)
    assert len(selected) == 1
    assert ("member", 16) not in scene.actors
    assert scene.generation == 2
    assert all(
        not actor.pickable
        for mesh, actor, color in p.meshes
        if actor_key(actor) not in scene.entities
    )


def test_deformed_nodes_and_vehicle_entities():
    m = Model()
    m.solve()
    p = NoRenderPlotter()
    scene = Scene3D(p, pv, lambda entity: None)
    scene.render(m, deformed=True, vehicle=(12, 8, 80, 120, 0, 25, 0.45))
    node_actor = scene.actors[("node", 6)][0][0]
    mesh = next(mesh for mesh, actor, color in p.meshes if actor is node_actor)
    i = m.results["ix"][6]
    np.testing.assert_allclose(
        mesh.center[:2],
        np.array(m.nodes[6][:2]) + 50 * m.results["U"][2 * i : 2 * i + 2],
        atol=1e-6,
    )
    assert len(scene.actors[("axle", 0)]) >= 4
    assert len(scene.actors[("axle", 1)]) >= 4
    scene.render(m, vehicle=(27, 23, 80, 120, 0, 25, 0.45))
    assert ("axle", 0) in scene.actors
    assert ("axle", 1) in scene.actors
    assert not scene._vehicle_arrows[0].visibility
    assert scene._vehicle_arrows[1].visibility


@pytest.mark.skipif(
    os.environ.get("BRIDGETRUSS_TEST_RENDER") != "1",
    reason="Set BRIDGETRUSS_TEST_RENDER=1 on a working VTK graphics backend",
)
def test_real_right_click_picking():
    p = pv.Plotter(off_screen=True, window_size=(1000, 650))
    selected = []
    try:
        scene = Scene3D(p, pv, selected.append)
        scene.render(Model(), reset_camera=True)
        p.view_xy()
        p.reset_camera()
        p.show(auto_close=False)
        for world, expected in [
            ((2.5, 0, 4), ("member", 0)),
            ((5, 4, 4), ("node", 6)),
            ((5, 5, 4), ("load", 6)),
        ]:
            p.renderer.SetWorldPoint(*world, 1.0)
            p.renderer.WorldToDisplay()
            x, y, _ = p.renderer.GetDisplayPoint()
            p.iren.interactor.SetEventPosition(round(x), round(y))
            p.iren.interactor.InvokeEvent("RightButtonPressEvent")
            p.iren.interactor.InvokeEvent("RightButtonReleaseEvent")
            assert selected[-1] == expected
        scene.render(Model(), vehicle=(12, 8, 80, 120, 0, 25, 0.45))
        p.view_xy()
        p.reset_camera()
        p.render()
        p.renderer.SetWorldPoint(8, 0.87, 3.18, 1.0)
        p.renderer.WorldToDisplay()
        x, y, _ = p.renderer.GetDisplayPoint()
        p.iren.picker.Pick(x, y, 0, p.renderer)
        assert selected[-1] == ("axle", 1)
    finally:
        p.close()
