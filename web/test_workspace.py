"""Desktop parity, session isolation, atomic editing, and browser workspace tests."""

import io
import json
import zipfile
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("plotly")

from bridge_model import Model
from moving_loads import combined_loads, envelope, influence_lines, travel_limits
from persistence import load_model, model_document
from web.plots import coordinates, diagram, diagram_png, scene
from web.workspace import ROOT, Workspace, numbers


def widget(elements, label):
    return next(element for element in elements if element.label == label)


def app():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    result = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
    assert not result.exception
    return result


def test_default_results_match_desktop_adapter():
    w = Workspace()
    expected = Model().solve()
    for key in ("U", "R", "F", "forces", "stresses"):
        np.testing.assert_allclose(w.model.results[key], expected[key])
    assert len(w.member_rows()) == 17
    assert len(w.node_rows()) == 10
    assert w.summary()["Peak |uy| (mm)"] == pytest.approx(8.91120087876333)


def test_sessions_are_independent():
    a, b = Workspace(), Workspace()
    a.clear_loads()
    a.scenario["front_N"] = 1000
    assert b.model.loads
    assert b.model.results is not None
    assert b.scenario["front_N"] == 80000
    assert a.model.results is None


def test_atomic_edits_invalidate_and_undo():
    w = Workspace()
    w.compute_envelopes()
    w.compute_influence()
    w.compare()
    original = model_document(w.model)
    w.set_member(0, 1, 0.003, 190e9, 1)
    assert w.model.members[0].A == 0.003
    assert w.model.results is None
    assert w.envelopes is w.influence is w.comparison is None
    w.undo()
    assert model_document(w.model) == original
    assert w.model.results is None
    w.analyze()
    assert w.model.results
    with pytest.raises(ValueError, match="No edit"):
        w.undo()


@pytest.mark.parametrize(
    "operation",
    [
        lambda w: w.set_member(0, 1, 0.005, 200e9),
        lambda w: w.set_member(0, 0, 0.005, 200e9),
        lambda w: w.set_member(0, 42, 0.005, 200e9),
        lambda w: w.set_member(0, 1, -1, 200e9, 1),
        lambda w: w.move_node(1, 0, 0),
        lambda w: w.move_node(1, float("nan"), 0),
        lambda w: w.add_node(1, 3, 4),
        lambda w: w.set_deck([0, 6]),
        lambda w: w.remove_node(0),
        lambda w: w.set_load(6, 7, 0, -1),
    ],
)
def test_invalid_edit_does_not_change_workspace(operation):
    w = Workspace()
    original = model_document(w.model)
    result = w.model.results
    with pytest.raises(ValueError):
        operation(w)
    assert model_document(w.model) == original
    assert w.model.results is result
    assert w.undo_state is None


def test_custom_model_can_be_built_incrementally():
    w = Workspace()
    w.new()
    with pytest.raises(ValueError):
        w.analyze()
    for nid, x, y in [(0, 0, 0), (1, 2, 0), (2, 1, 1)]:
        w.add_node(nid, x, y)
    for a, b in [(0, 1), (0, 2), (1, 2)]:
        w.set_member(a, b, 0.005, 200e9)
    w.set_support(0, (True, True))
    w.set_support(1, (False, True))
    w.set_load(2, 2, 0, -1000)
    w.set_deck([0, 1])
    assert w.analyze()["U"][5] < 0
    w.model_json()
    w.add_node(3, 4, 2)
    w.remove_node(3)
    w.set_load(2, 2, 0, 0)
    assert not w.model.loads


def test_reassign_load_requires_confirmation_and_undo():
    w = Workspace()
    w.set_load(6, 7, 2000, -9000, replace=True)
    assert 6 not in w.model.loads
    assert w.model.loads[7] == (2000, -9000)
    w.undo()
    assert w.model.loads[6] == (0, -50000)
    assert w.model.loads[7] == (0, -50000)


def test_desktop_json_round_trip(tmp_path):
    w = Workspace()
    w.configure(True, 90000, 110000, 3, 0.25)
    w.set_position(0.6)
    content = w.model_json()
    path = tmp_path / "bridge.json"
    path.write_bytes(content)
    desktop, scenario = load_model(path)
    assert scenario == w.scenario
    np.testing.assert_allclose(
        desktop.solve(combined_loads(desktop, w.position, w.axles))["U"], w.model.results["U"]
    )
    other = Workspace()
    other.load_json(content)
    assert other.model_json() == content
    assert other.model.results is None
    other.analyze()
    np.testing.assert_allclose(other.model.results["forces"], w.model.results["forces"])


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"{}",
        b"[]",
        b'{"nodes": [], "members": []}',
        b'{"nodes": [1], "members": [2], "schema_version": 20}',
        b"x" * 2_000_001,
    ],
)
def test_invalid_upload_keeps_active_model(content):
    w = Workspace()
    original = w.model_json()
    with pytest.raises(ValueError):
        w.load_json(content)
    assert w.model_json() == original


def test_moving_response_fraction_matches_desktop():
    w = Workspace()
    w.configure(True, 80000, 120000, 4, 0.5)
    for fraction in (0, 0.125, 0.5, 0.93, 1):
        w.set_position(fraction)
        lo, hi = travel_limits(w.model, w.axles)
        eps = max(hi - lo, 1) * 1e-8
        expected_position = lo - eps + (hi - lo + 2 * eps) * fraction
        assert w.position == pytest.approx(expected_position)
        model = deepcopy(w.model)
        expected = model.solve(combined_loads(model, expected_position, w.axles))
        np.testing.assert_allclose(w.model.results["U"], expected["U"], atol=1e-14)
    w.compute_envelopes()
    extremes = w.envelopes
    w.set_position(0.5)
    assert w.envelopes is extremes
    w.configure(True, 90000, 120000, 4, 0.5)
    assert w.envelopes is None


def test_invalid_vehicle_settings_are_atomic():
    w = Workspace()
    original = dict(w.scenario)
    for args in [(True, -1, 2, 4, 0.5), (True, 1, 2, 4, 0), (True, float("inf"), 2, 4, 0.5)]:
        with pytest.raises(ValueError):
            w.configure(*args)
        assert w.scenario == original
    w.new()
    with pytest.raises(ValueError):
        w.configure(True, 1, 2, 4, 0.5)
    assert not w.scenario["enabled"]


def test_play_pause_resume_reset_and_history():
    w = Workspace()
    w.play()
    assert w.playing and w.scenario["enabled"]
    w.tick(w._last_tick + 0.25)
    assert w.playback_time == pytest.approx(0.25)
    assert w.scenario["position_fraction"] > 0
    assert len(w.history) == 2 * len(w.model.nodes)
    position = w.position
    w.pause()
    w.tick()
    assert w.position == position
    w.play()
    w.tick(w._last_tick + 0.5)
    assert w.playback_time == pytest.approx(0.75)
    w.pause()
    assert b"playback_time_s,front_x_m,node,ux_mm,uy_mm" in w.history_csv()
    w.set_position(0.9)
    assert not w.history
    w.reset()
    assert not w.playing and not w.history and w.scenario["position_fraction"] == 0
    w.set_position(1)
    with pytest.raises(ValueError, match="Reset"):
        w.play()


def test_advanced_calculations_match_shared_engine():
    w = Workspace()
    expected = envelope(w.model, w.axles)
    actual = w.compute_envelopes()
    np.testing.assert_allclose(actual["forces"]["max"], expected["forces"]["max"])
    expected = influence_lines(w.model)
    actual = w.compute_influence()
    np.testing.assert_allclose(actual["U"], expected["U"])
    assert len(w.compare()) == 3
    study = w.explore([4], [1], [1], 50, 150, 7850)
    assert len(study["candidates"]) == 1 and study["best"] is not None
    w.load_json((ROOT / "examples/redundant_bridge.json").read_bytes())
    study = w.study_member(18, [1, 0.5, 0])
    assert study["cases"][-1]["status"] == "stable"
    assert study["cases"][-1]["snapshot"]["forces_N"][17] is None
    w.clear_loads()
    assert w.study is w.redundancy is None


def test_zip_exports_and_png_images():
    w = Workspace()
    w.compute_envelopes()
    images = {
        f"{mode}.png": diagram_png(w.model, mode) for mode in ("geometry", "force", "deformed")
    }
    assert all(data.startswith(b"\x89PNG") for data in images.values())
    with zipfile.ZipFile(io.BytesIO(w.bundle(images))) as archive:
        assert {
            "members.csv",
            "nodes.csv",
            "analysis.json",
            "envelopes.csv",
            "displacement_history.csv",
            *images,
        } <= set(archive.namelist())
        metadata = json.loads(archive.read("analysis.json"))
        assert metadata["model"] == json.loads(w.model_json())
        assert "relative_residual" in metadata["diagnostics"]


def test_redundancy_bundle_retains_original_ids():
    w = Workspace()
    w.load_json((ROOT / "examples/redundant_bridge.json").read_bytes())
    w.analyze()
    w.study_member(18, [1, 0])
    with zipfile.ZipFile(io.BytesIO(w.bundle())) as archive:
        assert "redundancy.json" in archive.namelist()
        assert any(name.endswith(".png") for name in archive.namelist())
        study = json.loads(archive.read("redundancy.json"))
        assert study["selected_member"] == 18
        assert study["cases"][-1]["member_ids"] == list(range(1, 18))


def test_plots_handle_empty_and_solved_models():
    w = Workspace()
    for mode in ("geometry", "force", "deformed"):
        assert diagram(w.model, mode).data
    original = np.array(list(w.model.nodes.values()))
    deformed = np.array(list(coordinates(w.model, 50).values()))
    assert not np.allclose(original, deformed)
    w.configure(True, 80000, 120000, 4, 0.5)
    w.set_position(0.5)
    for camera in ("Isometric", "Side", "Follow vehicle", "Free camera"):
        fig = scene(w, camera=camera)
        assert any(trace.type == "mesh3d" for trace in fig.data)
    w.new()
    assert scene(w)
    assert diagram(w.model)


def test_workspace_ui_edit_undo_analyze_and_session_isolation():
    a, b = app(), app()
    widget(a.number_input, "Area (m²)").set_value(0.003)
    widget(a.button, "Apply member edit").click().run()
    assert not a.exception
    assert a.session_state["workspace"].model.members[0].A == 0.003
    assert not a.metric
    assert b.session_state["workspace"].model.members[0].A == 0.005
    widget(a.button, "Analyze").click().run()
    assert not a.exception and a.metric
    widget(a.button, "Undo last edit").click().run()
    assert a.session_state["workspace"].model.members[0].A == 0.005
    widget(a.button, "Analyze").click().run()
    assert not a.exception


def test_workspace_ui_new_confirm_and_build_node():
    a = app()
    widget(a.button, "New Project").click().run()
    assert a.session_state["workspace"].model.nodes
    widget(a.button, "Confirm new empty project").click().run()
    assert not a.exception
    assert not a.session_state["workspace"].model.nodes
    widget(a.number_input, "x (m)").set_value(0.0)
    widget(a.number_input, "y (m)").set_value(0.0)
    widget(a.button, "Add node").click().run()
    assert not a.exception
    assert a.session_state["workspace"].model.nodes == {0: (0.0, 0.0, 0.0)}


def test_workspace_ui_export_and_guided_demo():
    a = app()
    widget(a.button, "Prepare result ZIP + PNG figures").click().run()
    assert not a.exception
    assert any(d.label == "Download results ZIP" for d in a.get("download_button"))
    widget(a.radio, "Interface").set_value("Guided demo").run()
    assert not a.exception
    widget(a.button, "Run example").click().run()
    assert not a.exception and a.metric[1].value == "STABLE"
    widget(a.radio, "Interface").set_value("Full workspace").run()
    assert not a.exception
    assert a.session_state["workspace"].model.members[0].A == 0.005


def test_controls_visibility_preserves_model_results_and_widget_settings():
    a = app()
    w = a.session_state["workspace"]
    result = w.model.results["U"].copy()
    widget(a.checkbox, "Show node IDs").uncheck().run()
    widget(a.selectbox, "Color by").select("Stress").run()
    widget(a.toggle, "Controls").set_value(False).run()
    assert not a.exception
    assert not a.session_state["controls_visible"]
    widget(a.button, "Analyze").click().run()
    assert not a.session_state["controls_visible"]
    widget(a.toggle, "Controls").set_value(True).run()
    assert not a.exception
    assert not widget(a.checkbox, "Show node IDs").value
    assert widget(a.selectbox, "Color by").value == "Stress"
    np.testing.assert_allclose(a.session_state["workspace"].model.results["U"], result)
    widget(a.button, "Hide controls").click().run()
    assert not a.exception
    assert not a.session_state["controls_visible"]


def test_traffic_editor_presets_apply_atomically():
    a = app()
    widget(a.selectbox, "Number of vehicles").select(3).run()
    assert not a.exception and len(a.session_state["workspace"].vehicles) == 1
    widget(a.selectbox, "Vehicle 2 type").select("Bus").run()
    assert widget(a.number_input, "Vehicle 2 front axle (kN)").value == 8
    widget(a.button, "Load preset for vehicle 2").click().run()
    assert widget(a.number_input, "Vehicle 2 front axle (kN)").value == 50
    widget(a.checkbox, "Enable moving loads").check()
    widget(a.button, "Apply traffic settings").click().run()
    assert not a.exception and len(a.session_state["workspace"].vehicles) == 3
    assert a.session_state["workspace"].vehicles[1]["kind"] == "Bus"
    widget(a.slider, "Leading front axle position (%)").set_value(50.0).run()
    assert not a.exception and a.session_state["workspace"].model.results is not None
    a.session_state["workspace_tab"] = "Interactive 3D"
    a.run()
    assert not a.exception


def test_number_lists_are_finite():
    assert numbers(" 1, 0.5, 0 ") == [1, 0.5, 0]
    for text in ("", "x", "1,nan", "1,inf"):
        with pytest.raises(ValueError):
            numbers(text)


def test_playback_export_precision_and_invalid_import():
    w = Workspace()
    w.play()
    w.tick(w._last_tick + 0.25)
    w.pause()
    fraction = w.scenario["position_fraction"]
    assert fraction == round(fraction * 1000) / 1000
    doc = json.loads(w.model_json())
    doc["scenario"]["position_fraction"] = 0.5004
    original = w.model_json()
    with pytest.raises(ValueError, match="precision"):
        w.load_json(json.dumps(doc))
    assert w.model_json() == original


def test_workspace_ui_studies_and_input_invalidation():
    a = app()
    a.session_state["workspace_tab"] = "Influence Lines"
    a.run()
    widget(a.button, "Compute influence lines").click().run()
    assert not a.exception
    assert a.session_state["workspace"].influence is not None
    a.session_state["workspace_tab"] = "Design Exploration"
    a.run()
    widget(a.button, "Run design study").click().run()
    assert not a.exception and a.session_state["workspace"].study
    widget(a.text_input, "Heights (m)").set_value("4").run()
    assert a.session_state["workspace"].study is None
    widget(a.button, "Run design study").click().run()
    assert a.session_state["workspace"].study
    a.session_state["workspace_tab"] = "Redundancy Study"
    a.run()
    widget(a.button, "Run redundancy study").click().run()
    assert not a.exception and a.session_state["workspace"].redundancy
    widget(a.text_input, "Area factors").set_value("1,0.5").run()
    assert a.session_state["workspace"].redundancy is None
    a.session_state["workspace_tab"] = "Design Exploration"
    a.run()
    assert widget(a.text_input, "Heights (m)").value == "4"
    assert a.session_state["workspace"].study
    a.session_state["workspace_tab"] = "Redundancy Study"
    a.run()
    assert widget(a.text_input, "Area factors").value == "1,0.5"
    widget(a.button, "Compute Signed Envelopes").click().run()
    a.session_state["workspace_tab"] = "Load Envelopes"
    a.run()
    assert not a.exception
    assert a.session_state["workspace"].envelopes is not None
    a.session_state["workspace_tab"] = "Equal-Volume Comparison"
    a.run()
    widget(a.button, "Compare equal-volume trusses").click().run()
    assert not a.exception
    assert len(a.session_state["workspace"].comparison) == 3


def test_workspace_ui_vehicle_settings_and_scene_selection():
    a = app()
    widget(a.checkbox, "Enable moving loads").check()
    widget(a.button, "Apply vehicle settings").click().run()
    assert not a.exception and a.session_state["workspace"].scenario["enabled"]
    assert a.session_state["workspace"].model.results
    widget(a.slider, "Front axle position (%)").set_value(50.0).run()
    assert not a.exception
    assert a.session_state["workspace"].scenario["position_fraction"] == 0.5
    a.session_state["workspace_tab"] = "Interactive 3D"
    a.run()
    widget(a.selectbox, "Scene selection").set_value(("member", 1)).run()
    assert not a.exception
    assert a.session_state["workspace"].selection == ("member", 1)
    widget(a.number_input, "Selected area (m²)").set_value(0.004)
    widget(a.button, "Edit selected member").click().run()
    assert not a.exception
    assert a.session_state["workspace"].model.members[0].A == 0.004


def test_playback_is_elapsed_time_based_and_does_not_backfill(monkeypatch):
    from web.workspace import RESPONSE_INTERVAL

    clock = [100.0]
    monkeypatch.setattr("web.workspace.time.monotonic", lambda: clock[0])
    w = Workspace()
    w.play()
    start = w.position
    clock[0] += RESPONSE_INTERVAL / 2
    w.tick()
    packet = w.playback_clock()
    assert w.position == start
    assert packet["fraction"] > w.scenario["position_fraction"]
    assert len(w.history) == len(w.model.nodes)
    # One delayed server refresh advances by elapsed time, not by one step.
    clock[0] = 101.0
    w.tick()
    assert w.position - start == pytest.approx(4 * w.response_step, abs=0.03)
    assert len(w.history) == 2 * len(w.model.nodes)
    # Pausing between response steps solves the visible position explicitly.
    clock[0] += RESPONSE_INTERVAL / 2
    w.pause()
    assert not w.playing
    assert w.position - start == pytest.approx(4.5 * w.response_step, abs=0.03)
    assert w.result_time == pytest.approx(1.125)
    expected = deepcopy(w.model).solve(combined_loads(w.model, w.position, w.axles))
    np.testing.assert_allclose(expected["U"], w.model.results["U"], atol=1e-14)
    paused = w.position
    clock[0] += 100
    w.play()
    clock[0] += RESPONSE_INTERVAL
    w.tick()
    assert w.position - paused == pytest.approx(w.response_step, abs=0.03)
    assert w.playback_time == pytest.approx(1.375)
    clock[0] += 1000
    w.tick()
    assert not w.playing
    assert w.scenario["position_fraction"] == 1
    assert w.playback_time < 20


def test_animated_scene_is_batched_and_camera_bounds_do_not_move():
    w = Workspace()
    w.configure(True, 80000, 120000, 4, 0.5)
    first = scene(w)
    vehicle = [t for t in first.data if t.meta and t.meta.get("role") == "vehicle"]
    assert len(vehicle) == 1
    assert len(vehicle[0].meta["wheels"]) == 4
    assert len(first.data) <= 8
    w.set_position(0.9)
    last = scene(w)
    assert first.layout.scene.xaxis.range == last.layout.scene.xaxis.range
    assert first.layout.scene.zaxis.range == last.layout.scene.zaxis.range
