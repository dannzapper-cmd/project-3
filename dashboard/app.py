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


def _render_how_to_use(settings: DashboardSettings) -> None:
    st.subheader("How to use this demo")
    if settings.is_cloud_mode:
        st.markdown(
            "1. Scan **Overview** status cards and sections 1–4 below.\n"
            "2. Open **Quick links** for the live API docs and local full demo guide.\n"
            "3. Compare **Cloud vs local** — this page uses bundled fixtures; "
            f"run `{CMD_REVIEWER_DEMO}` locally for the full pipeline."
        )
    else:
        st.markdown(
            f"1. If cards show **missing**, run `{CMD_REVIEWER_DEMO}` first.\n"
            "2. Explore forecast, decision intelligence, and MLOps sections.\n"
            "3. Optionally start `make observability-api` for `/health` and `/docs`."
        )


def _render_backend_explainer(settings: DashboardSettings) -> None:
    st.subheader("Cloud vs local backend")
    if settings.is_cloud_mode:
        st.success(
            "**Cloud demo (this page):** live read-only Streamlit surface with "
            "**bundled synthetic fixtures** (~116 KB, seed 42). No ML training, "
            "no live MLflow/ZenML/InvenTree on cold start."
        )
        st.info(
            "**Local full demo:** run the complete synthetic pipeline "
            f"(`{CMD_REVIEWER_DEMO}`) — data generation, ML training, decision "
            "intelligence, MLOps loop — then `make dashboard` reads generated "
            "artifacts from your machine."
        )
    else:
        st.success(
            "**Local mode (this page):** reading **generated workspace artifacts** "
            "from your machine after the synthetic pipeline."
        )
        st.info(
            "**Cloud demo:** live fixture-backed dashboard at the portfolio URL — "
            "safe reviewer surface without running training in Cloud Run."
        )


def _render_quick_links(settings: DashboardSettings) -> None:
    st.subheader("Quick links")
    api_base = settings.api_base_url
    repo = settings.github_repo_url
    guide = settings.github_blob_url(settings.reviewer_guide_path)
    evidence = settings.github_blob_url(settings.evidence_doc_path)
    scenario = settings.github_blob_url("examples/demo-scenario/scenario.yaml")
    sample_api = settings.github_blob_url("examples/api/forecast_request.json")
    pr_url = f"{repo}/pull/21"

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
        st.link_button("PR #21 (this release)", pr_url, use_container_width=True)

    c5, c6 = st.columns(2)
    with c5:
        st.link_button("Reviewer guide", guide, use_container_width=True)
    with c6:
        st.link_button("Technical evidence", evidence, use_container_width=True)

    c7, c8 = st.columns(2)
    with c7:
        st.link_button("Sample scenario YAML", scenario, use_container_width=True)
    with c8:
        st.link_button("Sample API JSON", sample_api, use_container_width=True)


def _render_system_flow(settings: DashboardSettings) -> None:
    st.subheader("System flow")
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
    synthetic: LoaderResult,
    comparison: LoaderResult,
    decision_summary: LoaderResult,
    mlops_summary: LoaderResult,
) -> None:
    st.header("0. How InvForge Works")
    st.markdown(
        "This dashboard is **read-only proof** that backend pipelines already ran. "
        f"`{CMD_DEMO_LOCAL}` executes the chain below (data → validate → train → "
        "decision → MLOps → dashboard smoke). **This UI never triggers pipelines.**"
    )

    steps = derive_system_flow_steps(
        synthetic=synthetic,
        comparison=comparison,
        decision_summary=decision_summary,
        mlops_summary=mlops_summary,
    )

    st.subheader("Pipeline chain (from `make demo-local`)")
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
            st.code(step["artifact_path"], language=None)

    st.subheader("Companion surfaces (run separately)")
    for step in steps:
        if step["kind"] != "companion":
            continue
        st.markdown(
            f"- {_flow_status_badge(step['status'])} **{step['title']}** — "
            f"`{step['command']}` · `{step['artifact_path']}` · _{step['detail']}_"
        )

    st.info(
        "**Honest scope:** synthetic data by default · cloud demo uses fixture-backed "
        "read-only surfaces · full pipeline runs locally · simulated cost metrics "
        "are **not production ROI**."
    )


def main() -> None:
    settings = DashboardSettings.from_env()

    if not render_login_gate(settings):
        return

    st.title("InvForge — AI Operations Control Tower")
    st.caption(settings.mode_label)

    st.warning(f"⚠️ **{settings.read_only_banner}**")

    _render_how_to_use(settings)
    _render_quick_links(settings)
    _render_backend_explainer(settings)

    st.markdown(
        "Read-only Streamlit viewer for synthetic demand forecasting, decision "
        "intelligence, and MLOps artifacts. **No pipelines run from this UI.**"
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
    with st.container(border=True):
        _render_pipeline_chain(
            synthetic=synthetic,
            comparison=comparison,
            decision_summary=decision_summary,
            mlops_summary=mlops_summary,
        )

    # --- Overview ---
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
        drift_flag = ev_step.get("dataset_drift_detected")

        m1, m2 = st.columns(2)
        m3, m4 = st.columns(2)
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
