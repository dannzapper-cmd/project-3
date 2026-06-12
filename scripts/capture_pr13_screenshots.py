#!/usr/bin/env python3
"""Capture PR-13 portfolio screenshots from locally running InvForge services.

Dev-only utility — Playwright is NOT a project runtime dependency.
Install locally if needed:
  python -m pip install playwright
  python -m playwright install chromium

Does NOT require cloud credentials or create cloud resources.
"""
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "docs" / "assets" / "screenshots"
MANIFEST = OUT_DIR / "SCREENSHOT_MANIFEST.md"

Status = Literal["PASS", "FAIL", "MANUAL REQUIRED", "SKIP"]


@dataclass
class ShotResult:
    name: str
    file: str
    status: Status
    url: str = ""
    notes: str = ""


@dataclass
class Runner:
    results: list[ShotResult] = field(default_factory=list)
    procs: list[subprocess.Popen] = field(default_factory=list)

    def log(self, msg: str) -> None:
        print(msg, flush=True)

    def wait_url(self, url: str, timeout: float = 90.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=3) as resp:
                    if resp.status < 500:
                        return True
            except (urllib.error.URLError, TimeoutError, ConnectionError):
                pass
            time.sleep(1.0)
        return False

    def start(self, cmd: list[str], env: dict | None = None) -> subprocess.Popen:
        merged = os.environ.copy()
        if env:
            merged.update(env)
        proc = subprocess.Popen(
            cmd,
            cwd=REPO_ROOT,
            env=merged,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.procs.append(proc)
        return proc

    def stop_all(self) -> None:
        for proc in self.procs:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        for proc in self.procs:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        self.procs.clear()

    def run_make(self, target: str) -> bool:
        self.log(f"Running make {target} ...")
        r = subprocess.run(
            ["make", target],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            self.log(f"  FAIL: make {target}\n{r.stderr[-500:]}")
            return False
        return True

    def capture_playwright(self, shots: list[tuple[str, str, str | None]]) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            for name, _, url in shots:
                self.results.append(
                    ShotResult(name, f"{name}.png", "MANUAL REQUIRED", url or "", "playwright not installed")
                )
            return

        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            for name, url, selector in shots:
                path = OUT_DIR / f"{name}.png"
                try:
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.goto(url, wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(2000)
                    if selector:
                        el = page.locator(selector).first
                        if el.count():
                            el.scroll_into_view_if_needed()
                            page.wait_for_timeout(500)
                    page.screenshot(path=str(path), full_page=True)
                    self.results.append(ShotResult(name, path.name, "PASS", url))
                    self.log(f"  PASS: {path.name}")
                    page.close()
                except Exception as exc:  # noqa: BLE001
                    self.results.append(
                        ShotResult(name, f"{name}.png", "FAIL", url, str(exc)[:200])
                    )
                    self.log(f"  FAIL: {name} — {exc}")
            browser.close()

    def capture_curl_json(self, name: str, url: str) -> None:
        """Render JSON health response as minimal HTML for screenshot."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.results.append(
                ShotResult(name, f"{name}.png", "MANUAL REQUIRED", url, "playwright not installed")
            )
            return
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                body = resp.read().decode()
            data = json.loads(body)
            pretty = json.dumps(data, indent=2)
            html = f"""<!DOCTYPE html><html><head><meta charset=utf-8>
<title>{name}</title>
<style>body{{font-family:monospace;background:#1e1e1e;color:#d4d4d4;padding:2rem}}
pre{{white-space:pre-wrap;font-size:13px}}</style></head>
<body><h2>{url}</h2><pre>{pretty}</pre></body></html>"""
            tmp = OUT_DIR / f"_{name}.html"
            tmp.write_text(html, encoding="utf-8")
            OUT_DIR.mkdir(parents=True, exist_ok=True)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page(viewport={"width": 1200, "height": 800})
                page.goto(tmp.as_uri(), wait_until="load")
                page.screenshot(path=str(OUT_DIR / f"{name}.png"), full_page=True)
                browser.close()
            tmp.unlink(missing_ok=True)
            self.results.append(ShotResult(name, f"{name}.png", "PASS", url))
            self.log(f"  PASS: {name}.png")
        except Exception as exc:  # noqa: BLE001
            self.results.append(ShotResult(name, f"{name}.png", "FAIL", url, str(exc)[:200]))

    def write_manifest(self) -> None:
        lines = [
            "# Screenshot manifest (PR-13)",
            "",
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}",
            f"Repo: `{REPO_ROOT}`",
            "",
            "| File | Status | URL | Notes |",
            "|------|--------|-----|-------|",
        ]
        for r in self.results:
            lines.append(f"| `{r.file}` | **{r.status}** | {r.url or '—'} | {r.notes or '—'} |")
        lines.extend(["", "Regenerate: `bash scripts/capture_pr13_screenshots.sh`", ""])
        MANIFEST.write_text("\n".join(lines), encoding="utf-8")
        self.log(f"Manifest: {MANIFEST}")


def main() -> int:
    runner = Runner()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    uv = shutil.which("uv") or "uv"

    runner.log("=== PR-13 screenshot capture ===")

    if not runner.run_make("demo-local"):
        runner.log("demo-local failed — aborting")
        return 1

    api_port = os.environ.get("INVFORGE_API_PORT", "8001")
    dash_port = os.environ.get("STREAMLIT_PORT", "8501")
    api_base = f"http://127.0.0.1:{api_port}"
    dash_base = f"http://127.0.0.1:{dash_port}"

    runner.start(
        [uv, "run", "--group", "dashboard", "streamlit", "run", "dashboard/app.py",
         "--server.headless", "true", "--server.port", dash_port],
    )
    runner.start(
        [uv, "run", "--group", "observability", "uvicorn", "api.main:app",
         "--host", "127.0.0.1", "--port", api_port],
    )

    runner.log("Waiting for dashboard and API ...")
    dash_ok = runner.wait_url(dash_base, timeout=120)
    api_ok = runner.wait_url(f"{api_base}/health", timeout=120)

    if not dash_ok:
        runner.results.append(
            ShotResult("dashboard-overview", "dashboard-overview.png", "FAIL", dash_base, "dashboard did not start")
        )
    if not api_ok:
        runner.results.append(
            ShotResult("api-health", "api-health.png", "FAIL", f"{api_base}/health", "API did not start")
        )

    if dash_ok:
        runner.capture_playwright([
            ("dashboard-overview", dash_base, "text=1. Overview"),
            ("dashboard-decision-intelligence", dash_base, "text=3. Decision Intelligence"),
            ("dashboard-mlops", dash_base, "text=4. MLOps Status"),
        ])

    if api_ok:
        runner.capture_curl_json("api-health", f"{api_base}/health")
        runner.capture_playwright([
            ("api-docs", f"{api_base}/docs", None),
        ])

    runner.stop_all()

    # Docker Grafana (optional)
    runner.log("Attempting Docker observability stack for Grafana ...")
    if runner.run_make("observability-up"):
        grafana_url = "http://127.0.0.1:3000/login"
        if runner.wait_url("http://127.0.0.1:3000", timeout=60):
            try:
                from playwright.sync_api import sync_playwright
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page(viewport={"width": 1440, "height": 900})
                    page.goto(grafana_url, wait_until="networkidle", timeout=60000)
                    page.fill('input[name="user"]', "admin")
                    page.fill('input[name="password"]', "admin")
                    page.click('button[type="submit"]')
                    page.wait_for_timeout(3000)
                    page.goto("http://127.0.0.1:3000/dashboards", wait_until="networkidle", timeout=60000)
                    page.wait_for_timeout(2000)
                    path = OUT_DIR / "grafana-observability.png"
                    page.screenshot(path=str(path), full_page=True)
                    runner.results.append(
                        ShotResult("grafana-observability", path.name, "PASS", "http://127.0.0.1:3000")
                    )
                    browser.close()
                    runner.log("  PASS: grafana-observability.png")
            except Exception as exc:  # noqa: BLE001
                runner.results.append(
                    ShotResult("grafana-observability", "grafana-observability.png", "FAIL", grafana_url, str(exc)[:200])
                )
        else:
            runner.results.append(
                ShotResult("grafana-observability", "grafana-observability.png", "FAIL", grafana_url, "Grafana not reachable")
            )
        subprocess.run(["make", "observability-down"], cwd=REPO_ROOT, capture_output=True)
    else:
        runner.results.append(
            ShotResult("grafana-observability", "grafana-observability.png", "MANUAL REQUIRED", "http://localhost:3000", "make observability-up failed or Docker unavailable")
        )

    # Marquez — skip heavy kind profile unless kind available; document manual
    if shutil.which("kind") and shutil.which("kubectl") and shutil.which("helm"):
        runner.log("Marquez via kind is heavy — marking MANUAL REQUIRED (see docs/screenshots.md)")
    runner.results.append(
        ShotResult(
            "marquez-lineage",
            "marquez-lineage.png",
            "MANUAL REQUIRED",
            "http://localhost:3000 (Marquez UI via lineage-port-forward)",
            "Run: make lineage-up && make lineage-port-forward — capture invforge.retraining job",
        )
    )

    runner.results.append(
        ShotResult(
            "github-actions-green",
            "github-actions-green.png",
            "MANUAL REQUIRED",
            "https://github.com/dannzapper-cmd/project-3/actions",
            "Export after PR-13 push when CI is green",
        )
    )

    # Terminal demo-local — save text evidence
    log_path = OUT_DIR / "demo-local-pass.log"
    r = subprocess.run(
        ["make", "demo-local"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    log_path.write_text(r.stdout[-4000:] if r.stdout else r.stderr, encoding="utf-8")
    runner.results.append(
        ShotResult(
            "terminal-demo-local-pass",
            "terminal-demo-local-pass.png",
            "MANUAL REQUIRED" if r.returncode == 0 else "FAIL",
            "—",
            f"Text log saved: {log_path.name}; screenshot terminal manually if needed",
        )
    )

    runner.write_manifest()

    failed = sum(1 for x in runner.results if x.status == "FAIL")
    runner.log(f"=== Done: {len(runner.results)} entries, {failed} FAIL ===")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
