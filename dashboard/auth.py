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
    st.info(
        "This is a **reviewer gate** for a read-only synthetic portfolio demo. "
        "It is not production authentication."
    )
    with st.form("demo_login"):
        username = st.text_input("Username", autocomplete="username")
        password = st.text_input(
            "Password", type="password", autocomplete="current-password"
        )
        submitted = st.form_submit_button("Sign in")
        if submitted:
            if (
                username == settings.demo_user
                and password == settings.demo_password
                and settings.demo_password
            ):
                st.session_state[_SESSION_KEY] = True
                st.rerun()
            st.error("Invalid demo credentials.")
    st.caption(
        "Cloud demo credentials are documented in the reviewer guide. "
        "They unlock synthetic read-only content only."
    )
    return False
