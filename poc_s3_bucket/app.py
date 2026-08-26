"""Entry point: applicant form + admin page backed by AWS RDS PostgreSQL."""

import streamlit as st

st.set_page_config(page_title="Applicant portal", page_icon=":material/person_add:")

page = st.navigation(
    [
        st.Page("app_pages/apply.py", title="Apply", icon=":material/person_add:", default=True),
        st.Page("app_pages/admin.py", title="Admin", icon=":material/admin_panel_settings:"),
    ],
    position="top",
)

st.title(page.title)
page.run()
