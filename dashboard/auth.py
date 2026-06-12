"""Simple reviewer gate for the cloud dashboard (not production security)."""

from __future__ import annotations

import streamlit as st

from dashboard.config import DashboardSettings

_SESSION_KEY = "invforge_demo_authenticated"


def is_authenticated(settings: DashboardSettings) -> bool:
    if not settings.demo_auth_enabled:
        return True
    return bool(st.session_state.get(_SESSION_KEY))


def render_login_gate(settings: DashboardSettings) -> bool:
    """Render login form. Returns True when the user may proceed."""

    if is_authenticated(settings):
        return True

    st.title("InvForge — Reviewer Demo")
    st.caption("AI Operations Control Tower · portfolio demo login")

    st.info(
        "This is a **reviewer gate** for a read-only synthetic portfolio demo. "
        "It is not production authentication."
    )

    if settings.show_demo_credentials_hint:
        with st.expander("Demo credentials (portfolio)", expanded=True):
            st.markdown(
                f"- **Username:** `{settings.demo_user}`\n"
                f"- **Password:** `{settings.demo_password}`\n\n"
                "These unlock **synthetic read-only** dashboard content only."
            )
            st.link_button(
                "Open reviewer guide",
                f"{settings.github_repo_url}/blob/main/{settings.reviewer_guide_path}",
                use_container_width=True,
            )

    with st.form("demo_login"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Sign in", use_container_width=True)
        if submitted:
            if (
                username == settings.demo_user
                and password == settings.demo_password
                and settings.demo_password
            ):
                st.session_state[_SESSION_KEY] = True
                st.rerun()
            else:
                st.error("Invalid demo credentials. Check username and password.")

    st.caption(
        "Desktop recommended for charts and tables. Mobile works for a first "
        "impression and login check."
    )
    return False
