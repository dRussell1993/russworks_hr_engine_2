from __future__ import annotations

from pathlib import Path
from typing import Any

from russworks.ui.loaders import discover_outputs, load_dashboard_outputs
from russworks.ui import views


PAGES = [
    "Overview",
    "Top HR Targets",
    "Team Clusters",
    "Step 5 Slips",
    "Confidence / Risk",
    "Accuracy Review",
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
    st.set_page_config(page_title="Hype Man Sports - Russ-Works HR Engine", layout="wide")
    _inject_theme(st)
    st.markdown("<h1>Hype Man Sports - Russ-Works HR Engine</h1>", unsafe_allow_html=True)
    st.caption("Local operator command dashboard for Russ-Works HR outputs.")

    discovery = discover_outputs()
    manual_root = st.sidebar.text_input("Manual output data directory", value="")
    date_options = discovery.available_dates or [""]
    selected_date = st.sidebar.selectbox("Report date", date_options, index=0)
    page = st.sidebar.radio("Page", PAGES)
    data = load_dashboard_outputs(date=selected_date or None, data_root=manual_root or None)

    st.sidebar.caption(f"Data source: **{data.source_label}**")
    st.sidebar.caption(f"Active data root: `{data.data_root or 'not found'}`")
    if data.missing_files:
        st.sidebar.error("Missing outputs detected")
        with st.sidebar.expander("Searched paths"):
            for path in data.searched_paths:
                st.code(path)

    if data.missing_files:
        st.warning(data.missing_output_message)
    if data.placeholder_warnings:
        st.warning("Placeholder-looking data detected. Verify this dashboard is not loading sample or test output.")
        with st.expander("Placeholder data warnings", expanded=False):
            _table(st, views.placeholder_warning_rows(data))

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
    elif page == "Accuracy Review":
        _render_accuracy(st, data)
    elif page == "Validation Warnings":
        _render_validation(st, data)
    elif page == "Command Center":
        _render_command_center(st, data)


def _render_overview(st: Any, data) -> None:
    st.subheader("Overview")
    cols = st.columns(4)
    for index, row in enumerate(views.overview_metrics(data)):
        cols[index % 4].metric(str(row["Metric"]), row["Value"])
    st.markdown("### Data Source")
    _table(st, views.data_source_rows(data))
    st.markdown("### Output Health")
    _table(st, views.missing_output_rows(data) or [{"Status": "Ready", "Message": "All expected dashboard outputs were found."}])
    _render_postmortem_status(st, data)
    if data.operator_report:
        with st.expander("Operator Report Preview", expanded=False):
            st.markdown(views.operator_report_preview(data))


def _render_targets(st: Any, data) -> None:
    st.subheader("Top HR Targets")
    options = views.filter_options(data)
    cols = st.columns(4)
    team = cols[0].selectbox("Team", ["", *options["teams"]])
    tier = cols[1].selectbox("Tier", ["", *options["tiers"]])
    confidence = cols[2].selectbox("Confidence", ["", *options["confidence"]])
    non_superstar = cols[3].checkbox("Non-superstar only")
    rows = views.top_hr_targets(
        data,
        limit=200,
        team=team,
        tier=tier,
        confidence=confidence,
        non_superstar_only=non_superstar,
    )
    _table(st, rows)
    _legend(st)


def _render_clusters(st: Any, data) -> None:
    st.subheader("Team Clusters")
    for card in views.cluster_cards(data):
        with st.container(border=True):
            st.markdown(
                f"### {card['Team']} {_badge(card['TAG'], 'tag')} {_badge(card['CPS'], 'cps')} {_badge(card['Label'], 'tier')}",
                unsafe_allow_html=True,
            )
            st.caption(f"Opponent: {card['Opponent']} | Cluster Score: {card['Cluster Score']} | Confidence: {card['Confidence']}")
            st.write(f"Captain: **{card['Captain']}**")
            st.write(f"Hidden beneficiary: **{card['Hidden Beneficiary']}**")
            if card.get("Warnings"):
                st.warning(card["Warnings"])


def _render_slips(st: Any, data) -> None:
    st.subheader("Step 5 Slips")
    grouped = views.slip_cards(data)
    if not grouped:
        st.info("No Step 5 slips found.")
        return
    tabs = st.tabs([group for group in views.SLIP_GROUP_ORDER if group in grouped])
    for tab, group in zip(tabs, [group for group in views.SLIP_GROUP_ORDER if group in grouped]):
        with tab:
            for card in grouped[group]:
                with st.container(border=True):
                    st.markdown(f"### {card['name']} {_badge(card['confidence'], 'confidence')}", unsafe_allow_html=True)
                    st.caption(f"Teams: {', '.join(card['teams'])}")
                    _table(st, card["legs"])
                    if card["justification"]:
                        st.write(card["justification"])
                    if card["risk_warning"]:
                        st.warning(card["risk_warning"])


def _render_confidence(st: Any, data) -> None:
    st.subheader("Confidence / Risk")
    st.markdown("### Confidence")
    _table(st, views.confidence_rows(data))
    st.markdown("### Portfolio / Simulation Risk")
    _table(st, views.risk_rows(data))
    st.markdown("### Exposure Warnings")
    _table(st, views.exposure_warning_rows(data))


def _render_accuracy(st: Any, data) -> None:
    st.subheader("Accuracy Review")
    metrics = views.accuracy_metric_rows(data)
    if metrics:
        cols = st.columns(min(5, len(metrics)))
        for index, row in enumerate(metrics):
            cols[index % len(cols)].metric(str(row["Metric"]), row["Value"])
    else:
        st.info("No post-mortem accuracy review found yet.")
    st.markdown("### Production Readiness / Match Integrity")
    _table(st, views.production_readiness_rows(data))
    placeholders = views.placeholder_prediction_rows(data)
    if placeholders:
        st.warning("Placeholder prediction data detected; calibration disabled for this run.")
        _table(st, placeholders)
    st.markdown("### Hit Rates")
    for title, rows in views.accuracy_hit_rate_sections(data).items():
        st.markdown(f"#### {title}")
        _table(st, rows)
    st.markdown("### Top Missed HRs")
    _table(st, views.accuracy_false_negative_rows(data))
    st.markdown("### Top Over-Ranked Misses")
    _table(st, views.accuracy_false_positive_rows(data))
    st.markdown("### Module Performance")
    _table(st, views.accuracy_module_rows(data))
    st.markdown("### Calibration Recommendations")
    _table(st, views.accuracy_recommendation_rows(data))


def _render_validation(st: Any, data) -> None:
    st.subheader("Validation Warnings")
    _table(st, views.validation_warning_rows(data))
    if data.placeholder_warnings:
        st.markdown("### Placeholder Data Alerts")
        _table(st, views.placeholder_warning_rows(data))


def _render_command_center(st: Any, data) -> None:
    st.subheader("Command Center")
    st.markdown("### Pipeline Status")
    _table(st, views.command_center_rows(data))
    st.markdown("### Provider Health")
    _table(st, views.provider_health_rows(data))
    st.markdown("### Generated Outputs")
    _table(st, views.generated_output_rows(data))
    _render_postmortem_status(st, data)
    st.markdown("### Scheduler Status")
    _table(st, views.scheduler_rows(data))


def _render_postmortem_status(st: Any, data) -> None:
    st.markdown("### Post-Mortem Status")
    _table(st, views.postmortem_status_rows(data))
    st.caption("Run the end-of-day comparison after actual home run data is available:")
    st.code(views.postmortem_command(data), language="bash")
    if st.button("Show post-mortem command", key=f"postmortem-command-{data.selected_date}"):
        st.info("Run the command above from the repository root after the actual HR CSV is available.")


def _table(st: Any, rows: list[dict[str, Any]]) -> None:
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No records found.")


def _legend(st: Any) -> None:
    st.markdown(
        " ".join(
            [
                _badge("Elite Core / Diamond", "diamond"),
                _badge("Core Target / Gold", "gold"),
                _badge("Strong Play / Silver", "silver"),
                _badge("Value / Green", "green"),
                _badge("Chaos / Orange", "orange"),
                _badge("Fade / Red", "red"),
            ]
        ),
        unsafe_allow_html=True,
    )


def _badge(text: Any, badge_type: str = "neutral") -> str:
    return f"<span class='badge badge-{badge_type}'>{text}</span>"


def _inject_theme(st: Any) -> None:
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(135deg, #07111f 0%, #101827 48%, #07111f 100%);
            color: #edf2f7;
        }
        h1, h2, h3 { color: #f8fafc; letter-spacing: 0; }
        [data-testid="stSidebar"] {
            background: #0b1220;
            border-right: 1px solid #1f2937;
        }
        .badge {
            display: inline-block;
            padding: 0.18rem 0.5rem;
            border-radius: 999px;
            font-size: 0.78rem;
            font-weight: 700;
            margin: 0.1rem;
            border: 1px solid rgba(255,255,255,0.15);
        }
        .badge-diamond, .badge-tier { background: #0f766e; color: #ecfeff; }
        .badge-gold { background: #a16207; color: #fefce8; }
        .badge-silver { background: #475569; color: #f8fafc; }
        .badge-green { background: #166534; color: #f0fdf4; }
        .badge-orange { background: #c2410c; color: #fff7ed; }
        .badge-red { background: #991b1b; color: #fef2f2; }
        .badge-tag { background: #1d4ed8; color: #eff6ff; }
        .badge-cps { background: #7e22ce; color: #faf5ff; }
        .badge-confidence { background: #334155; color: #f8fafc; }
        .badge-neutral { background: #111827; color: #f8fafc; }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
