"""Admin page: lists every applicant stored in RDS and lets you download resumes."""

import os

import streamlit as st

from db import ensure_table, fetch_applicants, fetch_resume

# --------------------------------------------------------------------------- #
# Optional password gate (set ADMIN_PASSWORD in .env to enable)
# --------------------------------------------------------------------------- #
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
st.session_state.setdefault("admin_authenticated", False)

if ADMIN_PASSWORD and not st.session_state.admin_authenticated:
    with st.form("admin_login"):
        password = st.text_input("Admin password", type="password")
        if st.form_submit_button("Sign in", type="primary", icon=":material/login:"):
            if password == ADMIN_PASSWORD:
                st.session_state.admin_authenticated = True
                st.rerun()
            st.error("Incorrect password.", icon=":material/lock:")
    st.stop()

if not ADMIN_PASSWORD:
    st.warning(
        "This page is not password protected. Set `ADMIN_PASSWORD` in `.env` to require a login.",
        icon=":material/lock_open:",
    )

# --------------------------------------------------------------------------- #
# Load data
# --------------------------------------------------------------------------- #
try:
    ensure_table()
    df = fetch_applicants()
except Exception as exc:  # noqa: BLE001
    st.error(f"Could not load applicants: {exc}", icon=":material/error:")
    st.stop()

with st.container(horizontal=True, vertical_alignment="center"):
    st.metric("Total applicants", len(df))
    search = st.text_input(
        "Search",
        placeholder="Search by name, email or phone",
        label_visibility="collapsed",
        width="stretch",
    )
    if st.button("Refresh", icon=":material/refresh:"):
        fetch_applicants.clear()
        st.rerun()

if df.empty:
    st.info("No applications have been submitted yet.", icon=":material/inbox:")
    st.stop()

filtered = df
if search:
    q = search.strip().lower()
    mask = (
        df["name"].str.lower().str.contains(q, regex=False)
        | df["email"].str.lower().str.contains(q, regex=False)
        | df["phone"].str.lower().str.contains(q, regex=False)
    )
    filtered = df[mask]

# --------------------------------------------------------------------------- #
# Records table
# --------------------------------------------------------------------------- #
event = st.dataframe(
    filtered,
    hide_index=True,
    on_select="rerun",
    selection_mode="single-row",
    key="applicants_table",
    column_config={
        "id": st.column_config.NumberColumn("ID", pinned=True),
        "name": st.column_config.TextColumn("Name", pinned=True),
        "email": st.column_config.TextColumn("Email"),
        "phone": st.column_config.TextColumn("Phone"),
        "address": st.column_config.TextColumn("Address"),
        "resume_filename": st.column_config.TextColumn("Resume"),
        "resume_mime": None,
        "resume_size_bytes": st.column_config.NumberColumn("Resume size", format="bytes"),
        "submitted_at": st.column_config.DatetimeColumn(
            "Submitted", format="DD MMM YYYY, HH:mm"
        ),
    },
)

st.caption(f"Showing {len(filtered)} of {len(df)} applicants. Select a row to view details.")

st.download_button(
    "Export as CSV",
    data=filtered.drop(columns=["resume_mime"]).to_csv(index=False).encode("utf-8"),
    file_name="applicants.csv",
    mime="text/csv",
    icon=":material/download:",
)

# --------------------------------------------------------------------------- #
# Selected applicant details + resume download
# --------------------------------------------------------------------------- #
selected_rows = event.selection.rows
if selected_rows:
    row = filtered.iloc[selected_rows[0]]

    with st.container(border=True):
        st.subheader(row["name"])
        with st.container(horizontal=True):
            st.markdown(f":material/mail: {row['email']}")
            st.markdown(f":material/call: {row['phone']}")
            st.markdown(f":material/schedule: {row['submitted_at']:%d %b %Y, %H:%M}")
        st.markdown(f":material/home: {row['address']}")

        try:
            resume = fetch_resume(int(row["id"]))
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not load resume: {exc}", icon=":material/error:")
        else:
            if resume is None:
                st.warning("Resume not found for this applicant.", icon=":material/warning:")
            else:
                filename, mime, data = resume
                st.download_button(
                    f"Download {filename}",
                    data=data,
                    file_name=filename,
                    mime=mime or "application/octet-stream",
                    type="primary",
                    icon=":material/download:",
                    key=f"resume_download_{row['id']}",
                )
