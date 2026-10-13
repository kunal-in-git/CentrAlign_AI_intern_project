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
        "INV-ACME-0998",
        "Acme Corp",
        "2026-08-01",
        990.00,
        "2026-08-31",
        "August services invoice",
    ),
    (
        "INV-NORTH-2001",
        "Northwind Ltd",
        "2026-10-05",
        920.00,
        "2026-10-28",
        "Office supplies invoice",
    ),
    (
        "INV-NORTH-1987",
        "Northwind Ltd",
        "2026-09-12",
        455.20,
        "2026-10-12",
        "Printer toner and paper",
    ),
    (
        "INV-ACMELOG-3001",
        "Acme Logistics",
        "2026-10-07",
        3120.00,
        "2026-11-06",
        "Freight and warehousing, October",
    ),
    (
        "INV-ACMELOG-2990",
        "Acme Logistics",
        "2026-09-08",
        2875.50,
        "2026-10-08",
        "Freight and warehousing, September",
    ),
    (
        "INV-GLOBEX-4100",
        "Globex Industries",
        "2026-10-09",
        12500.00,
        "2026-11-08",
        "Annual software licence renewal",
    ),
    (
        "INV-GLOBEX-4087",
        "Globex Industries",
        "2026-09-15",
        640.00,
        "2026-10-15",
        "Implementation consulting hours",
    ),
    (
        "INV-INITECH-501",
        "Initech",
        "2026-10-01",
        78.99,
        "2026-10-31",
        "Monthly cloud backup subscription",
    ),
    (
        "INV-STARK-7001",
        "Stark Supplies",
        "2026-10-10",
        5400.00,
        "2026-11-09",
        "Laptops for new hires",
    ),
    (
        "INV-STARK-7002",
        "Stark Supplies",
        "2026-10-10",
        210.00,
        "2026-11-09",
        "Laptop bags and accessories",
    ),
    (
        "INV-UMBRELLA-88",
        "Umbrella Health",
        "2026-07-20",
        1500.00,
        "2026-08-19",
        "Employee health checkups",
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

        connection.executemany(
            """
            INSERT OR IGNORE INTO invoices (
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
