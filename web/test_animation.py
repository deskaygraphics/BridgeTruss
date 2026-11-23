"""Numerical web parity and optional isolated-Chrome animation checks."""

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from example_studies import PRESETS, run_example, vehicle_example
from moving_loads import MovingResponse, convoy_axles
from redundancy import redundancy_study
from web.animation import animation_payload, animation_html


BRIDGE = next(iter(PRESETS))


@pytest.mark.parametrize("count", [1, 2, 3])
def test_web_convoy_matches_shared_solver(count):
    study = run_example(BRIDGE, vehicle_count=count, vehicle_gap_m=5)
    model, axles = vehicle_example(BRIDGE, vehicle_count=count, vehicle_gap_m=5)
    assert axles == convoy_axles(80000, 120000, 4, count, 5)
    expected = redundancy_study(model, 18, axles=axles)
    assert study["cases"] == expected["cases"]
    assert len(study["axles_offset_m_force_N"]) == 2 * count
    assert study["audience_inputs"]["vehicle_count"] == count
    assert study["audience_inputs"]["vehicle_gap_m"] == 5
    json.dumps(study, allow_nan=False)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"vehicle_count": 0},
        {"vehicle_count": 4},
        {"vehicle_count": True},
        {"vehicle_count": 2.5},
        {"vehicle_gap_m": -1},
        {"vehicle_gap_m": 1001},
        {"vehicle_gap_m": float("inf")},
        {"vehicle_gap_m": float("nan")},
    ],
)
def test_web_convoy_rejects_invalid_settings(kwargs):
    with pytest.raises(ValueError):
        run_example(BRIDGE, **kwargs)
    with pytest.raises(ValueError):
        animation_payload(BRIDGE, **kwargs)


def test_static_and_triangle_apply_no_vehicles():
    triangle = list(PRESETS)[1]
    assert animation_payload(triangle, vehicle_count=3) is None
    result = run_example(triangle, vehicle_count=3)
    assert result["axles_offset_m_force_N"] is None
    assert not result["audience_inputs"]["moving"]
    assert run_example(BRIDGE, moving=False, vehicle_count=3)["axles_offset_m_force_N"] is None


def test_animation_payload_and_safe_html():
    payload = animation_payload(BRIDGE, vehicle_count=3)
    assert payload["types"] == ["truck", "passenger car", "bus"]
    assert payload["limits"][0] < 0
    assert payload["limits"][1] > 45
    assert len(payload["static_u"]) == 2 * len(payload["nodes"])
    assert len(payload["deck_unit_u"]) == len(payload["deck"])
    payload["response_scope"] = "</script><script>alert('injected')</script>"
    html = animation_html(payload)
    assert "__ANIMATION_DATA__" not in html
    assert payload["response_scope"] not in html
    assert "\\u003c/script\\u003e" in html
    assert "<script src=" not in html
    assert "requestAnimationFrame" in html


@pytest.fixture(scope="module")
def browser():
    executable = (
        shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chromium-browser")
    )
    if executable is None:
        pytest.skip("Chrome/Chromium is required for browser animation verification")
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as runtime:
        instance = runtime.chromium.launch(
            executable_path=executable,
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        yield instance
        instance.close()


@pytest.mark.parametrize("count", [1, 2, 3])
def test_browser_response_matches_python_at_every_axle_event(browser, count):
    payload = animation_payload(BRIDGE, vehicle_count=count)
    model, axles = vehicle_example(BRIDGE, vehicle_count=count)
    response = MovingResponse(model)
    page = browser.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.set_content(animation_html(payload))
        assert page.locator("#bridge").get_attribute("data-vehicle-count") == str(count)
        events = {node[1] + offset for node in payload["deck"] for offset, _ in axles}
        positions = sorted(events | {-0.01, 22.005, payload["limits"][1]})
        for position in positions:
            actual = page.evaluate("x => responseAt(x)", position)
            expected = response.at(position, axles)["U"]
            np.testing.assert_allclose(actual["u"], expected, rtol=1e-11, atol=1e-13)
            assert actual["peak"] == pytest.approx(max(abs(expected[1::2])), abs=1e-13)
            assert actual["load"] == pytest.approx(
                sum(force for offset, force in axles if 0 <= position - offset <= 25)
            )
        assert not errors
    finally:
        page.close()


def test_browser_play_pause_reset_and_mobile_layout(browser, tmp_path):
    page = browser.new_page(viewport={"width": 1000, "height": 700})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        page.set_content(animation_html(animation_payload(BRIDGE, vehicle_count=3)))
        assert page.locator("#active-load").inner_text() == "0.0 kN"
        page.locator("#position").evaluate(
            "el => { el.value = '489'; el.dispatchEvent(new Event('input')); }"
        )
        assert page.locator("#active-load").inner_text() == "600.0 kN"
        start = float(page.locator("#bridge").get_attribute("data-front-position"))
        page.get_by_role("button", name="Play animation").click()
        page.wait_for_function(
            "start => Number(canvas.dataset.frontPosition) > start + 0.1", arg=start
        )
        page.get_by_role("button", name="Pause animation").click()
        stopped = page.locator("#position-value").inner_text()
        page.wait_for_timeout(100)
        assert page.locator("#position-value").inner_text() == stopped
        page.get_by_label("Camera view").select_option("side")
        page.get_by_label("Deformation ×50").check()
        assert page.locator("#deflection").inner_text() != "0.000 mm"
        page.screenshot(path=str(tmp_path / "web-convoy.png"))
        page.get_by_role("button", name="Reset").click()
        assert page.locator("#position").input_value() == "0"
        assert page.locator("#active-load").inner_text() == "0.0 kN"
        page.locator("#position").evaluate(
            "el => { el.value = '999'; el.dispatchEvent(new Event('input')); }"
        )
        page.get_by_label("Playback speed").select_option("4")
        page.get_by_role("button", name="Play animation").click()
        page.wait_for_function("position.value === '1000' && !state.playing")
        assert page.locator("#active-load").inner_text() == "0.0 kN"
        page.set_viewport_size({"width": 390, "height": 800})
        assert page.evaluate("document.body.scrollWidth <= window.innerWidth")
        assert not errors
    finally:
        page.close()


def test_streamlit_convoy_selection_invalidation_and_static_triangle():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).with_name("app.py")), default_timeout=30).run()
    app.selectbox(key="vehicle_count").select(3).run()
    assert not app.exception
    assert not app.number_input(key="vehicle_gap").disabled
    app.button[0].click().run()
    assert not app.exception
    assert len(app.session_state["study"]["axles_offset_m_force_N"]) == 6
    assert app.session_state["study"]["audience_inputs"]["vehicle_count"] == 3
    app.number_input(key="vehicle_gap").set_value(6.0).run()
    assert not app.metric
    app.button[0].click().run()
    assert app.session_state["study"]["audience_inputs"]["vehicle_gap_m"] == 6.0
    app.checkbox(key="moving_False").uncheck().run()
    assert not app.metric
    assert app.selectbox(key="vehicle_count").disabled
    app.selectbox[0].select(list(PRESETS)[1]).run()
    assert app.selectbox(key="vehicle_count").disabled
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["study"]["axles_offset_m_force_N"] is None
