"""Run with the lightweight web environment; no Qt/VTK dependency is needed."""

import json
from pathlib import Path
import pytest
from web.demo import PRESETS, run_example, verification_rows


def test_default_bridge_matches_verified_results():
    study = run_example(next(iter(PRESETS)))
    base, removed = study["cases"][0], study["cases"][4]
    assert base["peak_abs_uy_m"] == pytest.approx(0.019767714965005935)
    assert removed["peak_abs_uy_m"] == pytest.approx(0.020581917334809033)
    assert removed["member_comparison"][14]["candidate_force_N"] == pytest.approx(
        251642.78253111252
    )
    assert removed["member_comparison"][9]["candidate_force_N"] == pytest.approx(-21200)
    assert removed["snapshot"]["forces_N"][17] is None
    assert study["comparison_front_x_m"] == pytest.approx(14)
    json.dumps(study, allow_nan=False)


def test_triangle_reference_and_determinate_rejection():
    triangle = run_example(list(PRESETS)[1])
    assert triangle["axles_offset_m_force_N"] is None
    assert triangle["cases"][4]["peak_deflection_ratio"] == pytest.approx(2.914213562373095)
    failed = run_example(list(PRESETS)[2])
    assert failed["cases"][4]["status"] == "rejected"
    checks = verification_rows()
    assert len(checks) == 49 and all(row["passed"] for row in checks)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"remaining_percent": -1},
        {"remaining_percent": 101},
        {"front_kN": 501},
        {"rear_kN": -1},
        {"spacing_m": 16},
        {"moving": "yes"},
        {"front_kN": float("inf")},
    ],
)
def test_bounded_inputs(kwargs):
    with pytest.raises(ValueError):
        run_example(next(iter(PRESETS)), **kwargs)


def test_unknown_example():
    with pytest.raises(ValueError):
        run_example("../../not_an_example")


def test_streamlit_run_change_inputs_and_reject():
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest

    app = AppTest.from_file(str(Path(__file__).parent / "demo_app.py"), default_timeout=30).run()
    assert not app.exception
    assert not app.metric
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[1].value == "STABLE"
    assert app.metric[2].value.startswith("20.5819")
    assert app.session_state["study"]["selected_member"] == 18
    app.slider[0].set_value(50).run()
    assert not app.metric
    app.button[0].click().run()
    assert app.metric[2].value.startswith("19.9401")
    app.selectbox[0].select(list(PRESETS)[2]).run()
    assert not app.metric
    app.slider[0].set_value(0).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.metric[1].value == "REJECTED"
    assert app.warning
    app.selectbox[0].select(list(PRESETS)[1]).run()
    app.button[0].click().run()
    assert not app.exception
    assert app.session_state["study"]["axles_offset_m_force_N"] is None
    assert app.metric[1].value == "STABLE"
