"""Streamlit AI Operations Dashboard (PR-06 / PR-15).

Read-only visualization of PR-03/04/05 artifacts. Does not run pipelines.
Cloud mode uses bundled demo fixtures and an optional reviewer login gate.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from dashboard.auth import render_login_gate
from dashboard.config import DashboardSettings
from dashboard.loaders import (
    derive_overview_status,
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
from dashboard.types import LoaderMissing, LoaderOk

st.set_page_config(
    page_title="InvForge AI Operations",
    page_icon="📊",
    layout="wide",
)

LIMITATIONS_LOCAL = [
    "All inputs are **synthetic** (seed 42); no real InvenTree inventory data.",
    "Cost and policy figures are **simulated backtest diagnostics**, not "
    "real-world savings claims.",
    "MLflow, Evidently, and BentoML artifacts are **local** to this machine.",
    "This dashboard is **not** production monitoring, alerting, or serving.",
    "Grafana and Prometheus are available locally via `make observability-*`.",
    "Cloud deploy exposes a **read-only API + dashboard**; training stays local.",
]

LIMITATIONS_CLOUD = [
    "All data is **synthetic** (seed 42) from committed demo fixtures.",
    "Cost metrics are **simulated backtest diagnostics** — not real savings.",
    "This is a **read-only portfolio demo**; no mutations or admin actions.",
    "MLflow, ZenML, InvenTree, and retraining remain **local-only**.",
    "Demo login is a **reviewer gate**, not production authentication.",
]


def _render_missing(result: LoaderMissing) -> None:
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


def _render_system_flow(settings: DashboardSettings) -> None:
    st.header("System flow")
    st.markdown(
        """
```mermaid
flowchart LR
    subgraph cloud ["Cloud (read-only demo)"]
        DASH["Streamlit Dashboard"]
        API["FastAPI AI Ops API"]
    end
    subgraph local ["Local only"]
        INV["InvenTree"]
        ML["ML / MLOps pipeline"]
        OBS["Prometheus / Grafana"]
    end
    DASH -->|"status links"| API
    API -.->|"ingestion blocked in cloud"| INV
    ML -->|"artifacts"| DASH
```
"""
    )
    if settings.is_cloud_mode:
        st.caption(
            "You are viewing the **cloud read-only dashboard**. The full pipeline "
            f"runs locally via `{CMD_REVIEWER_DEMO}`."
        )
    else:
        st.caption(
            "Local mode reads artifacts from your workspace. Run "
            f"`{CMD_DEMO_LOCAL}` to populate them."
        )


def _render_reviewer_links(settings: DashboardSettings) -> None:
    st.header("Reviewer resources")
    api_url = settings.api_base_url or "<set INVFORGE_API_BASE_URL>"
    api_docs = (
        f"{settings.api_base_url}/docs" if settings.api_base_url else api_url
    )
    guide = (
        f"{settings.github_repo_url}/blob/main/{settings.reviewer_guide_path}"
    )
    repo = settings.github_repo_url
    scenario = f"{repo}/blob/main/examples/demo-scenario/scenario.yaml"
    sample_api = f"{repo}/blob/main/examples/api/forecast_request.json"

    st.markdown(
        f"""
| Resource | Link |
|----------|------|
| Live API docs | [{api_docs}]({api_docs}) |
| GitHub README | [{repo}]({repo}) |
| Reviewer demo guide | [{guide}]({guide}) |
| Local demo command | `{CMD_REVIEWER_DEMO}` |
| Sample scenario | [`examples/demo-scenario/scenario.yaml`]({scenario}) |
| Sample API JSON | [`examples/api/forecast_request.json`]({sample_api}) |
"""
    )


def _render_observability_summary(settings: DashboardSettings) -> None:
    st.header("Observability & API health")
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
    st.json(health)
    base = settings.api_base_url
    st.markdown(
        f"- Metrics: [`{base}/metrics`]({base}/metrics)\n"
        f"- OpenAPI: [`{base}/docs`]({base}/docs)"
    )


def _render_security_posture(settings: DashboardSettings) -> None:
    st.header("Security & read-only posture")
    mode = "Cloud read-only demo" if settings.is_cloud_mode else "Local"
    rows = [
        ("Dashboard mode", mode),
        ("Demo auth gate", "Enabled" if settings.demo_auth_enabled else "Disabled"),
        ("Mutation endpoints", "Blocked in cloud/demo API mode"),
        ("InvenTree admin", "Local only — not exposed publicly"),
        ("MLflow / ZenML", "Local only — not exposed publicly"),
        ("Data classification", "Synthetic seed-42 fixtures only"),
    ]
    st.table({"Control": [r[0] for r in rows], "Status": [r[1] for r in rows]})


def main() -> None:
    settings = DashboardSettings.from_env()

    if not render_login_gate(settings):
        return

    st.title("InvForge — AI Operations Control Tower")

    st.warning(f"⚠️ **{settings.read_only_banner}**")

    st.markdown(
        "Streamlit dashboard for synthetic demand forecasting, decision "
        "intelligence, and MLOps loop artifacts. **Read-only** — pipelines are "
        "never triggered from this UI."
    )

    if settings.is_cloud_mode:
        for item in LIMITATIONS_CLOUD:
            st.markdown(f"- {item}")
    else:
        for item in LIMITATIONS_LOCAL:
            st.markdown(f"- {item}")

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

    _render_system_flow(settings)

    # --- Overview ---
    st.header("1. Overview")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        _status_badge("Data", overview["data"])
    with c2:
        _status_badge("ML forecast", overview["ml_forecast"])
    with c3:
        _status_badge("Decision intel", overview["decision"])
    with c4:
        _status_badge("MLOps", overview["mlops"])

    if synthetic["status"] == "ok":
        syn = synthetic["data"]
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
        _render_missing(synthetic)

    # --- Forecast Performance ---
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

        col_a, col_b = st.columns(2)
        with col_a:
            st.subheader(f"Champion ({champ.get('name', 'champion')})")
            st.json(champ_metrics)
        with col_b:
            st.subheader(f"Challenger ({chal.get('name', 'challenger')})")
            st.json(chal_metrics)

        fig = _metric_bar_chart(
            str(champ.get("name", "champion")),
            str(chal.get("name", "challenger")),
            champ_metrics,
            chal_metrics,
        )
        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning(
                f"No paired numeric metrics for charting (primary: {primary})."
            )

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

        with st.expander("Raw champion/challenger JSON"):
            st.json(payload)
    else:
        _render_missing(comparison)

    # --- Decision Intelligence ---
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
            _render_missing(decision_recs)

        with st.expander("Raw decision summary JSON"):
            st.json(summary)
    else:
        _render_missing(decision_summary)

    # --- MLOps Status ---
    st.header("4. MLOps Status")
    if mlops_summary["status"] == "ok":
        _render_freshness(mlops_summary)
        loop = mlops_summary["data"]
        steps = loop.get("steps") or {}
        ev_step = steps.get("evidently") or {}
        reg_step = steps.get("registry") or {}
        cc_step = steps.get("champion_challenger") or {}
        bento_step = steps.get("bentoml") or {}

        m1, m2, m3, m4 = st.columns(4)
        drift_flag = ev_step.get("dataset_drift_detected")
        with m1:
            if drift_flag is None:
                st.metric("Drift detected", "Unknown")
            else:
                st.metric("Drift detected", "Yes" if drift_flag else "No")
        with m2:
            st.metric(
                "Registry strategy",
                reg_step.get("registry_strategy", "n/a"),
            )
        with m3:
            st.metric(
                "Champion/challenger",
                cc_step.get("decision", "n/a"),
            )
        with m4:
            st.metric("BentoML packaging", bento_step.get("status", "n/a"))

        if evidently["status"] == "ok":
            _render_freshness(evidently)
            ev_data = evidently["data"]
            st.write(
                f"Evidently reports — drift JSON: "
                f"`{'present' if ev_data['drift_report'] else 'missing'}` · "
                f"quality JSON: "
                f"`{'present' if ev_data['quality_report'] else 'missing'}`"
            )
        elif evidently["status"] == "missing":
            _render_missing(evidently)

        if registry["status"] == "ok":
            _render_freshness(registry)
            reg = registry["data"]
            champion = reg.get("champion") or {}
            st.write(
                f"Model `{reg.get('model_name')}` · registered: "
                f"`{champion.get('registered')}` · version: "
                f"`{champion.get('version', 'n/a')}` · alias: "
                f"`{champion.get('alias', reg.get('champion_alias', 'n/a'))}`"
            )
            with st.expander("Raw registry summary JSON"):
                st.json(reg)
        elif registry["status"] == "missing":
            _render_missing(registry)

        if bentoml_summary["status"] == "ok":
            _render_freshness(bentoml_summary)
            bento = bentoml_summary["data"]
            st.write(
                f"BentoML status: `{bento.get('status')}`"
                + (
                    f" (deferred to {bento.get('deferred_to')})"
                    if bento.get("deferred_to")
                    else ""
                )
            )
            if bento.get("reason"):
                st.caption(str(bento["reason"]))
        elif bentoml_summary["status"] == "missing":
            _render_missing(bentoml_summary)

        with st.expander("Raw MLOps loop summary JSON"):
            st.json(loop)
    else:
        _render_missing(mlops_summary)

    _render_observability_summary(settings)
    _render_security_posture(settings)
    _render_reviewer_links(settings)

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
