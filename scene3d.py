"""Illustrative geometry and actor picking; entity IDs refer to the planar model."""

import numpy as np
from moving_loads import deck_path
from visual_geometry import make_truck, make_road


def actor_key(actor):
    """VTK wrappers for the same actor can be different Python objects."""
    return actor.GetAddressAsString("")


class Scene3D:
    def __init__(self, plotter, geometry, on_select):
        self.plotter = plotter
        self.pv = geometry
        self.on_select = on_select
        self.entities = {}
        self.actors = {}
        self.selected = None
        self.anchor = None
        self.generation = 0
        self._signature = None
        self._groups = {}
        self._vehicle_parts = []
        self._vehicle_arrows = []
        self._camera_mode = "Isometric"
        self._fit_bounds = None
        self._last_vehicle = None
        self._show_options = (True, True, True)
        self.vehicle_note = ""
        self.wheel_radius = 0.42
        plotter.enable_mesh_picking(
            callback=self._picked,
            use_actor=True,
            show=False,
            show_message=False,
            left_clicking=False,
            picker="hardware",
        )

    def _picked(self, actor):
        entity = self.entities.get(actor_key(actor)) if actor is not None else None
        if entity is not None:
            self.on_select(entity)

    def add(self, mesh, color, entity=None, group=None, **kwargs):
        actor = self.plotter.add_mesh(
            mesh,
            color=color,
            pickable=entity is not None,
            smooth_shading=True,
            split_sharp_edges=True,
            specular=0.25,
            specular_power=30,
            ambient=0.22,
            **kwargs,
        )
        if group is not None:
            self._groups.setdefault(group, []).append(actor)
        if entity is not None:
            self.entities[actor_key(actor)] = entity
            self.actors.setdefault(entity, []).append((actor, color))
        return actor

    def highlight(self, selected=None, anchor=None, *, render=True):
        self.selected, self.anchor = selected, anchor
        for entity, actors in self.actors.items():
            for actor, color in actors:
                actor.prop.color = (
                    "#ffd84d" if entity == selected else ("#5affb0" if entity == anchor else color)
                )
        if render:
            self.plotter.render()

    @staticmethod
    def signature(model, deformed, vehicle):
        return (
            tuple((n, tuple(p)) for n, p in sorted(model.nodes.items())),
            tuple((m.a, m.b, m.A, m.E) for m in model.members),
            tuple(sorted(model.fixed.items())),
            tuple(sorted(model.loads.items())),
            tuple(model.deck_nodes),
            deformed,
            tuple(model.results["U"]) if deformed and model.results is not None else None,
            None if vehicle is None else (round(vehicle[0] - vehicle[1], 9), *vehicle[4:]),
        )

    def _member_colors(self, model, color_by):
        for index, _ in enumerate(model.members):
            values = model.results
            value = (
                0.0
                if values is None
                else values["stresses" if color_by == "Stress" else "forces"][index]
            )
            color = (
                "#758b9a"
                if color_by in ("Uniform", "Steel")
                else ("#e9534f" if value > 1e-8 else "#337dd7" if value < -1e-8 else "#9baec1")
            )
            self.actors[("member", index)] = [
                (actor, color) for actor, _ in self.actors.get(("member", index), [])
            ]

    def _build_vehicle(self, spacing):
        parts, self.wheel_radius, self.vehicle_note = make_truck(self.pv, spacing)
        for part in parts:
            entity = ("axle", part.axle) if part.axle is not None else None
            actor = self.add(part.mesh, part.color, entity, group="vehicle")
            self._vehicle_parts.append((actor, part))
        for axle in (0, 1):
            actor = self.add(
                self.pv.Arrow(
                    start=(0, 4.3, 3.5),
                    direction=(0, -1, 0),
                    scale=4.1,
                    shaft_radius=0.025,
                    tip_length=0.18,
                ),
                "#ed5638",
                ("axle", axle),
                group="loads",
            )
            self._vehicle_arrows.append(actor)

    def update_vehicle(self, vehicle, *, render=True):
        """Move existing actors without rebuilding geometry or invalidating picking."""
        self._last_vehicle = vehicle
        show_deck, show_vehicle, show_loads = self._show_options
        for group in ("deck", "supports", "ground"):
            for actor in self._groups.get(group, []):
                actor.visibility = show_deck
        for actor in self._groups.get("loads", []):
            actor.visibility = show_loads
        for actor in self._groups.get("vehicle", []):
            actor.visibility = show_vehicle and vehicle is not None
        if vehicle is not None:
            front, rear, front_force, rear_force, xmin, xmax, top = vehicle
            angle = -np.degrees((front - xmin) / self.wheel_radius) % 360.0
            for actor, part in self._vehicle_parts:
                if part.wheel_origin is None:
                    actor.position = (front, top, 0.0)
                else:
                    x, y, z = part.wheel_origin
                    actor.position = (front + x, top + y, z)
                    actor.orientation = (0.0, 0.0, angle)
            for actor, x, force in zip(
                self._vehicle_arrows, (front, rear), (front_force, rear_force)
            ):
                actor.position = (x, top, 0.0)
                actor.visibility = bool(show_loads and force > 0 and xmin <= x <= xmax)
            if self._camera_mode == "Follow vehicle":
                self._follow_camera(vehicle)
        if render:
            self.plotter.render()

    def _follow_camera(self, vehicle):
        front, rear, *_, top = vehicle
        target = (front - min((front - rear) * 0.4, 4.0), top + 1.3, 2.0)
        self.plotter.camera_position = [(target[0] + 8.0, top + 5.5, 11.0), target, (0.0, 1.0, 0.0)]
        camera = getattr(self.plotter, "camera", None)
        if camera is not None:
            camera.view_angle = 35.0

    def set_camera(self, mode):
        self._camera_mode = mode
        if mode == "Follow vehicle" and self._last_vehicle is not None:
            self._follow_camera(self._last_vehicle)
        elif mode in ("Isometric", "Side") and self._fit_bounds is not None:
            a, b, c, d, _, _ = self._fit_bounds
            x, y, span = (a + b) / 2, (c + d) / 2, max(b - a, 5.0)
            offset = (
                (span * 0.18, span * 0.28, span * 0.9) if mode == "Isometric" else (0.0, 0.0, span)
            )
            self.plotter.camera_position = [
                (x + offset[0], y + offset[1], 2.0 + offset[2]),
                (x, y, 2.0),
                (0.0, 1.0, 0.0),
            ]
            self.fit()

    def fit(self):
        kwargs = {"bounds": self._fit_bounds} if self._fit_bounds is not None else {}
        self.plotter.reset_camera(**kwargs)
        # Fit projected geometry, not just a bounding sphere, in wide Qt viewports.
        renderer = getattr(self.plotter, "renderer", None)
        if renderer is not None and hasattr(renderer, "ResetCameraScreenSpace"):
            if self._fit_bounds is None:
                renderer.ResetCameraScreenSpace()
            else:
                renderer.ResetCameraScreenSpace(self._fit_bounds)
        self.plotter.render()

    def render(
        self,
        model,
        *,
        deformed=False,
        color_by="Axial Force",
        vehicle=None,
        reset_camera=False,
        show_deck=True,
        show_vehicle=True,
        show_loads=True,
        camera_mode="Isometric",
    ):
        p, pv = self.plotter, self.pv
        self._show_options = (show_deck, show_vehicle, show_loads)
        signature = self.signature(model, deformed, vehicle)
        camera_changed = camera_mode != self._camera_mode
        if signature == self._signature:
            self._member_colors(model, color_by)
            self.update_vehicle(vehicle, render=False)
            self.highlight(self.selected, self.anchor, render=False)
            if reset_camera or camera_changed:
                self.set_camera(camera_mode)
            p.render()
            return
        self._signature = signature
        self.generation += 1
        camera = p.camera_position if not reset_camera else None
        p.clear()
        self.entities.clear()
        self.actors.clear()
        self._groups.clear()
        self._vehicle_parts.clear()
        self._vehicle_arrows.clear()
        self.vehicle_note = ""
        result = model.results

        def point(nid, side):
            xyz = np.array(model.nodes[nid], dtype=float)
            xyz[2] = side
            if deformed and result is not None:
                index = 2 * result["ix"][nid]
                xyz[:2] += 50.0 * result["U"][index : index + 2]
            return xyz

        if model.nodes:
            approach = (
                max(7.0, min(15.0, vehicle[0] - vehicle[1] + 1.0)) if vehicle is not None else 7.0
            )
            coords = np.array(list(model.nodes.values()), float)
            span = max(float(np.ptp(coords[:, 0])), float(np.ptp(coords[:, 1])), 1.0)
        else:
            span = 25.0
        if model.nodes:
            self._fit_bounds = (
                float(coords[:, 0].min()) - approach,
                float(coords[:, 0].max()) + approach,
                float(coords[:, 1].min()) - 2.3,
                float(coords[:, 1].max()) + 2.0,
                -0.3,
                4.3,
            )
        else:
            self._fit_bounds = (0.0, 25.0, -2.0, 6.0, 0.0, 4.0)
        radius = max(span * 0.003, 0.015)
        arrow_length = max(span * 0.06, 0.25)
        for side in (0.0, 4.0):
            for index, member in enumerate(model.members):
                value = (
                    0
                    if result is None
                    else result["stresses" if color_by == "Stress" else "forces"][index]
                )
                color = (
                    "#4b91de"
                    if color_by == "Uniform"
                    else ("#e9534f" if value > 1e-8 else "#337dd7" if value < -1e-8 else "#9baec1")
                )
                self.add(
                    pv.Line(point(member.a, side), point(member.b, side)).tube(radius=radius),
                    color,
                    ("member", index),
                )
            for nid in model.nodes:
                self.add(
                    pv.Sphere(radius=radius * 1.9, center=point(nid, side)),
                    "#ecf3ff",
                    ("node", nid),
                )
            for nid, (fx, fy) in model.loads.items():
                magnitude = float(np.hypot(fx, fy))
                if not magnitude:
                    continue
                direction = np.array([fx, fy, 0.0]) / magnitude
                tip = point(nid, side)
                self.add(
                    pv.Arrow(
                        start=tip - direction * arrow_length,
                        direction=direction,
                        scale=arrow_length,
                        shaft_radius=0.035,
                    ),
                    "#d52b45",
                    ("load", nid),
                    group="loads",
                )
        # Decorative ties and truck parts deliberately cannot be selected.
        for nid in model.deck_nodes:
            if nid in model.nodes:
                self.add(
                    pv.Line(point(nid, 0.0), point(nid, 4.0)).tube(radius=radius * 0.7), "#9aa9b9"
                )
        try:
            deck, xs = deck_path(model)
            supports = [model.nodes[n][0] for n in deck if any(model.fixed.get(n, (False, False)))]
            for mesh, color, group in make_road(
                pv,
                xs[0],
                xs[-1],
                model.nodes[deck[0]][1],
                approach=approach,
                support_positions=supports,
            )[0]:
                self.add(mesh, color, group=group)
        except ValueError:
            pass  # No invented roadway for an invalid or absent deck path.
        if vehicle is not None and model.nodes:
            self._build_vehicle(vehicle[0] - vehicle[1])
        p.add_axes()
        p.set_background("#a8c7e8")
        self._member_colors(model, color_by)
        self.update_vehicle(vehicle, render=False)
        if camera is None or camera_changed:
            self.set_camera(camera_mode)
        else:
            p.camera_position = camera
        if self._camera_mode == "Follow vehicle" and vehicle is not None:
            self._follow_camera(vehicle)
        self.highlight(self.selected, self.anchor)
