"""Report only the layout breakpoint; do not infer device type from user agents."""

from streamlit.components.v2 import component


_viewport = component(
    "bridgetruss_viewport",
    js="""
    export default function({parentElement, setStateValue}) {
        const query = window.matchMedia("(max-width: 767px)");
        const report = () => {
            if (parentElement.bridgeMobile !== query.matches) {
                parentElement.bridgeMobile = query.matches;
                setStateValue("mobile", query.matches);
            }
        };
        report();
        query.addEventListener("change", report);
        return () => query.removeEventListener("change", report);
    }
    """,
)


def phone_layout():
    result = _viewport(
        key="bridge_viewport",
        default={"mobile": None},
        height=0,
        on_mobile_change=lambda: None,
    )
    return result.mobile
