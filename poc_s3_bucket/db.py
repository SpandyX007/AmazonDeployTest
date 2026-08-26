"""Shared database helpers for the applicant app (AWS RDS PostgreSQL via psycopg2)."""

import os
from contextlib import contextmanager

import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# NOTE: DB_DATABASE in .env holds the RDS *instance* identifier (e.g. "database-1"),
# not a Postgres database name. Like test.py, connect to the default "postgres"
# database; set DB_NAME in .env if you create a dedicated database later.
DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "port": int(os.getenv("DB_PORT", "5432")),
    "database": os.getenv("DB_NAME", "postgres"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "sslmode": "verify-full",
    "sslrootcert": os.path.join(BASE_DIR, "global-bundle.pem"),
}


@contextmanager
def get_connection():
    """Open a psycopg2 connection to RDS and always close it afterwards."""
    conn = psycopg2.connect(**DB_CONFIG)
    try:
        yield conn
    finally:
        conn.close()


@st.cache_resource
def ensure_table() -> bool:
    """Create the applicants table once per server process (retried if it fails)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS applicants (
                id              SERIAL PRIMARY KEY,
                name            VARCHAR(150)  NOT NULL,
                email           VARCHAR(255)  NOT NULL UNIQUE,
                phone           VARCHAR(20)   NOT NULL,
                address         TEXT          NOT NULL,
                resume_filename VARCHAR(255)  NOT NULL,
                resume_mime     VARCHAR(100),
                resume          BYTEA         NOT NULL,
                submitted_at    TIMESTAMPTZ   NOT NULL DEFAULT NOW()
            )
            """
        )
        conn.commit()
    return True


def save_applicant(name: str, email: str, phone: str, address: str, resume) -> int:
    """Insert one applicant row and return its id."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO applicants
                (name, email, phone, address, resume_filename, resume_mime, resume)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                name,
                email,
                phone,
                address,
                resume.name,
                resume.type,
                psycopg2.Binary(resume.getvalue()),
            ),
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    # Make the new row visible to the admin page immediately.
    fetch_applicants.clear()
    return new_id


@st.cache_data(ttl="60s", max_entries=1)
def fetch_applicants() -> pd.DataFrame:
    """Return every applicant (metadata only, resume bytes are fetched on demand)."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            SELECT id,
                   name,
                   email,
                   phone,
                   address,
                   resume_filename,
                   resume_mime,
                   octet_length(resume) AS resume_size_bytes,
                   submitted_at
            FROM applicants
            ORDER BY submitted_at DESC, id DESC
            """
        )
        columns = [col.name for col in cur.description]
        rows = cur.fetchall()
    return pd.DataFrame(rows, columns=columns)


def fetch_resume(applicant_id: int) -> tuple[str, str | None, bytes] | None:
    """Return (filename, mime, bytes) for one applicant, or None if not found."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT resume_filename, resume_mime, resume FROM applicants WHERE id = %s",
            (applicant_id,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    filename, mime, data = row
    return filename, mime, bytes(data)
