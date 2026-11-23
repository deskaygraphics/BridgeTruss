"""Self-contained client animation; Streamlit only sends solved response snapshots."""

import json
from pathlib import Path

from plotly.offline import get_plotlyjs
from streamlit.components.v2 import component

from web.plots import CONFIG


_library = component(
    "bridgetruss_plotly_runtime",
    js=get_plotlyjs() + "\nexport default function() {}\n",
)
_scene = component(
    "bridgetruss_animated_scene",
    html=(
        '<div class="bridge-live-scene" data-testid="bridge-live-scene">'
        '<div class="bridge-live-plot"></div>'
        '<div class="bridge-live-position" role="status"></div></div>'
    ),
    css=(
        ".bridge-live-scene{width:100%;color:#edf2f8}"
        ".bridge-live-plot{height:450px;width:100%}"
        ".bridge-live-position{font-size:12px;padding:6px 10px;color:#b4c4d4}"
    ),
    js=Path(__file__).with_name("animation.js").read_text(),
    isolate_styles=False,
)


def load_animation_runtime():
    # Outside the timed fragment: never resend the library with response updates.
    _library(key="bridge_animation_runtime", height=0)


def animated_scene(fig, workspace, camera, fit):
    try:
        clock = workspace.playback_clock()
    except ValueError:
        clock = {
            "playing": False,
            "fraction": 0,
            "lo": 0,
            "hi": 1,
            "rate": 0,
            "solved": 0,
            "run": [workspace.revision, workspace.play_generation],
        }
    _scene(
        key="bridge_animated_scene",
        data={
            "figure": json.loads(fig.to_json()),
            "clock": clock,
            "config": CONFIG,
            "camera": camera,
            "fit": fit,
        },
        height=490,
    )


# Allow the running application to refresh the registered JS without losing models.
_bridge_loaded_stamp = (
    Path(__file__).stat().st_mtime_ns,
    Path(__file__).with_name("animation.js").stat().st_mtime_ns,
)
