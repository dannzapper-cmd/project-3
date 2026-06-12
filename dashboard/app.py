"""Streamlit AI Operations Dashboard (PR-06 / PR-15 / PR-16).

Read-only visualization of PR-03/04/05 artifacts. Does not run pipelines.
Cloud mode uses bundled demo fixtures and an optional reviewer login gate.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.auth import render_login_gate
from dashboard.config import DashboardSettings
from dashboard.loaders import (
    derive_overview_status,
    derive_system_flow_steps,
    load_bentoml_build_summary,
    load_champion_challenger_comparison,
    load_decision_recommendations,
    load_decision_summary,
    load_evidently_artifact_status,
    load_mlops_loop_summary,
    load_registry_summary,
    load_synthetic_data_status,
)
from dashboard.paths import (
    CMD_DECISION_INTEL,
    CMD_DEMO_LOCAL,
    CMD_GENERATE_DATA,
    CMD_MLOPS_LOOP,
    CMD_REVIEWER_DEMO,
    CMD_TRAIN_ML,
)
from dashboard.types import LoaderMissing, LoaderOk, LoaderResult

st.set_page_config(
    page_title="InvForge AI Operations",
    page_icon="📊",
    layout="wide",
)

_FIXTURES_ROOT = Path(__file__).resolve().parent / "demo_fixtures"
_DEMO_SCENARIOS_PATH = _FIXTURES_ROOT / "demo_scenarios.json"
_SAMPLE_SCENARIO_PATH = _FIXTURES_ROOT / "samples" / "scenario.yaml"
_SAMPLE_API_PATH = _FIXTURES_ROOT / "samples" / "forecast_request.json"

_SECTION_ANCHORS = {
    "overview": "section-overview",
    "forecast-performance": "section-forecast",
    "decision-intelligence": "section-decision",
    "mlops-status": "section-mlops",
}

LIMITATIONS_LOCAL = [
    "All inputs are **synthetic** (seed 42); no real InvenTree inventory data.",
    "Cost and policy figures are **simulated backtest diagnostics**, not "
    "real-world savings claims.",
    "MLflow, Evidently, and BentoML artifacts are **local** to this machine.",
    "This dashboard is **not** production monitoring, alerting, or serving.",
    "Grafana, Prometheus, and Marquez lineage are **optional local profiles** "
    "— run separately via `make observability-up` or kind stacks.",
    "kind Kubernetes profiles are **local evidence** — not managed GKE/EKS/AKS.",
]

LIMITATIONS_CLOUD = [
    "All data is **synthetic** (seed 42) from committed demo fixtures.",
    "Cost metrics are **simulated backtest diagnostics** — not real savings.",
    "This is a **read-only portfolio demo**; no mutations or admin actions.",
    "MLflow, ZenML, InvenTree, and retraining remain **local-only**.",
]


def _section_anchor(name: str) -> None:
    anchor_id = _SECTION_ANCHORS.get(name, name)
    st.markdown(f'<div id="{anchor_id}"></div>', unsafe_allow_html=True)


def _load_demo_scenarios() -> dict[str, Any] | None:
    if not _DEMO_SCENARIOS_PATH.is_file():
        return None
    try:
        payload = json.loads(_DEMO_SCENARIOS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_sample_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _render_missing(
    result: LoaderMissing,
    *,
    settings: DashboardSettings,
    cloud_label: str = "Not bundled in cloud fixture",
) -> None:
    if settings.is_cloud_mode:
        st.info(f"**{cloud_label}** — cloud mode uses committed synthetic fixtures only.")
        st.caption(result["reason"])
        st.markdown(
            f"Regenerate locally: `{CMD_REVIEWER_DEMO}` then `make dashboard`."
        )
        return
    st.error("Status: **missing**")
    st.write(result["reason"])
    st.markdown("**Generate artifacts (local only):**")
    for command in result["commands"]:
        st.code(command, language="bash")


def _render_freshness(result: LoaderOk) -> None:
    st.caption(f"Last generated: {result['mtime']}")


def _status_badge(label: str, status: str) -> None:
    colors = {"ok": "🟢", "missing": "🟠"}
    st.metric(label, f"{colors.get(status, '⚪')} {status.upper()}")


def _metric_bar_chart(
    champion_name: str,
    challenger_name: str,
    champ_metrics: dict[str, Any],
    chal_metrics: dict[str, Any],
    metrics: tuple[str, ...] = ("mae", "rmse", "mape"),
) -> go.Figure | None:
    labels: list[str] = []
    champion_vals: list[float] = []
    challenger_vals: list[float] = []

    for metric in metrics:
        c_val = champ_metrics.get(metric)
        ch_val = chal_metrics.get(metric)
        if c_val is None and ch_val is None:
            continue
        if c_val is None or ch_val is None:
            continue
        labels.append(metric.upper())
        champion_vals.append(float(c_val))
        challenger_vals.append(float(ch_val))

    if not labels:
        return None

    fig = go.Figure(
        data=[
            go.Bar(name=champion_name, x=labels, y=champion_vals),
            go.Bar(name=challenger_name, x=labels, y=challenger_vals),
        ]
    )
    fig.update_layout(
        barmode="group",
        title="Forecast metrics (lower is better)",
        yaxis_title="Value",
        legend_title="Model",
    )
    return fig


def _fetch_api_health(base_url: str) -> dict[str, Any] | None:
    if not base_url:
        return None
    url = f"{base_url.rstrip('/')}/health"
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def _render_mission_control(settings: DashboardSettings) -> None:
    st.markdown("## Reviewer Mission Control")
    hero_left, hero_right = st.columns([3, 2])
    with hero_left:
        st.markdown(
            "**What this is:** Read-only AI Operations dashboard for synthetic "
            "inventory forecasting and decision intelligence."
        )
        st.markdown("**What to click first:**")
        st.markdown(
            "1. **Overview** — pipeline health at a glance  \n"
            "2. **Forecast Performance** — champion vs challenger  \n"
            "3. **Decision Intelligence** — reorder recommendations  \n"
            "4. **MLOps Status** — drift, registry, packaging"
        )
    with hero_right:
        if settings.is_cloud_mode:
            st.success(
                "**Cloud (this page):** bundled synthetic fixtures · read-only · "
                "no training on cold start"
            )
            st.info(
                f"**Local full pipeline:** `{CMD_REVIEWER_DEMO}` then `make dashboard`"
            )
        else:
            st.success(
                "**Local (this page):** reads generated workspace artifacts after "
                "the synthetic pipeline."
            )
            st.info(
                "**Cloud demo:** fixture-backed reviewer surface at the portfolio URL."
            )
        st.caption(
            "**Safety:** no mutations · no real customer data · demo auth is a "
            "reviewer gate, not production security."
        )


def _render_guided_scenarios(settings: DashboardSettings) -> None:
    st.markdown("## Guided Demo Scenarios")
    payload = _load_demo_scenarios()
    scenarios = (payload or {}).get("scenarios") or []
    if not scenarios:
        st.caption("Scenario cards load from bundled demo fixtures.")
        return

    cols = st.columns(3)
    for col, scenario in zip(cols, scenarios[:3], strict=False):
        with col:
            with st.container(border=True):
                st.markdown(f"**{scenario.get('subtitle', '')}**")
                st.markdown(f"### {scenario.get('title', 'Scenario')}")
                st.write(scenario.get("summary", ""))
                highlights = scenario.get("highlights") or {}
                if scenario.get("id") == "stockout_triage":
                    st.markdown(
                        f"- **SKU:** `{scenario.get('part_id', 'n/a')}` "
                        f"({scenario.get('risk_level', 'n/a')} risk)\n"
                        f"- **Prediction:** `{highlights.get('prediction')}`\n"
                        f"- **Reorder point:** `{highlights.get('reorder_point')}`\n"
                        f"- **Safety stock:** `{highlights.get('safety_stock')}`\n"
                        f"- **EOQ:** `{highlights.get('eoq')}`\n"
                        f"- **Stockout risk:** `{highlights.get('stockout_risk')}`"
                    )
                elif scenario.get("id") == "forecast_review":
                    st.markdown(
                        f"- **Champion:** `{scenario.get('champion')}`\n"
                        f"- **Challenger:** `{scenario.get('challenger')}`\n"
                        f"- **Decision:** `{scenario.get('decision')}`\n"
                        f"- **{highlights.get('primary_metric', 'mae').upper()}:** "
                        f"champion `{highlights.get('champion_mae')}` · "
                        f"challenger `{highlights.get('challenger_mae')}`\n"
                        f"- **Gap:** `{highlights.get('relative_improvement_pct')}%` "
                        "(within auto-promote threshold)"
                    )
                elif scenario.get("id") == "mlops_readiness":
                    drift = highlights.get("drift_detected")
                    drift_label = (
                        "Yes" if drift else "No" if drift is not None else "n/a"
                    )
                    st.markdown(
                        f"- **Drift detected:** {drift_label}\n"
                        f"- **Registry:** `{highlights.get('registry_strategy')}`\n"
                        f"- **Champion/challenger:** "
                        f"`{highlights.get('champion_challenger')}`\n"
                        f"- **BentoML packaging:** "
                        f"`{highlights.get('bentoml_packaging')}`\n"
                        f"- **Evidently reports:** "
                        f"`{highlights.get('evidently_reports')}`"
                    )
                    if settings.is_cloud_mode:
                        st.caption(
                            "Cloud shows committed fixtures; local runs regenerate "
                            "full MLOps artifacts."
                        )
                anchor = scenario.get("cta_anchor", "")
                anchor_id = _SECTION_ANCHORS.get(anchor, anchor)
                label = scenario.get("cta_label", "View section")
                st.markdown(
                    f'<a href="#{anchor_id}" target="_self">{label} ↓</a>',
                    unsafe_allow_html=True,
                )


def _render_sample_inputs(settings: DashboardSettings) -> None:
    st.markdown("## Sample Inputs")
    st.markdown(
        "Cloud mode displays committed sample inputs and generated artifacts. "
        "To regenerate the pipeline, run the local demo."
    )

    link_row1_a, link_row1_b, link_row1_c = st.columns(3)
    guide = settings.github_blob_url(settings.reviewer_guide_path)
    scenario_url = settings.github_blob_url("examples/demo-scenario/scenario.yaml")
    sample_api_url = settings.github_blob_url("examples/api/forecast_request.json")
    with link_row1_a:
        st.link_button("Reviewer guide", guide, use_container_width=True)
    with link_row1_b:
        st.link_button("Sample scenario YAML", scenario_url, use_container_width=True)
    with link_row1_c:
        st.link_button("Sample API JSON", sample_api_url, use_container_width=True)

    if settings.api_base_url:
        st.link_button(
            "API docs",
            f"{settings.api_base_url}/docs",
            use_container_width=False,
        )

    tab_yaml, tab_json, tab_skus, tab_cmds = st.tabs(
        ["Scenario YAML", "API JSON", "Fixture SKUs", "Local commands"]
    )
    scenario_text = _read_sample_file(_SAMPLE_SCENARIO_PATH)
    api_text = _read_sample_file(_SAMPLE_API_PATH)

    with tab_yaml:
        if scenario_text:
            st.code(scenario_text, language="yaml")
        else:
            st.caption("Bundled scenario sample not found; use the GitHub link above.")

    with tab_json:
        if api_text:
            st.code(api_text, language="json")
        else:
            st.caption("Bundled API sample not found; use the GitHub link above.")

    with tab_skus:
        st.markdown(
            "Representative part IDs from synthetic fixtures (seed 42):"
        )
        st.markdown(
            "- `PRT-0001` — regular demand, low risk\n"
            "- `PRT-0009` — intermittent, medium stockout risk\n"
            "- `PRT-0013` — intermittent, **high** stockout risk (Scenario A)\n"
            "- `PRT-0096` — regular, high stockout risk, long lead time"
        )

    with tab_cmds:
        st.code(
            "\n".join(
                [
                    f"{CMD_REVIEWER_DEMO}",
                    "make dashboard",
                    'make UV="uv" demo-local',
                ]
            ),
            language="bash",
        )


def _render_quick_links(settings: DashboardSettings) -> None:
    with st.expander("Quick links & evidence", expanded=False):
        api_base = settings.api_base_url
        repo = settings.github_repo_url
        guide = settings.github_blob_url(settings.reviewer_guide_path)
        evidence = settings.github_blob_url(settings.evidence_doc_path)
        scenario = settings.github_blob_url("examples/demo-scenario/scenario.yaml")
        sample_api = settings.github_blob_url("examples/api/forecast_request.json")

        if api_base:
            c1, c2 = st.columns(2)
            with c1:
                st.link_button(
                    "Live API docs", f"{api_base}/docs", use_container_width=True
                )
            with c2:
                st.link_button(
                    "API health JSON", f"{api_base}/health", use_container_width=True
                )

        c3, c4 = st.columns(2)
        with c3:
            st.link_button("GitHub repo", repo, use_container_width=True)
        with c4:
            st.link_button("Reviewer guide", guide, use_container_width=True)

        c5, c6 = st.columns(2)
        with c5:
            st.link_button("Technical evidence", evidence, use_container_width=True)
        with c6:
            st.link_button("Sample scenario YAML", scenario, use_container_width=True)


def _render_system_flow(settings: DashboardSettings) -> None:
    with st.expander("System flow · cloud vs local", expanded=False):
        left, right = st.columns(2)
        with left:
            st.markdown("**Cloud (live read-only demo)**")
            st.markdown(
                "- Streamlit dashboard *(this page in cloud mode)*\n"
                "- FastAPI AI Ops API *(read-only endpoints)*\n"
                "- Mutations blocked · no public MLflow/ZenML/InvenTree"
            )
        with right:
            st.markdown("**Local only (full pipeline)**")
            st.markdown(
                "- Synthetic data → ML training → decision intel → MLOps loop\n"
                "- Dashboard reads generated artifacts\n"
                "- Optional: InvenTree, Prometheus/Grafana, kind/k8s"
            )
        if settings.is_cloud_mode:
            st.caption(
                f"Full pipeline locally: `{CMD_REVIEWER_DEMO}` then `make dashboard`."
            )
        else:
            st.caption(f"Populate artifacts: `{CMD_DEMO_LOCAL}`.")


def _render_observability_summary(settings: DashboardSettings) -> None:
    st.header("5. Observability & API health")
    if not settings.api_base_url:
        st.info(
            "Set `INVFORGE_API_BASE_URL` to show live API health (cloud dashboard)."
        )
        return

    health = _fetch_api_health(settings.api_base_url)
    if health is None:
        st.warning(f"Could not reach `{settings.api_base_url}/health`.")
        return

    st.success("API health endpoint reachable.")
    with st.expander("API health JSON"):
        st.json(health)
    base = settings.api_base_url
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("Open /metrics", f"{base}/metrics", use_container_width=True)
    with c2:
        st.link_button("Open /docs", f"{base}/docs", use_container_width=True)


def _render_security_posture(settings: DashboardSettings) -> None:
    st.header("6. Security & read-only posture")
    if settings.is_cloud_mode:
        mode = "Cloud fixture-backed demo"
        data_source = "Bundled fixtures (cloud)"
    else:
        mode = "Local full artifacts"
        data_source = "Generated local artifacts"
    rows = [
        ("Dashboard mode", mode),
        ("Data source", data_source),
        ("Demo auth gate", "Enabled" if settings.demo_auth_enabled else "Disabled"),
        ("Mutation endpoints", "Blocked in cloud/demo API mode"),
        ("InvenTree admin", "Local only — not exposed publicly"),
        ("MLflow / ZenML", "Local only — not exposed publicly"),
        ("Data classification", "Synthetic seed-42 fixtures only"),
    ]
    st.table({"Control": [r[0] for r in rows], "Status": [r[1] for r in rows]})


def _flow_status_badge(status: str) -> str:
    icons = {
        "ok": "🟢",
        "missing": "🟠",
        "optional": "🔵",
        "companion": "⚪",
    }
    return icons.get(status, "⚪")


def _render_pipeline_chain(
    *,
    settings: DashboardSettings,
    synthetic: LoaderResult,
    comparison: LoaderResult,
    decision_summary: LoaderResult,
    mlops_summary: LoaderResult,
) -> None:
    with st.expander("How InvForge works · pipeline chain", expanded=False):
        st.markdown(
            "This dashboard is **read-only proof** that backend pipelines already ran. "
            f"`{CMD_DEMO_LOCAL}` executes the chain below. **This UI never triggers "
            "pipelines.**"
        )

        steps = derive_system_flow_steps(
            synthetic=synthetic,
            comparison=comparison,
            decision_summary=decision_summary,
            mlops_summary=mlops_summary,
        )

        for step in steps:
            if step["kind"] != "pipeline":
                continue
            col_a, col_b = st.columns([1, 4])
            with col_a:
                st.metric(
                    f"Step {step['step']}",
                    f"{_flow_status_badge(step['status'])} {step['status'].upper()}",
                )
            with col_b:
                st.markdown(f"**{step['title']}** — `{step['command']}`")
                st.caption(step["detail"])
                if not settings.is_cloud_mode:
                    st.code(step["artifact_path"], language=None)

        st.markdown("**Companion surfaces (run separately)**")
        for step in steps:
            if step["kind"] != "companion":
                continue
            st.markdown(
                f"- {_flow_status_badge(step['status'])} **{step['title']}** — "
                f"`{step['command']}` · _{step['detail']}_"
            )


def _render_mlops_detail(
    *,
    settings: DashboardSettings,
    mlops_summary: LoaderResult,
    registry: LoaderResult,
    bentoml_summary: LoaderResult,
    evidently: LoaderResult,
) -> None:
    _section_anchor("mlops-status")
    st.header("4. MLOps Status")
    if mlops_summary["status"] != "ok":
        _render_missing(mlops_summary, settings=settings)
        return

    _render_freshness(mlops_summary)
    loop = mlops_summary["data"]
    steps = loop.get("steps") or {}
    ev_step = steps.get("evidently") or {}
    reg_step = steps.get("registry") or {}
    cc_step = steps.get("champion_challenger") or {}
    bento_step = steps.get("bentoml") or {}
    drift_flag = ev_step.get("dataset_drift_detected")

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        if drift_flag is None:
            st.metric("Drift detected", "Unknown")
        else:
            st.metric("Drift detected", "Yes" if drift_flag else "No")
    with m2:
        evidently_label = "present"
        if evidently["status"] == "ok":
            ev_data = evidently["data"]
            if not (ev_data["drift_report"] or ev_data["quality_report"]):
                evidently_label = "not bundled"
        elif settings.is_cloud_mode:
            evidently_label = "not bundled"
        else:
            evidently_label = "missing"
        st.metric("Evidently reports", evidently_label)
    with m3:
        st.metric(
            "Registry strategy",
            reg_step.get("registry_strategy", "n/a"),
        )
    with m4:
        st.metric(
            "Champion/challenger",
            cc_step.get("decision", "n/a"),
        )

    bento_loop_status = bento_step.get("status", "n/a")
    bento_detail_status = bento_loop_status
    if bentoml_summary["status"] == "ok":
        bento_detail_status = bentoml_summary["data"].get("status", bento_loop_status)

    st.metric("BentoML packaging", bento_detail_status)

    if settings.is_cloud_mode:
        st.caption(
            "Cloud fixture mode: MLOps cards reflect committed synthetic artifacts. "
            "Local runs write full reports under `artifacts/mlops/`."
        )

    detail_cols = st.columns(2)
    with detail_cols[0]:
        if evidently["status"] == "ok":
            ev_data = evidently["data"]
            drift_ok = ev_data["drift_report"]
            quality_ok = ev_data["quality_report"]
            st.markdown(
                f"**Evidently:** drift report "
                f"{'present' if drift_ok else 'not bundled'} · quality report "
                f"{'present' if quality_ok else 'not bundled'}"
            )
        elif settings.is_cloud_mode:
            st.info("Evidently reports: not bundled in cloud fixture.")
        else:
            _render_missing(evidently, settings=settings)

    with detail_cols[1]:
        if registry["status"] == "ok":
            reg = registry["data"]
            champion = reg.get("champion") or {}
            st.markdown(
                f"**Registry:** model `{reg.get('model_name')}` · version "
                f"`{champion.get('version', 'n/a')}` · alias "
                f"`{champion.get('alias', reg.get('champion_alias', 'n/a'))}`"
            )
        elif settings.is_cloud_mode:
            st.info("Registry summary: not bundled in cloud fixture.")
        else:
            _render_missing(registry, settings=settings)

    if bentoml_summary["status"] == "ok":
        bento = bentoml_summary["data"]
        note = bento.get("note") or bento.get("reason") or ""
        st.markdown(f"**BentoML detail:** status `{bento.get('status')}`")
        if note:
            st.caption(str(note))
    elif bento_loop_status not in ("n/a", None):
        st.markdown(f"**BentoML detail:** loop reports `{bento_loop_status}`")
        if settings.is_cloud_mode:
            st.caption(
                "Build summary JSON not bundled; loop summary still reflects packaging."
            )
        else:
            _render_missing(bentoml_summary, settings=settings)

    with st.expander("Raw MLOps loop summary JSON"):
        st.json(loop)


def main() -> None:
    settings = DashboardSettings.from_env()

    if not render_login_gate(settings):
        return

    st.title("InvForge — AI Operations Control Tower")
    st.caption(settings.mode_label)

    st.warning(f"⚠️ **{settings.read_only_banner}**")

    _render_mission_control(settings)
    _render_guided_scenarios(settings)
    _render_sample_inputs(settings)
    _render_quick_links(settings)

    synthetic = load_synthetic_data_status()
    comparison = load_champion_challenger_comparison()
    decision_summary = load_decision_summary()
    decision_recs = load_decision_recommendations()
    mlops_summary = load_mlops_loop_summary()
    registry = load_registry_summary()
    bentoml_summary = load_bentoml_build_summary()
    evidently = load_evidently_artifact_status()

    overview = derive_overview_status(
        synthetic=synthetic,
        comparison=comparison,
        decision_summary=decision_summary,
        mlops_summary=mlops_summary,
    )

    # --- Overview ---
    _section_anchor("overview")
    st.header("1. Overview")
    if settings.is_cloud_mode:
        r1a, r1b = st.columns(2)
        r2a, r2b = st.columns(2)
        cols = (r1a, r1b, r2a, r2b)
    else:
        cols = st.columns(4)
    labels = ("Data", "ML forecast", "Decision intel", "MLOps")
    keys = ("data", "ml_forecast", "decision", "mlops")
    for col, label, key in zip(cols, labels, keys, strict=True):
        with col:
            _status_badge(label, overview[key])

    if synthetic["status"] == "ok":
        syn = synthetic["data"]
        if settings.is_cloud_mode:
            st.success(
                f"Synthetic fixture data ready ({len(syn['files_present'])} CSV markers)."
            )
        else:
            st.info(
                f"Synthetic data directory: `{syn['synthetic_dir']}`. "
                f"Markers present: {', '.join(syn['files_present'])}."
            )
            if syn["files_missing"]:
                st.warning(
                    f"Missing markers: {', '.join(syn['files_missing'])}. "
                    f"Run `{CMD_GENERATE_DATA}` (local) or use bundled cloud fixtures."
                )
    else:
        _render_missing(synthetic, settings=settings)

    # --- Forecast Performance ---
    _section_anchor("forecast-performance")
    st.header("2. Forecast Performance")
    if comparison["status"] == "ok":
        _render_freshness(comparison)
        payload = comparison["data"]
        primary = payload.get("primary_metric", "mae")
        decision = payload.get("decision", "unknown")
        st.success(f"Champion/challenger decision: **{decision}**")
        st.write(payload.get("reason", ""))

        champ = payload.get("champion", {})
        chal = payload.get("challenger", {})
        champ_metrics = champ.get("metrics") or {}
        chal_metrics = chal.get("metrics") or {}

        fig = _metric_bar_chart(
            str(champ.get("name", "champion")),
            str(chal.get("name", "challenger")),
            champ_metrics,
            chal_metrics,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

        comp = payload.get("comparison") or {}
        st.markdown(
            f"**Primary metric ({primary}):** champion "
            f"`{comp.get('primary_metric_champion')}` · challenger "
            f"`{comp.get('primary_metric_challenger')}` · relative improvement "
            f"`{comp.get('relative_improvement_pct')}`%"
        )

        pr04_ctx = (payload.get("supporting_context") or {}).get(
            "pr04_cost_metrics"
        )
        if pr04_ctx and pr04_ctx.get("available"):
            st.caption(
                "PR-04 cost context (synthetic/simulated): "
                f"pinball loss `{pr04_ctx.get('selected_pinball_loss')}`, "
                f"cost reduction vs best baseline "
                f"`{pr04_ctx.get('cost_reduction_vs_best_baseline_pct')}`% — "
                "**not real-world savings**."
            )

        with st.expander("Model metrics detail"):
            col_a, col_b = st.columns(2)
            with col_a:
                st.subheader(f"Champion ({champ.get('name', 'champion')})")
                st.json(champ_metrics)
            with col_b:
                st.subheader(f"Challenger ({chal.get('name', 'challenger')})")
                st.json(chal_metrics)

        with st.expander("Raw champion/challenger JSON"):
            st.json(payload)
    else:
        _render_missing(comparison, settings=settings)

    # --- Decision Intelligence ---
    _section_anchor("decision-intelligence")
    st.header("3. Decision Intelligence")
    if decision_summary["status"] == "ok":
        _render_freshness(decision_summary)
        summary = decision_summary["data"]
        st.caption(
            f"Test period: {summary.get('test_period', 'n/a')} · "
            f"Rows: {summary.get('recommendation_rows', 'n/a')} · "
            f"Service level: {summary.get('service_level', 'n/a')}"
        )

        assumptions = summary.get("assumptions") or {}
        st.info(
            "**Simulated cost assumptions (synthetic):** "
            f"order cost USD `{assumptions.get('order_cost_usd')}`, "
            f"holding `{assumptions.get('annual_holding_cost_per_unit')}`, "
            f"understock `{assumptions.get('understock_cost_per_unit')}`, "
            f"overstock `{assumptions.get('overstock_cost_per_unit')}`."
        )

        cost = summary.get("cost_metrics") or {}
        if cost:
            st.markdown(
                f"Simulated optimized cost: `{cost.get('optimized_total_cost')}` · "
                f"vs best baseline reduction: "
                f"`{cost.get('cost_reduction_vs_best_baseline_pct')}`% "
                "(synthetic backtest only)."
            )
            for warning in cost.get("warnings", []):
                st.warning(warning)

        if decision_recs["status"] == "ok":
            _render_freshness(decision_recs)
            frame: pd.DataFrame = decision_recs["data"]
            display_cols = [
                c
                for c in [
                    "part_id",
                    "demand_pattern",
                    "current_stock",
                    "prediction",
                    "safety_stock",
                    "reorder_point",
                    "eoq",
                    "stockout_risk",
                    "risk_level",
                ]
                if c in frame.columns
            ]
            top_n = min(15, len(frame))
            risk_order = {"high": 0, "medium": 1, "low": 2}
            if "risk_level" in frame.columns and "stockout_risk" in frame.columns:
                ranked = frame.assign(
                    _risk_rank=frame["risk_level"].map(risk_order).fillna(9)
                ).sort_values(
                    ["_risk_rank", "stockout_risk"],
                    ascending=[True, False],
                )
                st.subheader(f"Top {top_n} reorder recommendations (by risk)")
                st.dataframe(
                    ranked[display_cols].head(top_n),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.dataframe(
                    frame[display_cols].head(top_n),
                    use_container_width=True,
                    hide_index=True,
                )
        elif decision_recs["status"] == "missing":
            _render_missing(decision_recs, settings=settings)

        with st.expander("Raw decision summary JSON"):
            st.json(summary)
    else:
        _render_missing(decision_summary, settings=settings)

    _render_mlops_detail(
        settings=settings,
        mlops_summary=mlops_summary,
        registry=registry,
        bentoml_summary=bentoml_summary,
        evidently=evidently,
    )

    with st.expander("Scope & limitations", expanded=False):
        items = LIMITATIONS_CLOUD if settings.is_cloud_mode else LIMITATIONS_LOCAL
        for item in items:
            st.markdown(f"- {item}")

    _render_system_flow(settings)
    with st.container(border=True):
        _render_pipeline_chain(
            settings=settings,
            synthetic=synthetic,
            comparison=comparison,
            decision_summary=decision_summary,
            mlops_summary=mlops_summary,
        )

    _render_observability_summary(settings)
    _render_security_posture(settings)

    st.markdown("---")
    st.caption(
        "Local artifact chain: "
        f"`{CMD_GENERATE_DATA}` → `{CMD_TRAIN_ML}` → "
        f"`{CMD_DECISION_INTEL}` → `{CMD_MLOPS_LOOP}` · "
        f"One-command reviewer path: `{CMD_REVIEWER_DEMO}` · "
        'Launch dashboard: `make UV="uv" dashboard`'
    )


if __name__ == "__main__":
    main()
