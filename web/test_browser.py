"""Opt-in real Chrome checks against an already running local Streamlit server.

BRIDGETRUSS_WEB_BROWSER=1 python -m pytest web/test_browser.py -q
Requires Playwright and Chrome; no browser automation dependency at runtime.
"""

import json
import os
import zipfile
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(
    os.environ.get("BRIDGETRUSS_WEB_BROWSER") != "1",
    reason="Set BRIDGETRUSS_WEB_BROWSER=1 with a local server running",
)
ROOT = Path(__file__).resolve().parents[1]


def test_full_workspace_in_chrome(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("BRIDGETRUSS_CHROME", "/usr/bin/google-chrome"),
            headless=True,
            args=["--enable-unsafe-swiftshader"],
        )
        context = browser.new_context(viewport={"width": 1680, "height": 1050})
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto("http://127.0.0.1:8501/")
        page.get_by_role("heading", name="BridgeTruss | Planar Analysis", exact=True).wait_for()
        page.get_by_test_id("stMetricValue").first.wait_for()

        def clean():
            assert page.get_by_test_id("stException").count() == 0
            assert not errors

        def tab(name):
            page.get_by_role("tab", name=name, exact=True).click()

        def click(name):
            page.get_by_role("button", name=name, exact=True).click()

        def ready():
            # Streamlit removes the running indicator only after the script finishes.
            page.locator(
                '[data-testid="stStatusWidget"] [data-testid="stStatusWidgetRunningIcon"]'
            ).wait_for(state="hidden")
            clean()

        ready()
        second = browser.new_context()
        other = second.new_page()
        other.goto("http://127.0.0.1:8501/")
        other.get_by_test_id("stMetricValue").first.wait_for()
        original = other.get_by_test_id("stMetricValue").first.inner_text()

        page.get_by_text("Edit / delete member", exact=True).click()
        page.get_by_role("spinbutton", name="Area (m²)", exact=True).fill("0.003")
        click("Apply member edit")
        page.get_by_text(
            "Model changed. Click Analyze to calculate current results.", exact=True
        ).wait_for()
        assert other.get_by_test_id("stMetricValue").first.inner_text() == original
        click("Analyze")
        page.get_by_test_id("stMetricValue").first.wait_for()
        clean()
        click("Undo last edit")
        click("Analyze")
        page.get_by_test_id("stMetricValue").first.wait_for()

        tab("Interactive 3D")
        page.get_by_text("Scene selection", exact=True).wait_for()
        page.get_by_test_id("bridge-live-scene").locator("canvas").first.wait_for()
        clean()

        tab("Influence Lines")
        click("Compute influence lines")
        page.get_by_text("Response", exact=True).wait_for()
        clean()

        tab("Design Exploration")
        click("Run design study")
        page.get_by_text("Minimum feasible sampled mass:", exact=False).wait_for()
        clean()

        tab("Redundancy Study")
        click("Run redundancy study")
        page.get_by_text("Comparison case", exact=True).wait_for()
        clean()

        click("Compute Signed Envelopes")
        tab("Load Envelopes")
        page.get_by_text(
            "Method: event-based with one-sided boundary states", exact=True
        ).wait_for()
        clean()

        tab("Equal-Volume Comparison")
        click("Compare equal-volume trusses")
        page.get_by_test_id("stDataFrame").first.wait_for()
        clean()

        tab("2D View")
        click("Play")
        page.get_by_role("button", name="Pause", exact=True).wait_for()
        page.wait_for_timeout(1500)
        click("Pause")
        page.get_by_role("button", name="Play", exact=True).wait_for()
        clean()
        tab("Displacement History")
        page.get_by_role("button", name="Export displacement history CSV", exact=True).wait_for()
        with page.expect_download() as downloaded:
            click("Export displacement history CSV")
        assert downloaded.value.suggested_filename == "displacement_history.csv"
        history = tmp_path / "history.csv"
        downloaded.value.save_as(history)
        assert len(history.read_text().splitlines()) > 11

        page.get_by_text("Save model / export results", exact=True).click()
        click("Prepare result ZIP + PNG figures")
        page.get_by_role("button", name="Download results ZIP", exact=True).wait_for()
        with page.expect_download() as downloaded:
            click("Download results ZIP")
        bundle = tmp_path / "results.zip"
        downloaded.value.save_as(bundle)
        with zipfile.ZipFile(bundle) as archive:
            assert {"members.csv", "nodes.csv", "analysis.json", "force.png"} <= set(
                archive.namelist()
            )
            saved = json.loads(archive.read("analysis.json"))
            assert saved["model"]["scenario"]["enabled"]
        clean()

        # Upload is validated by the same model loader as the desktop application.
        page.get_by_text("Replace current project", exact=True).click()
        page.get_by_test_id("stFileUploader").locator("input[type=file]").set_input_files(
            ROOT / "examples" / "redundant_bridge.json"
        )
        click("Open uploaded model")
        page.get_by_text("Model and vehicle scenario loaded.", exact=True).wait_for()
        click("Analyze")
        page.get_by_test_id("stMetricValue").first.wait_for()
        clean()
        tab("Interactive 3D")
        page.get_by_text("Scene selection", exact=True).wait_for()
        page.get_by_test_id("bridge-live-scene").locator("canvas").first.wait_for()
        page.screenshot(path=str(tmp_path / "workspace-3d.png"), full_page=True)
        assert other.get_by_test_id("stMetricValue").first.inner_text() == original
        second.close()
        context.close()
        browser.close()


@pytest.mark.parametrize(
    "viewport", [{"width": 1680, "height": 1050}, {"width": 1280, "height": 760}]
)
def test_right_controls_scroll_without_moving_dashboard(viewport):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("BRIDGETRUSS_CHROME", "/usr/bin/google-chrome"),
            headless=True,
        )
        page = browser.new_page(viewport=viewport)
        page.goto("http://127.0.0.1:8501/")
        panel = page.locator(".st-key-right_controls")
        panel.wait_for()
        page.wait_for_function("""() => {
            const panel = document.querySelector('.st-key-right_controls');
            return panel && getComputedStyle(panel).overscrollBehaviorY === 'contain';
        }""")
        chart = page.get_by_test_id("stPlotlyChart")
        chart.wait_for()
        size = panel.evaluate("e => ({height: e.clientHeight, content: e.scrollHeight})")
        assert size["content"] > size["height"]
        assert size["height"] == pytest.approx(viewport["height"] - 272, abs=2)
        main = page.get_by_test_id("stMain")
        page_scroll = main.evaluate("e => e.scrollTop")
        chart_y = chart.bounding_box()["y"]
        panel.hover(position={"x": 5, "y": 100})
        page.mouse.wheel(0, 400)
        page.wait_for_function(
            "() => document.querySelector('.st-key-right_controls').scrollTop > 0"
        )
        assert chart.bounding_box()["y"] == pytest.approx(chart_y, abs=0.5)
        assert main.evaluate("e => e.scrollTop") == page_scroll
        # Reaching either edge must not hand the wheel gesture to the main page.
        for end, delta in [("e.scrollHeight", 600), ("0", -600)]:
            panel.evaluate(f"e => {{ e.scrollTop = {end}; }}")
            page.mouse.wheel(0, delta)
            page.wait_for_timeout(250)
            assert chart.bounding_box()["y"] == pytest.approx(chart_y, abs=0.5)
            assert main.evaluate("e => e.scrollTop") == page_scroll
        assert page.get_by_test_id("stException").count() == 0
        browser.close()


@pytest.mark.parametrize("width,height", [(320, 740), (390, 844)])
def test_phone_panels_reopen_without_losing_settings(width, height, tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("BRIDGETRUSS_CHROME", "/usr/bin/google-chrome"),
            headless=True,
            args=["--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(
            viewport={"width": width, "height": height}, is_mobile=True, has_touch=True
        )
        page.goto("http://127.0.0.1:8501/")
        chart = page.get_by_test_id("stPlotlyChart")
        chart.wait_for()
        panel = page.locator(".st-key-right_controls")
        panel.wait_for(state="hidden")
        sidebar = page.get_by_test_id("stSidebar")
        assert sidebar.get_attribute("data-collapsed") == "true"
        assert chart.bounding_box()["width"] >= width - 32
        baseline = page.get_by_test_id("stMetricValue").first.inner_text()
        page.get_by_test_id("stExpandSidebarButton").click()
        page.get_by_role("heading", name="Model tools", exact=True).wait_for()
        assert sidebar.get_attribute("data-collapsed") == "false"
        sidebar.get_by_role("button", name="Collapse sidebar", exact=True).click()
        page.get_by_text("Controls", exact=True).click()
        panel.wait_for()
        box = panel.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert box["y"] + box["height"] <= height
        front = page.get_by_role("spinbutton", name="Front axle (kN)", exact=True)
        front.fill("95")
        # Hiding the panel also retains unsubmitted form edits on the client.
        page.get_by_role("button", name="Hide controls", exact=True).click()
        panel.wait_for(state="hidden")
        page.get_by_text("Controls", exact=True).click()
        panel.wait_for()
        assert float(front.input_value()) == 95
        page.get_by_role("button", name="Apply vehicle settings", exact=True).click()
        page.get_by_text("Workspace updated.", exact=True).wait_for()
        assert page.get_by_test_id("stMetricValue").first.inner_text() == baseline
        page.get_by_text("Show node IDs", exact=True).click()
        page.get_by_role("button", name="Hide controls", exact=True).click()
        panel.wait_for(state="hidden")
        page.get_by_role("button", name="Analyze", exact=True).click()
        page.get_by_text("Controls", exact=True).click()
        panel.wait_for()
        assert not page.get_by_role("checkbox", name="Show node IDs", exact=True).is_checked()
        assert float(front.input_value()) == 95
        page.get_by_role("button", name="Hide controls", exact=True).click()
        panel.wait_for(state="hidden")
        page.get_by_role("tab", name="Interactive 3D", exact=True).click()
        page.get_by_test_id("bridge-live-scene").locator("canvas").first.wait_for()
        assert page.get_by_test_id("bridge-live-scene").bounding_box()["width"] <= width
        assert page.evaluate("document.documentElement.scrollWidth") <= width
        assert page.get_by_test_id("stException").count() == 0
        page.screenshot(path=str(tmp_path / f"phone-{width}.png"), full_page=True)
        browser.close()


def test_desktop_controls_toggle_expands_dashboard_and_preserves_choice():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("BRIDGETRUSS_CHROME", "/usr/bin/google-chrome"),
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1680, "height": 1050})
        page.goto("http://127.0.0.1:8501/")
        panel = page.locator(".st-key-right_controls")
        panel.wait_for()
        chart = page.get_by_test_id("stPlotlyChart")
        chart.wait_for()
        original_width = chart.bounding_box()["width"]
        page.get_by_text("Controls", exact=True).click()
        panel.wait_for(state="hidden")
        page.wait_for_function(
            """width =>
            document.querySelector('[data-testid="stPlotlyChart"]').getBoundingClientRect().width > width
        """,
            arg=original_width + 100,
        )
        page.get_by_role("button", name="Analyze", exact=True).click()
        assert not panel.is_visible()
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(400)
        assert not panel.is_visible()
        page.get_by_text("Controls", exact=True).click()
        panel.wait_for()
        page.set_viewport_size({"width": 1680, "height": 1050})
        page.wait_for_timeout(400)
        assert panel.is_visible()
        assert page.get_by_test_id("stException").count() == 0
        browser.close()


def test_smooth_motion_keeps_scene_and_camera_mounted():
    playwright = pytest.importorskip("playwright.sync_api")
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=os.environ.get("BRIDGETRUSS_CHROME", "/usr/bin/google-chrome"),
            headless=True,
            args=["--enable-unsafe-swiftshader"],
        )
        page = browser.new_page(viewport={"width": 1680, "height": 1050})
        page.goto("http://127.0.0.1:8501/")
        page.get_by_role("tab", name="Interactive 3D", exact=True).click()
        host = page.get_by_test_id("bridge-live-scene")
        host.locator("canvas").first.wait_for()
        page.get_by_role("button", name="Play", exact=True).click()
        page.get_by_role("button", name="Pause", exact=True).wait_for()
        host.scroll_into_view_if_needed()
        page.wait_for_function(
            "() => Number(document.querySelector('.bridge-live-scene')?.dataset.frames) > 5"
        )
        samples = page.evaluate("""async () => {
            const host = document.querySelector('.bridge-live-scene');
            const graph = host.querySelector('.bridge-live-plot');
            await window.Plotly.relayout(graph, {'scene.camera.eye': {x: 0.7, y: -2, z: 0.5}});
            const start = performance.now(), samples = [];
            const first = Number(host.dataset.frames);
            while (performance.now() - start < 1500) {
                samples.push(Number(host.dataset.frontX));
                await new Promise(resolve => setTimeout(resolve, 20));
            }
            return {samples, seconds: (performance.now() - start) / 1000,
                    frames: Number(host.dataset.frames) - first,
                    same: host === document.querySelector('.bridge-live-scene'),
                    eye: graph.layout.scene.camera.eye, error: host.dataset.error};
        }""")
        assert samples["same"] and not samples.get("error")
        assert samples["frames"] / samples["seconds"] > 10
        assert len(set(samples["samples"])) > 10
        assert all(b >= a for a, b in zip(samples["samples"], samples["samples"][1:]))
        assert samples["eye"]["x"] == pytest.approx(0.7)
        print(f"Rendered playback rate: {samples['frames'] / samples['seconds']:.1f} fps")
        page.get_by_role("button", name="Pause", exact=True).click()
        page.get_by_role("button", name="Play", exact=True).wait_for()
        page.wait_for_function("""() => {
            const h = document.querySelector('.bridge-live-scene');
            if (!h || h.dataset.playing !== 'false') return false;
            return Math.abs(Number(h.dataset.frontX) - h.bridgeAnimation.packet.clock.solved) < 1e-7;
        }""")
        paused = host.get_attribute("data-front-x")
        page.wait_for_timeout(400)
        assert host.get_attribute("data-front-x") == paused
        page.get_by_role("button", name="Reset", exact=True).click()
        page.wait_for_function("""() => {
            const h = document.querySelector('.bridge-live-scene');
            return h?.dataset.frontX !== undefined && Math.abs(Number(h.dataset.frontX)) < 0.001;
        }""")
        assert page.get_by_test_id("stException").count() == 0
        browser.close()
