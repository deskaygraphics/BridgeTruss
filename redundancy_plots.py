"""Shared desktop/report figures built only from a completed study snapshot."""

from matplotlib.colors import Normalize
from matplotlib.cm import ScalarMappable
from matplotlib.ticker import MaxNLocator


def draw_comparison(figure, study, case_index):
    """Render common-load-case force diagrams and independent peak deflections."""
    figure.clear()
    axes = figure.subplots(2, 2)
    baseline = study["cases"][0]
    candidate = study["cases"][case_index]
    nodes = {n["id"]: n["xyz"] for n in study["model"]["nodes"]}
    span = max(p[0] for p in nodes.values()) - min(p[0] for p in nodes.values()) or 1
    bottom = min(p[1] for p in nodes.values())
    height = max(p[1] for p in nodes.values()) - bottom or span * 0.2
    members = study["model"]["members"]
    all_forces = list(baseline["snapshot"]["forces_N"])
    if candidate["status"] == "stable":
        all_forces += [v for v in candidate["snapshot"]["forces_N"] if v is not None]
    limit = max(max(abs(v) for v in all_forces) / 1000, 1e-12)
    norm = Normalize(-limit, limit)
    cmap = "coolwarm"
    mapper = ScalarMappable(norm=norm, cmap=cmap)
    for ax, row, title in (
        (axes[0, 0], baseline, "Baseline: A/A0 = 1"),
        (axes[0, 1], candidate, f"Candidate: A/A0 = {candidate['area_factor']:g}"),
    ):
        for m in members:
            p, q = nodes[m["i"]], nodes[m["j"]]
            present = m["id"] in row["member_ids"]
            force = (
                row["snapshot"]["forces_N"][m["id"] - 1] / 1000
                if row["status"] == "stable" and present
                else None
            )
            ax.plot(
                [p[0], q[0]],
                [p[1], q[1]],
                color=mapper.to_rgba(force) if force is not None else "#999999",
                linestyle="-" if present else "--",
                linewidth=2.5,
            )
            # Crossing bars can share a midpoint without forming a joint.
            dx, dy = q[0] - p[0], q[1] - p[1]
            if dx < 0:
                dx, dy = -dx, -dy
            x, y = (p[0] + q[0]) / 2, (p[1] + q[1]) / 2
            if dx and dy:
                y += height * (0.25 if dy > 0 else -0.25)
            elif not dx:
                x -= span * 0.025
            else:
                y += height * (-0.3 if abs(y - bottom) < 1e-9 else 0.3)
            ax.update_datalim([(x, y)])
            ax.annotate(
                f"M{m['id']}" + (f"\n{force:.2f}" if force is not None else ""),
                (x, y),
                fontsize=7,
                ha="center",
                va="center",
                bbox=dict(facecolor="white", alpha=0.65, edgecolor="none", pad=0.2),
            )
        for nid, (x, y, _) in nodes.items():
            ax.plot(x, y, "ko", markersize=3)
            ax.annotate(f"N{nid}", (x, y), xytext=(2, -9), textcoords="offset points", fontsize=6)
        if row["status"] != "stable":
            title += "\nRejected: no force solution"
        ax.set_title(title, fontsize=9)
        ax.set_aspect("equal", adjustable="datalim")
        ax.margins(0.15, 0.3)
        ax.set_xlabel("x (m)", fontsize=8)
        ax.set_ylabel("y (m)", fontsize=8)
        ax.grid(alpha=0.15)
    figure.colorbar(
        mapper, ax=list(axes[0]), label="Axial force (kN): + tension / − compression", shrink=0.7
    )
    ax = axes[1, 0]
    if candidate["status"] == "stable":
        comparison = [r for r in candidate["member_comparison"] if r["present"]]
        ax.bar(
            [r["member_id"] for r in comparison],
            [r["delta_force_N"] / 1000 for r in comparison],
            color="#3479b7",
        )
        ax.axhline(0, color="gray", lw=0.7)
        ax.set_xlabel("Original member ID")
        ax.xaxis.set_major_locator(MaxNLocator(integer=True))
        ax.set_ylabel("Candidate − baseline (kN)")
        ax.set_title("Redistribution at the same load case", fontsize=9)
        ax.text(
            0.02,
            0.98,
            "Removed member omitted" if candidate["removed"] else "",
            va="top",
            transform=ax.transAxes,
            fontsize=7,
        )
    else:
        ax.axis("off")
        ax.text(
            0.02,
            0.95,
            candidate["reason"] + "\nNo artificial stiffness or finite response assigned.",
            va="top",
            wrap=True,
            transform=ax.transAxes,
            fontsize=9,
        )
    ax = axes[1, 1]
    stable = sorted(
        (r for r in study["cases"] if r["status"] == "stable"), key=lambda r: r["area_factor"]
    )
    ax.plot(
        [r["area_factor"] for r in stable],
        [r["peak_abs_uy_m"] * 1000 for r in stable],
        "o-",
        color="#3479b7",
    )
    if candidate["status"] == "stable":
        ax.plot(
            candidate["area_factor"],
            candidate["peak_abs_uy_m"] * 1000,
            "o",
            color="#d04d40",
            markersize=8,
        )
    rejected = [r["area_factor"] for r in study["cases"] if r["status"] != "stable"]
    if rejected:
        ax.text(
            0.03,
            0.97,
            "Rejected factors: " + ", ".join(f"{f:g}" for f in rejected),
            transform=ax.transAxes,
            va="top",
            fontsize=8,
        )
    ax.set_xlabel("Selected member area factor A/A0 (0 = removed)")
    ax.set_ylabel("Peak |uy| (mm)")
    ax.set_title(
        "Full-passage peaks"
        if study["axles_offset_m_force_N"] is not None
        else "Static peak deflection",
        fontsize=9,
    )
    ax.grid(alpha=0.2)
    position = study["comparison_front_x_m"]
    label = "static loads" if position is None else f"shared front x = {position:.6g} m"
    figure.suptitle(
        f"M{study['selected_member']} stiffness/removal study | force diagrams: {label}\n"
        "Linear elastic; no collapse or buckling prediction. Independent envelope peaks are not simultaneous.",
        fontsize=10,
    )
    figure.set_layout_engine("constrained")
