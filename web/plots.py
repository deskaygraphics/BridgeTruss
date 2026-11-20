"""Browser-native views of the shared planar model; geometry is illustrative."""

import io

import numpy as np
import plotly.graph_objects as go
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from moving_loads import deck_path


BACKGROUND = "#19232e"
PANEL = "#202e3d"
TEXT = "#edf2f8"
CONFIG = {
    "scrollZoom": True,
    "displaylogo": False,
    "toImageButtonOptions": {"format": "png", "scale": 2},
}


def base_layout(fig, title, fit=0):
    fig.update_layout(
        title={"text": title, "font": {"size": 16}},
        template="plotly_dark",
        paper_bgcolor=BACKGROUND,
        plot_bgcolor=PANEL,
        font={"color": TEXT},
        margin={"l": 30, "r": 20, "t": 45, "b": 30},
        height=450,
        showlegend=False,
        uirevision=str(fit),
    )
    return fig


def coordinates(model, magnification=0):
    points = {n: np.array(p, float).copy() for n, p in model.nodes.items()}
    if model.results is not None and magnification:
        for i, nid in enumerate(model.results["ids"]):
            points[nid][:2] += model.results["U"][2 * i : 2 * i + 2] * magnification
    return points


def member_color(model, index, color_by):
    if color_by == "Steel" or model.results is None:
        return "#9eaebd"
    key = "stresses" if color_by == "Stress" else "forces"
    values = model.results[key]
    value = values[index]
    if abs(value) < max(float(max(abs(values))), 1) * 1e-8:
        return "#c3cbd4"
    # Signed magnitude, independently normalized for force and stress.
    weight = min(1.0, abs(value) / max(float(max(abs(values))), 1e-12))
    neutral = np.array([195, 203, 212])
    endpoint = np.array([239, 102, 89] if value > 0 else [72, 153, 236])
    rgb = np.rint(neutral * (1 - weight) + endpoint * weight).astype(int)
    return f"rgb({rgb[0]},{rgb[1]},{rgb[2]})"


def member_text(model, index):
    m = model.members[index]
    text = f"M{index + 1} · {m.a}–{m.b}<br>A = {m.A:.6g} m² · E = {m.E / 1e9:g} GPa"
    if model.results is not None:
        r = model.results
        text += f"<br>N = {r['forces'][index] / 1000:.6g} kN"
        text += f"<br>σ = {r['stresses'][index] / 1e6:.6g} MPa"
    return text


def diagram(model, mode="geometry", labels=True, scale=1.0, fit=0, selection=None):
    fig = go.Figure()
    magnification = 50 if mode == "deformed" else 0
    points = coordinates(model, magnification)
    if mode == "deformed" and model.results is not None:
        for m in model.members:
            a, b = model.nodes[m.a], model.nodes[m.b]
            fig.add_trace(
                go.Scatter(
                    x=[a[0], b[0]],
                    y=[a[1], b[1]],
                    mode="lines",
                    line={"color": "#6c7b89", "width": 1, "dash": "dot"},
                    hoverinfo="skip",
                )
            )
    for i, m in enumerate(model.members):
        a, b = points[m.a], points[m.b]
        color = member_color(model, i, "Axial Force" if mode == "force" else "Steel")
        if selection == ("member", i + 1):
            color = "#ffd166"
        fig.add_trace(
            go.Scatter(
                x=[a[0], b[0]],
                y=[a[1], b[1]],
                mode="lines",
                line={"color": color, "width": 4},
                text=member_text(model, i),
                hovertemplate="%{text}<extra></extra>",
            )
        )
        if mode == "force" and model.results is not None:
            fig.add_annotation(
                x=(a[0] + b[0]) / 2,
                y=(a[1] + b[1]) / 2,
                text=f"{model.results['forces'][i] / 1000:.1f}",
                showarrow=False,
                yshift=10,
                font={"size": 10 * scale},
            )
    ids = sorted(points)
    fig.add_trace(
        go.Scatter(
            x=[points[n][0] for n in ids],
            y=[points[n][1] for n in ids],
            mode="markers+text" if labels else "markers",
            text=[str(n) for n in ids],
            textposition="top center",
            textfont={"size": 12 * scale},
            marker={
                "size": 8,
                "color": ["#ffd166" if selection == ("node", n) else "#e7f0f7" for n in ids],
            },
            hovertemplate="Node %{text}<br>x=%{x:.4g} m<br>y=%{y:.4g} m<extra></extra>",
        )
    )
    for nid, fixed in model.fixed.items():
        if not any(fixed):
            continue
        x, y = points[nid][:2]
        kind = "Pin" if all(fixed) else "Vertical roller" if fixed[1] else "Horizontal roller"
        fig.add_trace(
            go.Scatter(
                x=[x],
                y=[y],
                mode="markers",
                marker={"size": 20, "symbol": "triangle-up", "color": "#87c4a2"},
                text=kind,
                hovertemplate="%{text}<extra></extra>",
            )
        )
        if not all(fixed):
            fig.add_annotation(x=x, y=y, text="○○", showarrow=False, yshift=-23)
    loads = model.display_loads if model.display_loads is not None else model.loads
    if points:
        span = max(np.ptp([p[0] for p in points.values()]), 1)
        for nid, (fx, fy) in loads.items():
            if not fx and not fy:
                continue
            x, y = points[nid][:2]
            norm = max(np.hypot(fx, fy), 1)
            fig.add_annotation(
                x=x,
                y=y,
                ax=x - fx / norm * span * 0.08,
                ay=y - fy / norm * span * 0.08,
                axref="x",
                ayref="y",
                text=f"({fx / 1000:g}, {fy / 1000:g}) kN",
                arrowhead=3,
                arrowwidth=2,
                arrowcolor="#f1bd62",
                font={"size": 11 * scale, "color": "#f1bd62"},
            )
    title = {
        "geometry": "2D View · geometry / supports / loads",
        "force": "Axial Forces · kN · red tension / blue compression",
        "deformed": "Deformation ×50 · dotted = undeformed",
    }[mode]
    if mode != "geometry" and model.results is None:
        title += " · analyze to display results"
    base_layout(fig, title, fit)
    fig.update_xaxes(title="x (m)", gridcolor="#354657")
    fig.update_yaxes(title="y (m)", scaleanchor="x", scaleratio=1, gridcolor="#354657")
    fig.update_layout(dragmode="pan", font={"size": 12 * scale})
    return fig


def box(fig, bounds, color):
    x0, x1, y0, y1, z0, z1 = bounds
    fig.add_trace(
        go.Mesh3d(
            x=[x0, x1, x1, x0, x0, x1, x1, x0],
            y=[y0, y0, y1, y1, y0, y0, y1, y1],
            z=[z0, z0, z0, z0, z1, z1, z1, z1],
            i=[0, 0, 4, 4, 0, 0, 1, 1, 2, 2, 3, 3],
            j=[1, 2, 5, 6, 1, 5, 2, 6, 3, 7, 0, 4],
            k=[2, 3, 6, 7, 5, 4, 6, 5, 7, 6, 4, 7],
            color=color,
            flatshading=True,
            hoverinfo="skip",
        )
    )


def wheel(fig, x, lane, height, rotation):
    theta = np.linspace(0, 2 * np.pi, 21)
    xx = x + 0.42 * np.cos(theta)
    zz = height + 0.42 * np.sin(theta)
    fig.add_trace(
        go.Surface(
            x=np.vstack([xx, xx]),
            y=np.vstack([np.full(21, lane - 0.12), np.full(21, lane + 0.12)]),
            z=np.vstack([zz, zz]),
            colorscale=[[0, "#20252b"], [1, "#20252b"]],
            showscale=False,
            hoverinfo="skip",
        )
    )
    fig.add_trace(
        go.Scatter3d(
            x=[x - 0.3 * np.cos(rotation), x + 0.3 * np.cos(rotation)],
            y=[lane + 0.14, lane + 0.14],
            z=[height - 0.3 * np.sin(rotation), height + 0.3 * np.sin(rotation)],
            mode="lines",
            line={"color": "#aab5bf", "width": 5},
            hoverinfo="skip",
        )
    )


def truck_mesh(front, spacing, top):
    """One GPU mesh; wheel vertex ranges allow client-side rolling transforms."""
    parts = go.Figure()
    rear = -min(spacing, 12) - 0.7
    box(parts, (rear, 0.8, 0.9, 3.1, top + 0.55, top + 0.85), "#26333f")
    box(parts, (-0.7, 0.9, 0.9, 3.1, top + 0.85, top + 2.5), "#c64632")
    box(parts, (rear, -0.85, 0.95, 3.05, top + 0.9, top + 2.85), "#dce4e9")
    box(parts, (0.91, 0.94, 1.1, 2.9, top + 1.7, top + 2.3), "#29485f")
    vertices = {k: [] for k in ("x", "y", "z", "i", "j", "k", "vertexcolor")}

    def append(mesh):
        offset = len(vertices["x"])
        for axis in ("x", "y", "z"):
            vertices[axis].extend(getattr(mesh, axis))
        for axis in ("i", "j", "k"):
            vertices[axis].extend(int(i) + offset for i in getattr(mesh, axis))
        vertices["vertexcolor"].extend([mesh.color] * len(mesh.x))

    for mesh in parts.data:
        append(mesh)
    wheels = []
    for x in (0.0, -spacing):
        for lane in (0.8, 3.2):
            start = len(vertices["x"])
            n = 16
            angles = np.arange(n) * 2 * np.pi / n
            faces = []
            for i in range(n):
                j = (i + 1) % n
                faces.extend(
                    [(i, j, i + n), (j, j + n, i + n), (2 * n, j, i), (2 * n + 1, i + n, j + n)]
                )
            append(
                go.Mesh3d(
                    x=[*(x + 0.42 * np.cos(angles)), *(x + 0.42 * np.cos(angles)), x, x],
                    y=[*[lane - 0.12] * n, *[lane + 0.12] * n, lane - 0.12, lane + 0.12],
                    z=[
                        *(top + 0.42 + 0.42 * np.sin(angles)),
                        *(top + 0.42 + 0.42 * np.sin(angles)),
                        top + 0.42,
                        top + 0.42,
                    ],
                    i=[f[0] for f in faces],
                    j=[f[1] for f in faces],
                    k=[f[2] for f in faces],
                    color="#20252b",
                )
            )
            spoke = go.Figure()
            box(
                spoke,
                (x - 0.3, x + 0.3, lane + 0.125, lane + 0.15, top + 0.385, top + 0.455),
                "#aab5bf",
            )
            append(spoke.data[0])
            wheels.append({"start": start, "stop": len(vertices["x"]), "x": x, "z": top + 0.42})
    vertices["x"] = [x + front for x in vertices["x"]]
    return go.Mesh3d(
        **vertices,
        flatshading=True,
        hoverinfo="skip",
        meta={"role": "vehicle", "front": front, "wheels": wheels},
    )


def scene(
    workspace,
    color_by="Axial Force",
    labels=True,
    deformed=False,
    show_deck=True,
    show_vehicle=True,
    show_loads=True,
    camera="Isometric",
    fit=0,
):
    m = workspace.model
    fig = go.Figure()
    points = coordinates(m, 50 if deformed else 0)
    members = {k: [] for k in ("x", "y", "z", "text", "color")}
    for side in (0.0, 4.0):
        for i, member in enumerate(m.members):
            a, b = points[member.a], points[member.b]
            color = member_color(m, i, color_by)
            if workspace.selection == ("member", i + 1):
                color = "#ffd166"
            members["x"].extend([a[0], b[0], None])
            members["y"].extend([side, side, None])
            members["z"].extend([a[1], b[1], None])
            members["text"].extend([member_text(m, i)] * 3)
            members["color"].extend([color] * 3)
        ids = sorted(points)
        fig.add_trace(
            go.Scatter3d(
                x=[points[n][0] for n in ids],
                y=[side] * len(ids),
                z=[points[n][1] for n in ids],
                text=[str(n) for n in ids],
                mode="markers+text" if labels else "markers",
                marker={
                    "size": 4,
                    "color": [
                        "#ffd166" if workspace.selection == ("node", n) else "#dde5ed" for n in ids
                    ],
                },
                textposition="top center",
                hovertemplate="Node %{text}<extra></extra>",
            )
        )
    fig.add_trace(
        go.Scatter3d(
            x=members["x"],
            y=members["y"],
            z=members["z"],
            text=members["text"],
            mode="lines",
            line={"width": 9, "color": members["color"]},
            hovertemplate="%{text}<extra></extra>",
            meta={"role": "members"},
        )
    )
    if points:
        # The duplicate side and cross ties are decorative, never additional members.
        fig.add_trace(
            go.Scatter3d(
                x=[x for p in points.values() for x in (p[0], p[0], None)],
                y=[y for p in points.values() for y in (0, 4, None)],
                z=[z for p in points.values() for z in (p[1], p[1], None)],
                mode="lines",
                line={"color": "#687d90", "width": 3},
                hoverinfo="skip",
            )
        )
        try:
            deck, xs = deck_path(m)
            xmin, xmax, elevation = xs[0], xs[-1], m.nodes[deck[0]][1]
        except ValueError:
            xmin, xmax = min(p[0] for p in points.values()), max(p[0] for p in points.values())
            elevation = min(p[1] for p in points.values())
        top = elevation + 0.18
        if show_deck:
            box(fig, (xmin, xmax, 0.15, 3.85, elevation, top), "#46525b")
            for x in sorted({m.nodes[n][0] for n, fix in m.fixed.items() if any(fix)}):
                box(fig, (x - 0.5, x + 0.5, -0.3, 4.3, elevation - 1.7, elevation - 0.2), "#a5a098")
            for y in (0.35, 3.65):
                box(fig, (xmin, xmax, y - 0.03, y + 0.03, top, top + 0.02), "#e9e8d9")
        if show_vehicle and workspace.scenario["enabled"]:
            front = workspace.position
            spacing = workspace.scenario["spacing_m"]
            fig.add_trace(truck_mesh(front, spacing, top))
        if show_loads:
            loads = m.display_loads if m.display_loads is not None else m.loads
            length = max(xmax - xmin, 1) * 0.07
            arrows = {k: [] for k in ("x", "y", "z", "text", "color")}
            tips = {k: [] for k in ("x", "y", "z", "u", "v", "w")}
            for nid, (fx, fy) in loads.items():
                if not fx and not fy:
                    continue
                x, z = points[nid][:2]
                norm = max(np.hypot(fx, fy), 1)
                ux, uz = fx / norm, fy / norm
                selected = workspace.selection == ("load", nid)
                color = "#ffd166" if selected else "#f1bd62"
                arrows["x"].extend([x - ux * length, x, None])
                arrows["y"].extend([0, 0, None])
                arrows["z"].extend([z - uz * length, z, None])
                arrows["text"].extend([f"{fx / 1000:g}, {fy / 1000:g} kN", "", ""])
                arrows["color"].extend([color] * 3)
                for key, value in zip(tips, (x, 0, z, ux, 0, uz)):
                    tips[key].append(value)
            fig.add_trace(
                go.Scatter3d(
                    x=arrows["x"],
                    y=arrows["y"],
                    z=arrows["z"],
                    text=arrows["text"],
                    mode="lines+text",
                    line={"color": arrows["color"], "width": 6},
                    hoverinfo="text",
                )
            )
            fig.add_trace(
                go.Cone(
                    **tips,
                    sizemode="absolute",
                    sizeref=length * 0.25,
                    anchor="tip",
                    colorscale=[[0, "#f1bd62"], [1, "#f1bd62"]],
                    showscale=False,
                    hoverinfo="skip",
                )
            )
    static_meshes = [t for t in fig.data if t.type == "mesh3d" and not t.meta]
    if static_meshes:
        merged = {k: [] for k in ("x", "y", "z", "i", "j", "k", "vertexcolor")}
        for trace in static_meshes:
            offset = len(merged["x"])
            for axis in ("x", "y", "z"):
                merged[axis].extend(getattr(trace, axis))
            for axis in ("i", "j", "k"):
                merged[axis].extend(offset + i for i in getattr(trace, axis))
            merged["vertexcolor"].extend([trace.color] * len(trace.x))
        fig.data = tuple(t for t in fig.data if t.type != "mesh3d" or t.meta)
        fig.add_trace(
            go.Mesh3d(**merged, flatshading=True, hoverinfo="skip", meta={"role": "decoration"})
        )
    title = "Interactive 3D · illustrative planar model"
    if deformed:
        title += " · deformation ×50"
    base_layout(fig, title, fit)
    eye = {"x": 1.4, "y": -1.8, "z": 0.9}
    center = {"x": 0, "y": 0, "z": 0}
    if camera == "Side":
        eye = {"x": 0, "y": -2.5, "z": 0.1}
    elif camera == "Follow vehicle" and points and workspace.scenario["enabled"]:
        center["x"] = (workspace.position - (xmin + xmax) / 2) / max(xmax - xmin, 1)
        eye = {"x": 0.3, "y": -0.7, "z": 0.4}
    scene_layout = {
        "aspectmode": "data",
        "xaxis_title": "x (m)",
        "yaxis_title": "width (m)",
        "zaxis_title": "elevation (m)",
        "bgcolor": PANEL,
        "uirevision": f"{fit}-{camera}",
    }
    if points:
        # Fixed bounds prevent rescaling/jitter as the truck crosses the bridge.
        min_x, max_x = xmin, xmax
        if workspace.scenario["enabled"] and show_vehicle:
            min_x = workspace.position_at(0) - workspace.scenario["spacing_m"] - 1
            max_x = workspace.position_at(1) + 1.5
        scene_layout.update(
            {
                "xaxis": {"range": [min_x - 1, max_x + 1]},
                "yaxis": {"range": [-0.5, 4.5]},
                "zaxis": {
                    "range": [elevation - 2, max(max(p[1] for p in points.values()), top + 3) + 0.5]
                },
            }
        )
    if camera != "Free camera":
        scene_layout["camera"] = {"eye": eye, "center": center, "up": {"x": 0, "y": 0, "z": 1}}
    fig.update_layout(scene=scene_layout)
    return fig


def diagram_png(model, mode="geometry"):
    """Server-side figure export without Chrome, VTK, or a GUI backend."""
    fig = Figure(figsize=(11, 4), layout="constrained")
    FigureCanvasAgg(fig)
    ax = fig.add_subplot(111)
    points = coordinates(model, 50 if mode == "deformed" else 0)
    for i, member in enumerate(model.members):
        a, b = points[member.a], points[member.b]
        color = member_color(model, i, "Axial Force" if mode == "force" else "Steel")
        if color.startswith("rgb("):
            color = tuple(int(v) / 255 for v in color[4:-1].split(","))
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=2)
        if mode == "force" and model.results is not None:
            ax.annotate(
                f"{model.results['forces'][i] / 1000:.1f}",
                ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2),
                fontsize=8,
            )
    for nid, p in points.items():
        ax.plot(p[0], p[1], "ko", ms=3)
        ax.annotate(str(nid), p[:2], xytext=(0, 5), textcoords="offset points", fontsize=8)
    ax.set(
        xlabel="x (m)",
        ylabel="y (m)",
        aspect="equal",
        title={
            "geometry": "Geometry",
            "force": "Axial forces (kN)",
            "deformed": "Deformation (magnified ×50)",
        }[mode],
    )
    ax.grid(alpha=0.2)
    stream = io.BytesIO()
    fig.savefig(stream, format="png", dpi=140)
    fig.clear()
    return stream.getvalue()
