from types import SimpleNamespace
import numpy as np
import pytest
from matplotlib.backend_bases import MouseEvent
from test_gui import app as app, window as window
from main import Plot
from bridge_model import Model


@pytest.fixture
def canvas(app):
    plot = Plot((6, 3), interactive=True)
    model = Model()
    model.solve()
    plot.draw_model(model, "deformed", True)
    plot.draw()
    yield plot
    plot.close()


def test_response_graphs_fill_panel_width_without_changing_results(window, app):
    window.show()
    app.processEvents()
    results = window.model.results
    for plot in window.diagram_canvases():
        plot.draw()
        assert plot.ax.get_aspect() == "auto"
        expected_width = plot.fig.bbox.width * (
            plot.fig.subplotpars.right - plot.fig.subplotpars.left
        )
        np.testing.assert_allclose(plot.ax.bbox.width, expected_width)
    window.resize(window.width() + 300, window.height())
    app.processEvents()
    for plot in (window.small_deform, window.small_forces):
        plot.draw()
        assert plot.ax.bbox.width > plot.width() * 0.85
    assert window.model.results is results


def limits(canvas):
    return np.array([canvas.ax.get_xlim(), canvas.ax.get_ylim()])


def event_at(canvas, name, x, y, **kwargs):
    pixels = canvas.ax.transData.transform((x, y))
    return MouseEvent(name, canvas, *pixels, **kwargs)


def test_wheel_zoom_preserves_cursor_anchor(canvas):
    before = limits(canvas)
    point = before[:, 0] + np.diff(before, axis=1).ravel() * [0.3, 0.6]
    event = event_at(canvas, "scroll_event", *point, button="up", step=1)
    assert event.inaxes is canvas.ax
    anchor = np.array([event.xdata, event.ydata])
    fraction = (anchor - before[:, 0]) / np.diff(before, axis=1).ravel()
    canvas.callbacks.process("scroll_event", event)
    canvas.draw()
    after = limits(canvas)
    np.testing.assert_allclose(np.diff(after, axis=1), np.diff(before, axis=1) / 1.2)
    np.testing.assert_allclose((anchor - after[:, 0]) / np.diff(after, axis=1).ravel(), fraction)
    assert canvas._manual_view


@pytest.mark.parametrize("button", [1, 2])
def test_drag_pan_and_release(canvas, button):
    before = limits(canvas)
    point = before.mean(axis=1)
    press = event_at(canvas, "button_press_event", *point, button=button)
    canvas.callbacks.process("button_press_event", press)
    box_width, box_height = canvas.ax.bbox.width, canvas.ax.bbox.height
    move = MouseEvent("motion_notify_event", canvas, press.x + 30, press.y + 15, button=button)
    canvas.callbacks.process("motion_notify_event", move)
    expected = (
        before
        - np.array(
            [30 * np.diff(before[0])[0] / box_width, 15 * np.diff(before[1])[0] / box_height]
        )[:, None]
    )
    np.testing.assert_allclose(limits(canvas), expected)
    release = MouseEvent("button_release_event", canvas, move.x, move.y, button=button)
    canvas.callbacks.process("button_release_event", release)
    assert canvas._pan_anchor is None
    snapshot = limits(canvas)
    canvas._on_motion(move)
    np.testing.assert_array_equal(limits(canvas), snapshot)


def test_double_click_and_fit_restore_home(canvas):
    home = limits(canvas)
    canvas.zoom_at(*home.mean(axis=1), 3)
    double = event_at(
        canvas, "button_press_event", *limits(canvas).mean(axis=1), button=1, dblclick=True
    )
    canvas.callbacks.process("button_press_event", double)
    canvas.draw()
    np.testing.assert_allclose(limits(canvas), home)
    assert not canvas._manual_view


def test_pan_survives_a_response_redraw(canvas):
    before = limits(canvas)
    press = event_at(canvas, "button_press_event", *before.mean(axis=1), button=1)
    canvas.callbacks.process("button_press_event", press)
    model = Model()
    model.loads[6] = (0.0, -100000.0)
    model.solve()
    canvas.draw_model(model, "deformed", True)
    assert canvas._pan_anchor is not None
    move = MouseEvent("motion_notify_event", canvas, press.x + 20, press.y, button=1)
    canvas.callbacks.process("motion_notify_event", move)
    assert canvas._manual_view
    assert not np.allclose(limits(canvas), before)


def test_zoom_bounds_and_invalid_events(canvas):
    home_width = np.diff(canvas._home_limits[0])[0]
    for _ in range(60):
        canvas.zoom_at(*limits(canvas).mean(axis=1), 10)
    assert np.diff(canvas.ax.get_xlim())[0] >= home_width * 1e-4 * (1 - 1e-8)
    for _ in range(60):
        canvas.zoom_at(*limits(canvas).mean(axis=1), -10)
    assert np.diff(canvas.ax.get_xlim())[0] <= home_width * 20 * (1 + 1e-8)
    before = limits(canvas)
    assert not canvas.zoom_at(None, 0, 1)
    assert not canvas.zoom_at(0, 0, float("nan"))
    assert not canvas.zoom_at(0, 0, None)
    canvas._on_scroll(SimpleNamespace(inaxes=None))
    np.testing.assert_array_equal(limits(canvas), before)


def test_label_scaling_is_not_cumulative_and_keeps_view(canvas):
    canvas.zoom_at(*limits(canvas).mean(axis=1), 2)
    before = limits(canvas)
    canvas.set_label_scale(2.0)
    values = [text for text in canvas.ax.texts if text.get_text().endswith(" kN")]
    assert values and all(text.get_fontsize() == 18 for text in values)
    canvas.set_label_scale(1.5)
    canvas.set_label_scale(1.0)
    assert all(text.get_fontsize() == 9 for text in values)
    np.testing.assert_allclose(limits(canvas), before)
    with pytest.raises(ValueError):
        canvas.set_label_scale(float("nan"))


def test_empty_plot_and_geometry_change_reset(canvas):
    model = Model()
    model.solve()
    canvas.zoom_at(*limits(canvas).mean(axis=1), 2)
    model.nodes[0] = (-1.0, 0.0, 0.0)
    model.solve()
    canvas.draw_model(model, "deformed", True)
    assert not canvas._manual_view
    model.clear()
    canvas.draw_model(model, "force")
    assert not canvas.zoom_at(5, 5, 1)
    assert canvas._pan_anchor is None


def test_all_four_diagrams_preserve_views_during_vehicle_updates(window):
    w = window
    w.moving_toggle.setChecked(True)
    snapshots = []
    for plot in w.diagram_canvases():
        plot.draw()
        assert plot.interactive
        plot.zoom_at(*limits(plot).mean(axis=1), 2)
        snapshots.append(limits(plot))
    w.vehicle_position.setValue(650)
    for plot, before in zip(w.diagram_canvases(), snapshots):
        plot.draw()
        np.testing.assert_allclose(limits(plot), before)
    assert not w.view2.interactive
    assert not w.test_errors


def test_shared_scale_and_fit_do_not_change_analysis(window):
    w = window
    result = w.model.results
    force_view = limits(w.forceplot)
    w.defplot.zoom_at(*limits(w.defplot).mean(axis=1), 2)
    np.testing.assert_array_equal(limits(w.forceplot), force_view)
    w.diagram_label_scale.setValue(200)
    for plot in w.diagram_canvases():
        assert plot.label_scale == 2.0
        text = next(label for label in plot.ax.texts if label.get_text().endswith(" kN"))
        assert text.get_fontsize() == 18
    w.refresh()
    assert w.defplot._manual_view
    w.diagram_fit_button.click()
    for plot in w.diagram_canvases():
        np.testing.assert_allclose(limits(plot), plot._home_limits)
        assert not plot._manual_view
    assert w.model.results is result


def test_compact_load_values_do_not_overlap_title(app):
    plot = Plot((5, 2), interactive=True)
    plot.resize(500, 180)
    plot.show()
    app.processEvents()
    model = Model()
    model.solve()
    plot.draw_model(model, "deformed")
    plot.set_label_scale(1.5)
    plot.reset_view()
    plot.draw()
    renderer = plot.get_renderer()
    title = plot.ax.title.get_window_extent(renderer)
    assert title.y1 <= plot.fig.bbox.y1
    assert plot._load_labels
    for label in plot._load_labels:
        bounds = label.get_window_extent(renderer)
        assert bounds.y1 <= plot.ax.bbox.y1 + 1
        assert not bounds.overlaps(title)
        assert label.get_clip_on()
    plot.close()
