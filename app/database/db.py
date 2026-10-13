import sqlite3
from pathlib import Path

from app.config import DATABASE_PATH


SEED_INVOICES = [
    (
        "INV-ACME-1001",
        "Acme Corp",
        "2026-09-02",
        1250.00,
        "2026-09-30",
        "September services invoice",
    ),
    (
        "INV-ACME-1002",
        "Acme Corp",
        "2026-10-04",
        1845.75,
        "2026-10-25",
        "October support invoice",
    ),
    (
        "INV-NORTH-2001",
        "Northwind Ltd",
        "2026-10-05",
        920.00,
        "2026-10-28",
        "Office supplies invoice",
    ),
]


def get_connection():
    """Create a connection to our SQLite database."""
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    """Create database tables and insert demo invoices."""
    Path(DATABASE_PATH).parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with get_connection() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS invoices (
                invoice_id TEXT PRIMARY KEY,
                supplier TEXT NOT NULL,
                invoice_date TEXT NOT NULL,
                amount REAL NOT NULL,
                due_date TEXT NOT NULL,
                description TEXT NOT NULL
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS internal_records (
                record_id TEXT PRIMARY KEY,
                invoice_id TEXT NOT NULL UNIQUE,
                supplier TEXT NOT NULL,
                amount REAL NOT NULL,
                due_date TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        existing_count = connection.execute(
            "SELECT COUNT(*) FROM invoices"
        ).fetchone()[0]

        if existing_count == 0:
            connection.executemany(
                """
                INSERT INTO invoices (
                    invoice_id,
                    supplier,
                    invoice_date,
                    amount,
                    due_date,
                    description
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                SEED_INVOICES,
            )

        connection.commit()
