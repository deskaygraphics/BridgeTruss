"""Run: python -m streamlit run web/app.py (from the repository root)."""

import csv
import io
import json
import sys
import threading
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import streamlit as st
from matplotlib.figure import Figure
from redundancy_plots import draw_comparison
from web.demo import PRESETS, run_example, verification_rows


st.set_page_config(page_title="BridgeTruss | CE 7405", layout="wide")


@st.cache_data(max_entries=128, show_spinner=False)
def calculate(*inputs):
    return run_example(*inputs)


@st.cache_data(show_spinner=False)
def verify():
    return verification_rows()


@st.cache_resource
def plot_lock():
    return threading.RLock()


def summary_rows(study):
    return [
        {
            "Area remaining (%)": row["area_factor"] * 100,
            "Status": row["status"],
            "Peak |uy| (mm)": row.get("peak_abs_uy_m", 0) * 1000
            if row["status"] == "stable"
            else None,
            "Deflection / baseline": row.get("peak_deflection_ratio"),
            "Critical node": row.get("critical_node"),
            "Deflection front x (m)": row.get("deflection_front_x_m"),
            "Peak |N| (kN)": row.get("peak_abs_force_N", 0) / 1000
            if row["status"] == "stable"
            else None,
            "Critical original member": row.get("critical_member"),
            "Force front x (m)": row.get("force_front_x_m"),
            "Rejection reason": row.get("reason", ""),
        }
        for row in study["cases"]
    ]


def main():
    st.title("BridgeTruss")
    st.caption("CE 7405 • Desmond Kangah • planar matrix analysis • audience demo")
    st.markdown(
        "**Engineering question:** How does reducing one member’s stiffness change "
        "load sharing, deflection and stability?"
    )
    st.info(
        "Try it in under a minute: keep the redundant bridge preset, leave area at 0%, "
        "and press Run example. Does an unchanged global maximum force mean nothing changed?"
    )
    preset = st.selectbox("Example", list(PRESETS))
    triangle = PRESETS[preset][0] == "benchmark_redundant.json"
    c1, c2 = st.columns(2)
    with c1:
        percent = st.slider("Selected member area remaining (%)", 0, 100, 0, 25)
        st.caption("0% physically removes the member. The baseline is always retained.")
    with c2:
        moving = st.checkbox(
            "Include complete vehicle passage",
            value=not triangle,
            disabled=triangle,
            key=f"moving_{triangle}",
        )
        st.caption(
            "Existing static loads remain active. The triangle uses its static hand-check load."
        )
    with st.expander("Vehicle inputs (optional)"):
        cols = st.columns(3)
        front = cols[0].number_input("Front axle (kN)", 0.0, 500.0, 80.0, 10.0, disabled=triangle)
        rear = cols[1].number_input("Rear axle (kN)", 0.0, 500.0, 120.0, 10.0, disabled=triangle)
        spacing = cols[2].number_input("Axle spacing (m)", 0.0, 15.0, 4.0, 1.0, disabled=triangle)
    inputs = (preset, percent, bool(moving), front, rear, spacing)
    if st.session_state.get("calculated_inputs") != inputs:
        st.session_state.pop("study", None)
    if st.button("Run example", type="primary"):
        try:
            with st.spinner("Solving the baseline and area-factor cases…"):
                st.session_state["study"] = calculate(*inputs)
                st.session_state["calculated_inputs"] = inputs
        except ValueError as exc:
            st.error(str(exc))
    study = st.session_state.get("study")
    if study is not None:
        index = next(
            i for i, row in enumerate(study["cases"]) if row["area_factor"] == percent / 100
        )
        row, baseline = study["cases"][index], study["cases"][0]
        st.subheader(f"Original member M{study['selected_member']}: {percent}% area remaining")
        st.caption(
            f"Endpoints: {study['selected_endpoints']}. {study['loading']}. "
            "Stable means accepted by the stiffness check—not safe by a design code."
        )
        metrics = st.columns(3)
        metrics[0].metric("Baseline peak |uy|", f"{baseline['peak_abs_uy_m'] * 1000:.6g} mm")
        metrics[1].metric("Candidate status", row["status"].upper())
        if row["status"] == "stable":
            ratio = row["peak_deflection_ratio"]
            metrics[2].metric(
                "Candidate peak |uy|",
                f"{row['peak_abs_uy_m'] * 1000:.6g} mm",
                f"{(ratio - 1) * 100:.3f}% vs baseline" if ratio is not None else None,
                delta_color="inverse",
            )
        else:
            st.warning(row["reason"] + ". No finite response is assigned to this case.")
        pos = study["comparison_front_x_m"]
        st.markdown(
            "**Force diagrams and member differences use "
            + (
                "the same static loads.**"
                if pos is None
                else f"the same front-axle x = {pos:.6g} m.**"
            )
            + " Envelope peaks below may occur at different positions."
        )
        plots, tables, assumptions = st.tabs(
            ["Comparison figures", "Numerical results", "Assumptions"]
        )
        with plots:
            with plot_lock():
                figure = Figure(figsize=(13, 8))
                draw_comparison(figure, study, index)
                st.pyplot(figure, clear_figure=True)
        with tables:
            st.dataframe(summary_rows(study), hide_index=True)
            if row["status"] == "stable":
                st.markdown("**Member forces at the common load case** (+ tension / − compression)")
                members = [
                    {
                        "Original member": m["member_id"],
                        "Endpoints": f"{m['node_i']}–{m['node_j']}",
                        "Present": m["present"],
                        "Baseline N (kN)": m["baseline_force_N"] / 1000,
                        "Candidate N (kN)": m["candidate_force_N"] / 1000 if m["present"] else None,
                        "Change N (kN)": m["delta_force_N"] / 1000 if m["present"] else None,
                    }
                    for m in row["member_comparison"]
                ]
                st.dataframe(members, hide_index=True)
                st.markdown("**Nodal displacements at the same common load case**")
                st.dataframe(
                    [
                        {
                            "Node": nid,
                            "Baseline ux (mm)": baseline["snapshot"]["U_m"][2 * i] * 1000,
                            "Candidate ux (mm)": row["snapshot"]["U_m"][2 * i] * 1000,
                            "Baseline uy (mm)": baseline["snapshot"]["U_m"][2 * i + 1] * 1000,
                            "Candidate uy (mm)": row["snapshot"]["U_m"][2 * i + 1] * 1000,
                        }
                        for i, nid in enumerate(study["node_ids"])
                    ],
                    hide_index=True,
                )
                st.caption(
                    f"Common-case relative residual: {row['snapshot']['relative_residual']:.3e}; "
                    f"stiffness condition estimate: {row['snapshot']['condition_number']:.3e}."
                )
        with assumptions:
            st.write(study["limitations"])
            st.write(
                "The bridge has a 25 m span, 4 m height, E = 200 GPa and baseline A = 0.005 m². "
                "Four static 50 kN loads remain active. The extra diagonal crosses another bar "
                "without connecting to it. The triangle instead uses its shipped 1 kN apex load."
            )
            st.write("Changing any input clears the results; press Run example again.")
        content = json.dumps(study, indent=2, allow_nan=False)
        st.download_button(
            "Download reproducible study JSON",
            content,
            "bridgetruss_study.json",
            "application/json",
        )
        stream = io.StringIO()
        rows = summary_rows(study)
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
        st.download_button(
            "Download summary CSV", stream.getvalue(), "bridgetruss_summary.csv", "text/csv"
        )
    with st.expander("Independent verification: triangle hand equations and quantified errors"):
        st.latex(r"f=(\sqrt{2}+1/2)L_v/(EA),\quad k_4=\alpha EA/L_v,\quad Q=P/(1+k_4f)")
        st.markdown(
            "Equilibrium: P = Q + k₄δ. Compatibility: δ = Qf. "
            "Apex uy = −Qf; tie N = Q/2; diagonal N = −Q/√2. "
            "P = 1000 N, EA = 2×10⁹ N, Lv = 1 m."
        )
        checks = verify()
        st.success(
            f"{sum(r['passed'] for r in checks)}/{len(checks)} analytical comparisons passed."
        )
        st.dataframe(
            [
                {
                    **r,
                    **{
                        k: f"{r[k]:.6e}"
                        for k in ("reference", "computed", "absolute_error", "absolute_tolerance")
                    },
                }
                for r in checks
            ],
            hide_index=True,
        )
        st.caption(
            "Hand-reference equations are independent of the stiffness assembly. "
            "Near-roundoff agreement verifies these cases, not real-bridge prediction accuracy."
        )
    st.divider()
    st.caption(
        "Educational, linear-elastic analysis only. No buckling, yielding, dynamics, "
        "spatial stability, progressive-collapse or design-code certification. "
        "AI-assisted development; the author is responsible for verification and interpretation."
    )
    st.link_button(
        "Source and desktop application", "https://github.com/deskaygraphics/BridgeTruss"
    )


if __name__ == "__main__":
    main()
