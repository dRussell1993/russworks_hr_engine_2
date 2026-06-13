from __future__ import annotations

from pathlib import Path
from typing import Any

from .loaders import available_output_dates, load_dashboard_outputs
from . import views


PAGES = [
    "Overview",
    "Top HR Targets",
    "Team Clusters",
    "Step 5 Slips",
    "Confidence / Risk",
    "Validation Warnings",
    "Command Center",
]


def main() -> None:
    st = _load_streamlit()
    if _should_bootstrap_streamlit(st):
        _bootstrap_streamlit()
        return
    render_app(st)


def render_app(st: Any) -> None:
    st.set_page_config(page_title="Russ-Works Command Dashboard", layout="wide")
    st.title("Russ-Works HR Engine")
    st.caption("Local operator dashboard for generated Russ-Works outputs.")

    dates = available_output_dates("data")
    selected_date = st.sidebar.selectbox("Report date", dates or [""], index=0)
    page = st.sidebar.radio("Page", PAGES)
    data = load_dashboard_outputs(date=selected_date or None, data_root="data")

    if data.missing_files:
        st.sidebar.warning("Missing outputs: " + ", ".join(data.missing_files))
    st.sidebar.caption("Run `python -m russworks.run --date YYYY-MM-DD` to refresh outputs.")

    if page == "Overview":
        _render_overview(st, data)
    elif page == "Top HR Targets":
        _render_targets(st, data)
    elif page == "Team Clusters":
        _render_clusters(st, data)
    elif page == "Step 5 Slips":
        _render_slips(st, data)
    elif page == "Confidence / Risk":
        _render_confidence(st, data)
    elif page == "Validation Warnings":
        _render_validation(st, data)
    elif page == "Command Center":
        _render_command_center(st, data)


def _render_overview(st: Any, data) -> None:
    st.subheader("Overview")
    _table(st, views.overview_metrics(data))
    if data.operator_report:
        with st.expander("Operator Report Preview"):
            st.markdown(views.operator_report_preview(data))


def _render_targets(st: Any, data) -> None:
    st.subheader("Top HR Targets")
    _table(st, views.top_hr_targets(data, limit=50))


def _render_clusters(st: Any, data) -> None:
    st.subheader("Team Clusters")
    _table(st, views.team_clusters(data))


def _render_slips(st: Any, data) -> None:
    st.subheader("Step 5 Slips")
    grouped = views.slip_cards(data)
    if not grouped:
        st.info("No Step 5 slips found.")
        return
    for slip_type, cards in grouped.items():
        st.markdown(f"### {slip_type}")
        for card in cards:
            with st.container(border=True):
                st.markdown(f"**{card['name']}**")
                st.caption(f"Confidence: {card['confidence']} | Teams: {', '.join(card['teams'])}")
                st.write(", ".join(card["batters"]))
                if card["justification"]:
                    st.write(card["justification"])


def _render_confidence(st: Any, data) -> None:
    st.subheader("Confidence / Risk")
    st.markdown("#### Confidence")
    _table(st, views.confidence_rows(data))
    st.markdown("#### Risk")
    _table(st, views.risk_rows(data))


def _render_validation(st: Any, data) -> None:
    st.subheader("Validation Warnings")
    _table(st, views.validation_warning_rows(data))


def _render_command_center(st: Any, data) -> None:
    st.subheader("Command Center")
    _table(st, views.command_center_rows(data))


def _table(st: Any, rows: list[dict[str, Any]]) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No records found.")


def _load_streamlit() -> Any:
    try:
        import streamlit as st
    except ImportError as exc:
        raise SystemExit(
            "Streamlit is required for the local UI. Install dependencies with `pip install -e .` "
            "or install Streamlit directly with `pip install streamlit`."
        ) from exc
    return st


def _should_bootstrap_streamlit(st: Any) -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx
    except Exception:
        return False
    return get_script_run_ctx() is None


def _bootstrap_streamlit() -> None:
    from streamlit.web import bootstrap

    bootstrap.run(str(Path(__file__).resolve()), False, [], {})


if __name__ == "__main__":
    main()
