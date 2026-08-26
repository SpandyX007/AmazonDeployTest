"""Applicant form page: collects details + resume and stores them in AWS RDS."""

import re

import streamlit as st
from psycopg2 import errors as pg_errors

from db import ensure_table, save_applicant

ALLOWED_RESUME_TYPES = ["pdf", "doc", "docx"]
MAX_RESUME_MB = 5

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9][0-9 \-]{7,18}$")


def validate(name: str, email: str, phone: str, address: str, resume) -> list[str]:
    problems = []
    if not name:
        problems.append("Full name is required.")
    if not email:
        problems.append("Email is required.")
    elif not EMAIL_RE.match(email):
        problems.append("Enter a valid email address.")
    if not phone:
        problems.append("Phone number is required.")
    elif not PHONE_RE.match(phone):
        problems.append("Enter a valid phone number (digits, spaces, dashes, optional leading +).")
    if not address:
        problems.append("Address is required.")
    if resume is None:
        problems.append("Please upload your resume.")
    return problems


st.caption("Fill in your details and upload your resume. Submissions are stored in AWS RDS.")

st.session_state.setdefault("form_version", 0)
st.session_state.setdefault("last_saved", None)

# Show the confirmation from the previous run (the form was reset on success).
if st.session_state.last_saved:
    saved_name, saved_id = st.session_state.last_saved
    st.success(
        f"Thanks {saved_name}! Your application (#{saved_id}) has been saved.",
        icon=":material/check_circle:",
    )
    st.session_state.last_saved = None

try:
    ensure_table()
except Exception as exc:  # noqa: BLE001 - surface any connection/SQL problem to the user
    st.error(f"Could not connect to the database: {exc}", icon=":material/error:")
    st.stop()

# Widget keys are suffixed with a version so the form can be cleared after a
# successful submission without losing the user's input on validation errors.
v = st.session_state.form_version

with st.form(f"applicant_form_{v}"):
    name = st.text_input("Full name", max_chars=150, key=f"name_{v}")
    email = st.text_input(
        "Email", max_chars=255, placeholder="you@example.com", key=f"email_{v}"
    )
    phone = st.text_input(
        "Phone number", max_chars=20, placeholder="+91 98765 43210", key=f"phone_{v}"
    )
    address = st.text_area("Address", max_chars=1000, key=f"address_{v}")
    resume = st.file_uploader(
        "Resume",
        type=ALLOWED_RESUME_TYPES,
        max_upload_size=MAX_RESUME_MB,
        help=f"PDF, DOC or DOCX, up to {MAX_RESUME_MB} MB.",
        key=f"resume_{v}",
    )
    submitted = st.form_submit_button(
        "Submit application", type="primary", icon=":material/send:"
    )

if submitted:
    name = name.strip()
    email = email.strip().lower()
    phone = phone.strip()
    address = address.strip()

    problems = validate(name, email, phone, address, resume)
    if problems:
        for problem in problems:
            st.error(problem, icon=":material/warning:")
    else:
        try:
            with st.spinner("Saving your application..."):
                new_id = save_applicant(name, email, phone, address, resume)
        except pg_errors.UniqueViolation:
            st.error(
                "An application with this email address already exists.",
                icon=":material/warning:",
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Failed to save your application: {exc}", icon=":material/error:")
        else:
            st.session_state.last_saved = (name, new_id)
            st.session_state.form_version += 1
            st.rerun()
