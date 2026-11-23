"""Browser animation payloads; no Qt, VTK, Streamlit or third-party JavaScript."""

import json
from pathlib import Path

from example_studies import vehicle_example
from moving_loads import MovingResponse, travel_limits


def animation_payload(
    preset, front_kN=80, rear_kN=120, spacing_m=4, vehicle_count=1, vehicle_gap_m=4
):
    model, axles = vehicle_example(
        preset, True, front_kN, rear_kN, spacing_m, vehicle_count, vehicle_gap_m
    )
    if axles is None:
        return None  # The hand-check triangle is static, even if requested otherwise.
    response = MovingResponse(model)
    ids = response.prepared.ids
    lo, hi = travel_limits(model, axles)
    epsilon = max(hi - lo, 1.0) * 1e-8
    return {
        "nodes": [[nid, *model.nodes[nid][:2]] for nid in ids],
        "members": [[member.a, member.b] for member in model.members],
        "supports": list(model.fixed),
        "deck": [[nid, model.nodes[nid][0]] for nid in response.deck_nodes],
        "deck_y": model.nodes[response.deck_nodes[0]][1],
        "axles": axles,
        "spacing": spacing_m,
        "gap": vehicle_gap_m,
        "types": ["truck", "passenger car", "bus"][:vehicle_count],
        "limits": [lo - epsilon, hi + epsilon],
        "static_u": response.displacements[:, 0].tolist(),
        "deck_unit_u": response.displacements[:, 1:].T.tolist(),
        "response_scope": "Unmodified baseline: static loads plus current convoy position",
    }


def animation_html(payload):
    """Embed finite JSON safely inside a fully self-contained component."""
    content = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    for character, escaped in (("<", "\\u003c"), (">", "\\u003e"), ("&", "\\u0026")):
        content = content.replace(character, escaped)
    template = Path(__file__).with_name("vehicle_scene.html").read_text(encoding="utf-8")
    return template.replace("__ANIMATION_DATA__", content)
