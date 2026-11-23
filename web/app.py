"""Full browser workspace. Run: python -m streamlit run web/app.py."""

import hashlib
import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")

import plotly.graph_objects as go
import streamlit as st
from matplotlib.figure import Figure

import persistence as _persistence
import traffic as _traffic
from web import animation as _animation, plots as _plots, workspace as _workspace

# Streamlit can retain modules imported before their files were watched.
_refresh_dependencies = False
for _module in (_traffic, _persistence, _workspace, _plots, _animation):
    _stamp = Path(_module.__file__).stat().st_mtime_ns
    if _module is _animation:
        _stamp = (_stamp, Path(_module.__file__).with_name("animation.js").stat().st_mtime_ns)
    if _refresh_dependencies or getattr(_module, "_bridge_loaded_stamp", None) != _stamp:
        importlib.reload(_module)
        _module._bridge_loaded_stamp = _stamp
        _refresh_dependencies = True

from redundancy_plots import draw_comparison
from web.animation import animated_scene, load_animation_runtime
from web.plots import CONFIG, base_layout, diagram, diagram_png, scene
from web.responsive import phone_layout
from web.workspace import KINDS, Workspace, csv_bytes, numbers
from traffic import PRESETS, VEHICLE_FIELDS, preset_vehicle, traffic_scenario


st.set_page_config(
    page_title="BridgeTruss | Planar Analysis", layout="wide", initial_sidebar_state="auto"
)

STYLE = """
<style>
.stApp {background:#19232e;color:#edf2f8}
[data-testid="stSidebar"] {background:#202e3d}
.block-container {padding-top:3.5rem;padding-bottom:1rem;max-width:2000px}
h1 {font-size:1.6rem!important}
h3 {font-size:1.05rem!important}
[data-testid="stMetricValue"] {font-size:1.45rem}
.stButton>button,.stDownloadButton>button {border-radius:4px}
[data-testid="stVerticalBlockBorderWrapper"] {border-color:#3b4d61}
.st-key-right_controls {
    height:calc(100vh - 17rem)!important;
    height:calc(100dvh - 17rem)!important;
    min-height:16rem;
    flex:0 0 auto;
    overflow-y:auto;
    overscroll-behavior-y:contain;
    scrollbar-gutter:stable;
    padding-right:0.5rem;
}
.st-key-workspace_toolbar button {min-height:44px}
.st-key-controls_visible label {min-height:44px;align-items:center}
@media (max-width:767px) {
    .block-container {padding-left:0.75rem;padding-right:0.75rem}
    h1 {font-size:1.3rem!important}
    .st-key-workspace_panels [data-testid="stColumn"]:has(.st-key-right_controls) {
        position:fixed;
        top:8rem;
        right:0.5rem;
        width:min(22rem, calc(100vw - 1rem))!important;
        max-width:calc(100vw - 1rem)!important;
        z-index:990;
        padding:0.5rem;
        border:1px solid #4a6076;
        border-radius:8px;
        background:#202e3d;
        box-shadow:0 8px 32px #0008;
    }
    .st-key-right_controls {
        height:calc(100vh - 10rem)!important;
        height:calc(100dvh - 10rem)!important;
        min-height:0;
    }
}
</style>
"""


def remember_controls_choice():
    st.session_state["controls_user_choice"] = True


def hide_controls():
    st.session_state["controls_user_choice"] = True
    st.session_state["controls_visible"] = False


def act(function, *args, message=None, **kwargs):
    """Streamlit action boundary: domain failures remain visible, never crash the page."""
    try:
        function(*args, **kwargs)
        st.session_state["notice"] = message or "Workspace updated."
        st.rerun()
    except (ValueError, TypeError, OSError) as exc:
        st.error(str(exc))


def table(rows, **kwargs):
    st.dataframe(rows, hide_index=True, width="stretch", **kwargs)


def chart(fig, key):
    if st.session_state.get("phone_layout", False):
        fig.update_layout(height=320, margin={"l": 35, "r": 10, "t": 65, "b": 35})
        fig.update_layout(
            title={"text": fig.layout.title.text.replace(" · ", "<br>", 1), "font": {"size": 12}}
        )
    st.plotly_chart(fig, key=key, theme=None, config=CONFIG, width="stretch")


def project_controls(w):
    with st.sidebar:
        st.header("Model tools")
        with st.expander("New / presets / open", expanded=True):
            kind = st.selectbox("Truss type", KINDS, key="preset_kind")
            confirm = st.checkbox("Replace current project", key="confirm_replace")
            if st.button("Create / replace", width="stretch", disabled=not confirm):
                act(w.new, kind, message=f"{kind} workspace created.")
            example = st.selectbox(
                "Supplied model", sorted(p.name for p in (ROOT / "examples").glob("*.json"))
            )
            if st.button("Open example", disabled=not confirm, width="stretch"):
                act(
                    w.load_json,
                    (ROOT / "examples" / example).read_bytes(),
                    message=f"Opened {example}. Click Analyze.",
                )
            upload = st.file_uploader("Open desktop model JSON", type=["json"], max_upload_size=2)
            if st.button(
                "Open uploaded model", disabled=upload is None or not confirm, width="stretch"
            ):
                act(w.load_json, upload.getvalue(), message="Model and vehicle scenario loaded.")
            st.caption(
                "Replacement requires confirmation. Editing drafts is allowed; saved models must be stable."
            )

        revision = w.revision
        with st.expander("Add node"):
            with st.form(f"add_node_{revision}", clear_on_submit=False):
                nid = st.number_input(
                    "New node ID", min_value=0, value=max(w.model.nodes, default=-1) + 1, step=1
                )
                x = st.number_input("x (m)", value=12.5, format="%.3f")
                y = st.number_input("y (m)", value=2.0, format="%.3f")
                if st.form_submit_button("Add node", width="stretch"):
                    act(
                        w.add_node,
                        int(nid),
                        x,
                        y,
                        message="Node added. Connect members, then Analyze.",
                    )

        ids = sorted(w.model.nodes)
        member_ids = list(range(1, len(w.model.members) + 1))
        with st.expander("Move / remove node"):
            if ids:
                n = st.selectbox("Node", ids, key=f"move_node_{revision}")
                px, py, _ = w.model.nodes[n]
                with st.form(f"move_form_{revision}_{n}"):
                    x = st.number_input("New x (m)", value=float(px), format="%.3f")
                    y = st.number_input("New y (m)", value=float(py), format="%.3f")
                    if st.form_submit_button("Move node"):
                        act(w.move_node, n, x, y)
                if st.button("Remove unconnected node"):
                    act(w.remove_node, n)
            else:
                st.caption("Add a node first.")

        with st.expander("Add / attach member"):
            st.caption("Choose two joints. Crossings do not create connections.")
            if len(ids) >= 2:
                with st.form(f"member_form_{revision}"):
                    a = st.selectbox("First joint", ids)
                    b = st.selectbox("Second joint", ids, index=1)
                    area = st.number_input(
                        "New member area (m²)", min_value=0.000001, value=0.005, format="%.6f"
                    )
                    elastic = st.number_input(
                        "New member E (GPa)", min_value=0.001, value=200.0, format="%.3f"
                    )
                    if st.form_submit_button("Attach member", width="stretch"):
                        act(w.set_member, a, b, area, elastic * 1e9)
            else:
                st.caption("Create at least two nodes.")

        with st.expander("Edit / delete member"):
            if member_ids:
                mid = st.selectbox(
                    "Member",
                    member_ids,
                    format_func=lambda i: (
                        f"M{i}: {w.model.members[i - 1].a}–{w.model.members[i - 1].b}"
                    ),
                    key=f"edit_mid_{revision}",
                )
                m = w.model.members[mid - 1]
                with st.form(f"edit_member_{revision}_{mid}"):
                    a = st.selectbox("Node i", ids, index=ids.index(m.a))
                    b = st.selectbox("Node j", ids, index=ids.index(m.b))
                    area = st.number_input(
                        "Area (m²)", min_value=0.000001, value=float(m.A), format="%.6f"
                    )
                    elastic = st.number_input(
                        "E (GPa)", min_value=0.001, value=float(m.E / 1e9), format="%.3f"
                    )
                    if st.form_submit_button("Apply member edit"):
                        act(w.set_member, a, b, area, elastic * 1e9, mid)
                if st.button("Delete member", width="stretch"):
                    act(w.remove_member, mid)
                st.caption("Deleting a member renumbers remaining members, as on desktop.")
            else:
                st.caption("No members yet.")

        with st.expander("Add / change / reassign load"):
            if ids:
                source = st.selectbox("Load source node", ids, key=f"load_source_{revision}")
                fx, fy = w.model.loads.get(source, (0, 0))
                with st.form(f"load_form_{revision}_{source}"):
                    target = st.selectbox("Target node", ids, index=ids.index(source))
                    fx = st.number_input("Fx (kN)", value=float(fx / 1000))
                    fy = st.number_input("Fy (kN)", value=float(fy / 1000))
                    replace = st.checkbox("Replace target's existing load if reassigning")
                    if st.form_submit_button("Apply load"):
                        act(w.set_load, source, target, fx * 1000, fy * 1000, replace)
                st.caption("Negative Fy acts downward. Set both components to zero to remove.")
                clear = st.checkbox("Confirm clearing all static loads")
                if st.button("Clear static loads", disabled=not clear):
                    act(w.clear_loads)
            else:
                st.caption("Add a node first.")

        with st.expander("Set support / deck nodes"):
            if ids:
                n = st.selectbox("Support node", ids, key=f"support_node_{revision}")
                fixed = w.model.fixed.get(n, (False, False))
                choices = {
                    "Pinned (x and y fixed)": (True, True),
                    "Vertical roller (y fixed)": (False, True),
                    "Horizontal roller (x fixed)": (True, False),
                    "Free": (False, False),
                }
                with st.form(f"support_form_{revision}_{n}"):
                    typ = st.selectbox(
                        "Support type", list(choices), index=list(choices.values()).index(fixed)
                    )
                    if st.form_submit_button("Apply support"):
                        act(w.set_support, n, choices[typ])
                with st.form(f"deck_form_{revision}"):
                    deck = st.multiselect("Deck node IDs", ids, default=w.model.deck_nodes)
                    if st.form_submit_button("Select deck nodes"):
                        act(w.set_deck, deck)
                st.caption("Deck: at least two joints, common elevation, distinct x coordinates.")
        if st.button("Undo last edit", disabled=w.undo_state is None, width="stretch"):
            act(w.undo)
        st.caption("All edits clear affected results. Click Analyze after editing.")


def view_controls():
    with st.expander("View controls", expanded=True):
        labels = st.checkbox("Show node IDs", value=True)
        deformed = st.checkbox("Show 3D deformation ×50")
        color = st.selectbox("Color by", ["Axial Force", "Stress", "Steel"])
        scale = st.slider("2D label size (%)", 75, 250, 100, 25)
        camera = st.selectbox("Camera", ["Isometric", "Side", "Follow vehicle", "Free camera"])
        road = st.checkbox("Road / bearings", value=True)
        vehicle = st.checkbox("Vehicle", value=True)
        loads = st.checkbox("Load arrows", value=True)
        if st.button("Fit all views", width="stretch"):
            st.session_state["fit"] = st.session_state.get("fit", 0) + 1
        st.caption("2D: wheel zoom, drag pan, double-click fit. 3D: drag orbit. Gold = selected.")
    return labels, deformed, color, scale / 100, camera, road, vehicle, loads


def traffic_editor(w):
    """Draft controls never alter numerical traffic until an explicit Apply."""
    s = w.scenario
    prefix = f"traffic_{w.revision}"
    saved = [{key: v[key] for key in VEHICLE_FIELDS} for v in w.vehicles]
    draft = st.session_state.setdefault(f"{prefix}_draft", [dict(v) for v in saved])
    while len(draft) < 3:
        draft.append(preset_vehicle("Car" if len(draft) == 1 else "Bus", 3))
    count = st.selectbox(
        "Number of vehicles", [1, 2, 3], index=len(saved) - 1, key=f"{prefix}_count"
    )
    first_kind = st.selectbox(
        "Vehicle 1 type",
        list(PRESETS),
        index=list(PRESETS).index(draft[0]["kind"]),
        key=f"{prefix}_kind_0",
    )
    draft[0]["kind"] = first_kind
    if count == 1 and first_kind == "Truck" and not traffic_scenario(s):
        # Keep the original single-truck form and its labels for existing workflows.
        with st.form(f"vehicle_form_{w.revision}"):
            enabled = st.checkbox("Enable moving loads", value=s["enabled"])
            front = st.number_input("Front axle (kN)", 0.0, 100000.0, float(s["front_N"] / 1000))
            rear = st.number_input("Rear axle (kN)", 0.0, 100000.0, float(s["rear_N"] / 1000))
            spacing = st.number_input("Axle spacing (m)", 0.0, 1000.0, float(s["spacing_m"]))
            step = st.number_input("Response step (m)", 0.05, 20.0, w.response_step, 0.05)
            if st.form_submit_button("Apply vehicle settings", width="stretch"):

                def apply_single():
                    w.configure(bool(enabled), front * 1000, rear * 1000, spacing, step)
                    w.analyze()

                act(apply_single)
        return
    st.caption(
        "Example presets, not regulatory design vehicles. Load a preset explicitly; "
        "changing a type does not silently replace custom axle forces."
    )
    enabled = st.checkbox("Enable moving loads", value=s["enabled"], key=f"{prefix}_enabled")
    vehicles = []
    for i in range(count):
        v = draft[i]
        with st.expander(f"Vehicle {i + 1}", expanded=True):
            kind = (
                first_kind
                if i == 0
                else st.selectbox(
                    f"Vehicle {i + 1} type",
                    list(PRESETS),
                    index=list(PRESETS).index(v["kind"]),
                    key=f"{prefix}_kind_{i}",
                )
            )
            v["kind"] = kind
            if st.button(f"Load preset for vehicle {i + 1}", key=f"{prefix}_preset_{i}"):
                replacement = preset_vehicle(kind, 0 if i == 0 else 3)
                for field, divisor in (("front_N", 1000), ("rear_N", 1000), ("spacing_m", 1)):
                    st.session_state[f"{prefix}_{field}_{i}"] = replacement[field] / divisor
                v.update({key: replacement[key] for key in ("front_N", "rear_N", "spacing_m")})
            front = st.number_input(
                f"Vehicle {i + 1} front axle (kN)",
                0.0,
                100000.0,
                float(v["front_N"] / 1000),
                key=f"{prefix}_front_N_{i}",
            )
            rear = st.number_input(
                f"Vehicle {i + 1} rear axle (kN)",
                0.0,
                100000.0,
                float(v["rear_N"] / 1000),
                key=f"{prefix}_rear_N_{i}",
            )
            spacing = st.number_input(
                f"Vehicle {i + 1} wheelbase (m)",
                0.0,
                1000.0,
                float(v["spacing_m"]),
                key=f"{prefix}_spacing_m_{i}",
            )
            gap = 0.0
            if i:
                gap = st.number_input(
                    f"Gap before vehicle {i + 1} (m)",
                    2.0,
                    1000.0,
                    float(v["gap_m"]),
                    key=f"{prefix}_gap_{i}",
                    help="Previous vehicle's rear axle to this vehicle's front axle; not bumper clearance.",
                )
            vehicles.append(
                {
                    "kind": kind,
                    "front_N": front * 1000,
                    "rear_N": rear * 1000,
                    "spacing_m": spacing,
                    "gap_m": gap,
                }
            )
            v.update(vehicles[-1])
    step = st.number_input(
        "Response step (m)", 0.05, 20.0, w.response_step, 0.05, key=f"{prefix}_step"
    )
    st.caption(
        "Same lane, direction and playback clock. Wheelbases ≥ 1.2 m; rear-axle-to-next-"
        "front-axle gaps ≥ 2 m. Static loads stay active once."
    )
    if vehicles != saved or enabled != s["enabled"] or step != w.response_step:
        st.warning(
            "Draft traffic is not applied. Plots and results still use the applied configuration."
        )
    if st.button("Apply traffic settings", type="primary", width="stretch"):

        def apply_traffic():
            w.configure_traffic(bool(enabled), vehicles, step)
            w.analyze()

        act(apply_traffic, message=f"Applied {count} simultaneous vehicle(s).")


def vehicle_controls(w):
    with st.expander("Moving vehicle loads", expanded=True):
        s = w.scenario
        st.caption(f"Applied traffic: {len(w.vehicles)} vehicle(s).")
        traffic_editor(w)
        # A fresh key prevents stale slider state from overwriting playback or reset.
        fraction = st.slider(
            "Leading front axle position (%)" if len(w.vehicles) > 1 else "Front axle position (%)",
            0.0,
            100.0,
            float(s["position_fraction"] * 100),
            0.1,
            key=f"position_{w.revision}_{s['position_fraction']:.8f}",
            disabled=w.playing,
        )
        if abs(fraction / 100 - s["position_fraction"]) > 1e-8:
            act(w.set_position, fraction / 100)
        try:
            reference = "lead front" if len(w.vehicles) > 1 else "front"
            st.caption(
                f"Solved {reference} x = {w.position:.3f} m · playback {w.playback_time:.3f} s"
            )
            if len(w.vehicles) > 1:
                st.caption("All reported front-x positions refer to the leading vehicle.")
                table(
                    [
                        {
                            "Vehicle": i + 1,
                            "Type": v["kind"],
                            "Front x (m)": w.position - v["front_offset_m"],
                        }
                        for i, v in enumerate(w.vehicles)
                    ]
                )
        except ValueError:
            st.caption("Select a valid deck path before applying a vehicle.")
        play, reset = st.columns(2)
        if play.button("Pause" if w.playing else "Play", width="stretch"):
            act(w.pause if w.playing else w.play)
        if reset.button("Reset", width="stretch"):
            act(w.reset)
        st.caption(
            "Smooth visual motion is independent of solved response steps. "
            "Tables and colors use the labeled solved position; playback is not physical time."
        )
        if st.button("Compute Signed Envelopes", width="stretch"):
            w.pause()
            act(w.compute_envelopes, message="Full-passage envelopes calculated.")
        with st.expander("Moving load setup guide"):
            st.write(
                "1. Create a stable truss and Analyze.\n"
                "2. Select horizontal deck nodes.\n"
                "3. Keep static loads, or clear them for vehicle-only response.\n"
                "4. Choose one to three vehicles; edit axle forces, wheelbases and gaps. "
                "Enable moving loads and Apply vehicle/traffic settings.\n"
                "5. Use the slider or Play/Pause/Reset.\n"
                "6. Compute envelopes for full-passage extrema, independent of response step."
            )
    st.caption("Red: tension · Blue: compression · Gray: near-zero / steel")


def selection_controls(w):
    st.caption(
        "Both displayed sides edit ONE planar model. Select entities here instead of desktop right-click picking."
    )
    options = [None]
    options += [("node", n) for n in sorted(w.model.nodes)]
    options += [("member", i + 1) for i in range(len(w.model.members))]
    options += [("load", n) for n in sorted(w.model.loads)]
    current = w.selection if w.selection in options else None
    selected = st.selectbox(
        "Scene selection",
        options,
        index=options.index(current),
        format_func=lambda v: "Nothing selected" if v is None else f"{v[0].title()} {v[1]}",
        key=f"selection_{w.revision}",
    )
    w.selection = selected
    if selected is None:
        return
    kind, identity = selected
    if kind == "member":
        m = w.model.members[identity - 1]
        with st.form(f"scene_member_{w.revision}_{identity}"):
            area = st.number_input(
                "Selected area (m²)", min_value=0.000001, value=float(m.A), format="%.6f"
            )
            elastic = st.number_input("Selected E (GPa)", min_value=0.001, value=float(m.E / 1e9))
            if st.form_submit_button("Edit selected member"):
                act(w.set_member, m.a, m.b, area, elastic * 1e9, identity)
        if st.button("Remove selected member"):
            act(w.remove_member, identity)
    elif kind == "node":
        x, y, _ = w.model.nodes[identity]
        with st.form(f"scene_node_{w.revision}_{identity}"):
            x = st.number_input("Selected x (m)", value=float(x))
            y = st.number_input("Selected y (m)", value=float(y))
            if st.form_submit_button("Edit selected node"):
                act(w.move_node, identity, x, y)
        if st.button("Remove selected unconnected node"):
            act(w.remove_node, identity)
    else:
        fx, fy = w.model.loads[identity]
        with st.form(f"scene_load_{w.revision}_{identity}"):
            target = st.selectbox(
                "Reassign load to node",
                sorted(w.model.nodes),
                index=sorted(w.model.nodes).index(identity),
            )
            fx = st.number_input("Selected Fx (kN)", value=float(fx / 1000))
            fy = st.number_input("Selected Fy (kN)", value=float(fy / 1000))
            replace = st.checkbox("Confirm replacing target load")
            if st.form_submit_button("Edit selected load"):
                act(w.set_load, identity, target, fx * 1000, fy * 1000, replace)
        if st.button("Remove selected load"):
            act(w.set_load, identity, identity, 0.0, 0.0)


def influence_panel(w):
    if st.button("Compute influence lines"):
        w.pause()
        act(w.compute_influence)
    data = w.influence
    st.caption("Response to a unit downward 1 N load; existing static loads are excluded.")
    if data is None:
        return
    choices = {
        f"Member {i + 1} axial force (N/N)": ("forces", i) for i in range(len(w.model.members))
    }
    for i, nid in enumerate(data["ids"]):
        for k, axis in enumerate("xy"):
            choices[f"Node {nid} u{axis} (m/N)"] = ("U", 2 * i + k)
            if w.model.fixed.get(nid, (False, False))[k]:
                choices[f"Support {nid} R{axis} (N/N)"] = ("R", 2 * i + k)
    name = st.selectbox("Response", list(choices))
    key, index = choices[name]
    fig = go.Figure(go.Scatter(x=data["x"], y=data[key][:, index], mode="lines+markers"))
    base_layout(fig, name)
    fig.update_xaxes(title="Unit load x (m)")
    chart(fig, "influence_plot")


def envelope_panel(w):
    st.caption("Includes static loads. Minima and maxima can occur at different vehicle positions.")
    if w.envelopes is None:
        st.info("Use Compute Signed Envelopes in Moving vehicle loads.")
        return
    rows = []
    for key, scale, unit in [
        ("forces", 1e-3, "kN"),
        ("stresses", 1e-6, "MPa"),
        ("U", 1e3, "mm"),
        ("R", 1e-3, "kN"),
    ]:
        values = w.envelopes[key]
        for i in range(len(values["min"])):
            label = (
                f"M{i + 1}"
                if key in ("forces", "stresses")
                else f"Node {w.envelopes['ids'][i // 2]} {'xy'[i % 2]}"
            )
            rows.append(
                {
                    "Response": key,
                    "Entity": label,
                    "Unit": unit,
                    "Min": values["min"][i] * scale,
                    "Max": values["max"][i] * scale,
                    "Front x at min (m)": values["x_min"][i],
                    "Front x at max (m)": values["x_max"][i],
                }
            )
    st.write(f"Method: {w.envelopes['method']}")
    table(rows)
    st.download_button(
        "Download envelopes CSV",
        csv_bytes([list(rows[0]), *[list(r.values()) for r in rows]]),
        "envelopes.csv",
        "text/csv",
    )


def design_panel(w):
    st.caption(
        "Finite grid, unchanged prescribed loads. Axial-stress screening only; no buckling or code certification."
    )
    draft = st.session_state.get(
        "design_draft", ("3,4,5", "0.75,1,1.25", "0.75,1,1.25", 50.0, 150.0, 7850.0)
    )
    c1, c2, c3 = st.columns(3)
    height = c1.text_input("Heights (m)", draft[0], key="design_height")
    chord = c2.text_input("Chord factors", draft[1], key="design_chord")
    web = c3.text_input("Web factors", draft[2], key="design_web")
    limit_u = c1.number_input(
        "Allowable |uy| (mm)", min_value=0.001, value=draft[3], key="design_limit_u"
    )
    limit_s = c2.number_input(
        "Allowable |stress| (MPa)", min_value=0.001, value=draft[4], key="design_limit_s"
    )
    density = c3.number_input(
        "Density (kg/m³)", min_value=1.0, value=draft[5], key="design_density"
    )
    st.session_state["design_draft"] = (height, chord, web, limit_u, limit_s, density)
    try:
        inputs = (numbers(height), numbers(chord), numbers(web), limit_u, limit_s, density)
    except ValueError as exc:
        w.study = None
        st.error(str(exc))
        return
    if w.study_inputs != inputs:
        w.study = None
    if st.button("Run design study"):
        w.pause()
        act(w.explore, *inputs)
    if w.study is None:
        return
    best = w.study["best"]
    if best:
        st.success(
            f"Minimum feasible sampled mass: {best['mass_kg']:.2f} kg; "
            f"height {best['height_m']:g} m, chord ×{best['chord_factor']:g}, web ×{best['web_factor']:g}."
        )
    else:
        st.warning(
            "No tested candidate satisfies both limits. This does not prove no feasible design exists."
        )
    st.caption(w.study["loading"])
    table(w.study["candidates"])
    fig = go.Figure()
    for row in w.study["candidates"]:
        if "mass_kg" in row:
            fig.add_trace(
                go.Scatter(
                    x=[row["mass_kg"]],
                    y=[row["vertical_deflection_m"] * 1000],
                    mode="markers",
                    marker={
                        "symbol": "star" if row["pareto"] else "circle",
                        "size": 14 if row["pareto"] else 8,
                        "color": "#4899ec" if row["feasible"] else "#ef6659",
                    },
                    text=f"h={row['height_m']}, chord={row['chord_factor']}, web={row['web_factor']}",
                    hovertemplate="%{text}<br>%{x:.3f} kg · %{y:.4f} mm<extra></extra>",
                )
            )
    base_layout(fig, "Mass / deflection · blue feasible · stars Pareto")
    fig.update_xaxes(title="Mass (kg)")
    fig.update_yaxes(title="Peak |uy| (mm)")
    chart(fig, "design_tradeoff")


def redundancy_panel(w):
    if not w.model.members:
        st.info("Add members before running a redundancy study.")
        return
    draft_mid, draft_factors = st.session_state.get("redundancy_draft", (1, "1,0.75,0.5,0.25,0"))
    mid = st.selectbox(
        "Original member",
        list(range(1, len(w.model.members) + 1)),
        index=min(draft_mid, len(w.model.members)) - 1,
        key=f"redundancy_member_{w.revision}",
    )
    text = st.text_input("Area factors", draft_factors, key="redundancy_factors")
    st.session_state["redundancy_draft"] = (mid, text)
    try:
        factors = numbers(text)
    except ValueError as exc:
        w.redundancy = None
        st.error(str(exc))
        return
    if w.redundancy_inputs != (mid, factors):
        w.redundancy = None
    if st.button("Run redundancy study"):
        w.pause()
        act(w.study_member, mid, factors)
    study = w.redundancy
    if study is None:
        st.caption(
            "Zero physically removes the member. Original IDs remain aligned with the baseline."
        )
        return
    table(
        [
            {
                k: v
                for k, v in row.items()
                if k not in ("snapshot", "envelopes", "member_comparison", "member_ids")
            }
            for row in study["cases"]
        ]
    )
    index = st.selectbox(
        "Comparison case",
        list(range(len(study["cases"]))),
        format_func=lambda i: (
            f"{study['cases'][i]['area_factor'] * 100:g}% area · {study['cases'][i]['status']}"
        ),
    )
    st.caption(
        f"Common comparison: {study['comparison_case']}; front x = {study['comparison_front_x_m']}"
    )
    fig = Figure(figsize=(12, 8))
    draw_comparison(fig, study, index)
    st.pyplot(fig, clear_figure=True)
    row = study["cases"][index]
    if row["status"] == "stable":
        table(row["member_comparison"])
        base = study["cases"][0]["snapshot"]["U_m"]
        u = row["snapshot"]["U_m"]
        table(
            [
                {
                    "Node": n,
                    "Baseline ux (mm)": base[2 * i] * 1000,
                    "Candidate ux (mm)": u[2 * i] * 1000,
                    "Baseline uy (mm)": base[2 * i + 1] * 1000,
                    "Candidate uy (mm)": u[2 * i + 1] * 1000,
                }
                for i, n in enumerate(study["node_ids"])
            ]
        )
    else:
        st.warning(row["reason"])
    st.caption(study["limitations"])
    st.download_button(
        "Download redundancy JSON",
        json.dumps(study, indent=2, allow_nan=False),
        "redundancy.json",
        "application/json",
    )
    st.caption("The result ZIP also contains comparison PNGs and detailed study CSVs.")


def comparison_panel(w):
    st.caption(
        "Same geometry, supports, static/vehicle loads, E and total material volume. "
        "Moving enabled: complete passage, not current frame. Requires preset-compatible ten-node geometry."
    )
    if st.button("Compare equal-volume trusses"):
        w.pause()
        act(w.compare)
    if w.comparison:
        table(w.comparison)


def downloads(w):
    with st.expander("Save model / export results"):
        if w.playing:
            st.info("Pause playback to prepare downloads.")
            return
        try:
            content = w.model_json()
            st.download_button(
                "Save Model JSON", content, "bridge.json", "application/json", on_click="ignore"
            )
        except (ValueError, TypeError, KeyError) as exc:
            st.caption(f"Verified model save unavailable: {exc}")
            return
        r = w.model.results
        if r is None:
            st.caption("Analyze to enable numerical result and figure exports.")
            return
        st.download_button(
            "Member CSV",
            csv_bytes(
                [
                    ["Member", "Node i", "Node j", "Length (m)", "Axial force (N)", "Stress (Pa)"],
                    *[
                        [i + 1, m.a, m.b, r["lengths"][i], r["forces"][i], r["stresses"][i]]
                        for i, m in enumerate(w.model.members)
                    ],
                ]
            ),
            "member_forces.csv",
            "text/csv",
            on_click="ignore",
        )
        signature = hashlib.sha256(
            (
                content
                + repr(
                    (
                        w.revision,
                        w.history[-1:] or None,
                        w.study_inputs if w.study else None,
                        w.redundancy_inputs if w.redundancy else None,
                        w.envelopes is not None,
                    )
                ).encode()
            )
        ).hexdigest()
        if st.button("Prepare result ZIP + PNG figures"):
            try:
                figures = {
                    f"{mode}.png": diagram_png(w.model, mode)
                    for mode in ("geometry", "force", "deformed")
                }
                st.session_state["prepared_export"] = (signature, w.bundle(figures), figures)
            except (ValueError, OSError) as exc:
                st.error(str(exc))
        export = st.session_state.get("prepared_export")
        if export and export[0] == signature:
            st.download_button(
                "Download results ZIP",
                export[1],
                "bridge_results.zip",
                "application/zip",
                on_click="ignore",
            )
            for name, data in export[2].items():
                st.download_button(f"Download {name}", data, name, "image/png", on_click="ignore")
        st.caption(
            "Charts also have a camera button for browser-side image download, including 3D."
        )


def results(w):
    r = w.model.results
    if r is None:
        st.info(w.error or "Model changed. Click Analyze to calculate current results.")
        return
    summary = w.summary()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Peak |uy|", f"{summary['Peak |uy| (mm)']:.4f} mm")
    c2.metric("Peak |N|", f"{summary['Peak |N| (kN)']:.2f} kN")
    c3.metric("Steel mass", f"{summary['Steel mass (kg)']:.1f} kg")
    c4.metric("Relative residual", f"{r['relative_residual']:.2e}")
    c1, c2 = st.columns([1.3, 1])
    with c1:
        st.subheader("Member forces and stresses")
        table(w.member_rows(), height=240)
    with c2:
        st.subheader("Nodal displacements / reactions")
        if w.result_time is not None:
            st.caption(f"Solved at playback t = {w.result_time:.3f} s; x = {w.position:.3f} m")
        elif w.scenario["enabled"]:
            st.caption(f"Current-position quasi-static results; x = {w.position:.3f} m")
        else:
            st.caption("Static results — no playback timestamp")
        table(w.node_rows(), height=210)
    with st.expander("Structural summary / model data"):
        st.write(summary)
        table(
            [
                {
                    "Node": n,
                    "x (m)": p[0],
                    "y (m)": p[1],
                    "Fix x": w.model.fixed.get(n, (False, False))[0],
                    "Fix y": w.model.fixed.get(n, (False, False))[1],
                    "Fx (kN)": w.model.loads.get(n, (0, 0))[0] / 1000,
                    "Fy (kN)": w.model.loads.get(n, (0, 0))[1] / 1000,
                }
                for n, p in sorted(w.model.nodes.items())
            ]
        )


def workspace_body(w):
    # Only the selected tab is rendered, especially important during playback.
    if not st.session_state.get("controls_visible", True):
        # Keep widgets mounted: removing them would discard unsubmitted inputs.
        st.html("""<style>
            .st-key-workspace_panels [data-testid="stColumn"]:has(.st-key-right_controls) {
                display:none;
            }
        </style>""")
    with st.container(key="workspace_panels"):
        central, controls = st.columns([4.0, 1.15], gap="medium")
    with controls, st.container(border=False, key="right_controls"):
        if st.button("Hide controls", on_click=hide_controls, width="stretch"):
            st.rerun()
        vehicle_controls(w)
        options = view_controls()
    with central:
        if len(w.vehicles) > 1:
            active = "enabled" if w.scenario["enabled"] else "disabled"
            st.caption(
                f"Applied profile: {len(w.vehicles)} vehicles; moving loads {active}. "
                "Vehicle-study front-x columns refer to the leading vehicle."
            )
        labels, deformed, color, scale, camera, road, vehicle, loads = options
        names = [
            "2D View",
            "Interactive 3D",
            "Axial Forces",
            "Deformation",
            "Influence Lines",
            "Load Envelopes",
            "Design Exploration",
            "Redundancy Study",
            "Displacement History",
            "Equal-Volume Comparison",
        ]
        tabs = st.tabs(names, key="workspace_tab", on_change="rerun")
        fit = st.session_state.get("fit", 0) + w.revision
        for name, tab in zip(names, tabs):
            if not tab.open:
                continue
            with tab:
                if name in ("2D View", "Axial Forces", "Deformation"):
                    mode = {
                        "2D View": "geometry",
                        "Axial Forces": "force",
                        "Deformation": "deformed",
                    }[name]
                    chart(diagram(w.model, mode, labels, scale, fit, w.selection), f"main_{mode}")
                elif name == "Interactive 3D":
                    selection_controls(w)
                    animated_scene(
                        scene(w, color, labels, deformed, road, vehicle, loads, camera, fit),
                        w,
                        camera,
                        fit,
                    )
                    st.caption(
                        "Road, vehicles, duplicate side and cross ties add no stiffness or self-weight. "
                        "Vehicle shapes are illustrative; front-x labels use the leading vehicle."
                    )
                elif name == "Influence Lines":
                    influence_panel(w)
                elif name == "Load Envelopes":
                    envelope_panel(w)
                elif name == "Design Exploration":
                    design_panel(w)
                elif name == "Redundancy Study":
                    redundancy_panel(w)
                elif name == "Displacement History":
                    st.caption(
                        "Playback timestamps, not physical time. Edits, manual positioning, and Reset clear history. "
                        "Most recent 1000 solved frames retained; delayed frames are not backfilled."
                    )
                    table(
                        [
                            dict(
                                zip(
                                    ["Playback t (s)", "Front x (m)", "Node", "ux (mm)", "uy (mm)"],
                                    row,
                                )
                            )
                            for row in w.history
                        ],
                        height=400,
                    )
                    st.download_button(
                        "Export displacement history CSV",
                        w.history_csv(),
                        "displacement_history.csv",
                        "text/csv",
                    )
                else:
                    comparison_panel(w)
        results(w)
        downloads(w)


def main():
    st.html(STYLE)
    if "workspace" not in st.session_state:
        st.session_state["workspace"] = Workspace()
    w = st.session_state["workspace"]
    if type(w) is not Workspace:
        # Hot reload should retain users' unsaved geometry, not the old class methods.
        upgraded = Workspace.__new__(Workspace)
        upgraded.__dict__.update(w.__dict__)
        upgraded.playing = False
        upgraded.play_generation = getattr(w, "play_generation", 0)
        st.session_state["workspace"] = w = upgraded
    mobile = phone_layout()
    st.session_state["phone_layout"] = bool(mobile)
    if not st.session_state.get("controls_user_choice", False):
        st.session_state["controls_visible"] = not bool(mobile)
    st.title("BridgeTruss | Planar Analysis")
    with st.container(key="workspace_toolbar", horizontal=True, vertical_alignment="center"):
        if st.button("Analyze", type="primary"):
            w.pause()
            act(w.analyze, message="Analysis completed using the shared desktop solver.")
        if st.button("New Project"):
            st.session_state["show_new"] = True
        st.toggle(
            "Controls",
            key="controls_visible",
            on_change=remember_controls_choice,
            help="Show or hide vehicle and view settings without changing your model.",
        )
    if mobile:
        st.caption("Model tools: top-left sidebar arrow. Vehicle / view settings: Controls.")
    if st.session_state.get("show_new"):
        st.warning("New Project removes the active model, loads and calculated results.")
        yes, no = st.columns(2)
        if yes.button("Confirm new empty project"):
            st.session_state["show_new"] = False
            act(w.new)
        if no.button("Cancel new project"):
            st.session_state["show_new"] = False
            st.rerun()
    st.caption(
        f"{w.model.kind} · {len(w.model.nodes)} nodes · {len(w.model.members)} members · "
        "same numerical engine and model files as desktop"
    )
    notice = st.session_state.pop("notice", None)
    if notice:
        st.success(notice)
    interface = st.sidebar.radio("Interface", ["Full workspace", "Guided demo"])
    if interface == "Guided demo":
        w.pause()
        from web.demo_app import main as demo

        demo()
        return
    project_controls(w)
    load_animation_runtime()

    @st.fragment(run_every=0.25 if w.playing else None)
    def live_workspace():
        was_playing = w.playing
        if w.playing:
            try:
                w.tick()
            except ValueError as exc:
                w.pause()
                st.error(str(exc))
        workspace_body(w)
        if was_playing and not w.playing:
            st.rerun()

    live_workspace()
    st.caption(
        "Educational planar, linear-elastic, quasi-static analysis. No buckling, yielding, "
        "dynamics, spatial stability, automatic self-weight, or design-code certification. "
        "Stable does not mean certified safe."
    )


if __name__ == "__main__":
    main()
