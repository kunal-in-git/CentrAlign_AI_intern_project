import uuid
from datetime import datetime, timezone

from app.database.db import get_connection


def search_invoices(supplier: str, limit: int = 10) -> dict:
    """Find invoices for a supplier, newest first."""

    if not supplier.strip():
        return {"invoices": [], "count": 0}

    limit = max(1, min(limit, 20))
    query = supplier.strip()

    with get_connection() as connection:
        suppliers = [
            row[0]
            for row in connection.execute(
                """
                SELECT DISTINCT supplier
                FROM invoices
                WHERE supplier LIKE ?
                ORDER BY supplier
                """,
                (f"%{query}%",),
            ).fetchall()
        ]

        exact = [s for s in suppliers if s.lower() == query.lower()]

        if len(suppliers) > 1 and not exact:
            return {
                "invoices": [],
                "count": 0,
                "error": (
                    f"{query!r} matches more than one supplier: "
                    f"{', '.join(suppliers)}. Ask the user which one "
                    "they mean."
                ),
                "matching_suppliers": suppliers,
            }

        rows = connection.execute(
            """
            SELECT *
            FROM invoices
            WHERE supplier LIKE ?
            ORDER BY invoice_date DESC
            LIMIT ?
            """,
            (exact[0] if exact else f"%{query}%", limit),
        ).fetchall()

    invoices = [dict(row) for row in rows]

    return {
        "invoices": invoices,
        "count": len(invoices),
    }


def read_invoice(invoice_id: str) -> dict:
    """Read the full details of one invoice."""

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT *
            FROM invoices
            WHERE invoice_id = ?
            """,
            (invoice_id.strip(),),
        ).fetchone()

    if row is None:
        return {
            "error": f"Invoice {invoice_id!r} was not found."
        }

    return {"invoice": dict(row)}


def record_invoice(
    invoice_id: str,
    amount: float,
    due_date: str,
) -> dict:
    """Validate and save an invoice to the internal system."""

    try:
        parsed_date = datetime.strptime(
            due_date, "%Y-%m-%d"
        ).date()
    except (ValueError, TypeError):
        return {"error": "Due date must use YYYY-MM-DD format."}

    with get_connection() as connection:
        invoice = connection.execute(
            """
            SELECT *
            FROM invoices
            WHERE invoice_id = ?
            """,
            (invoice_id.strip(),),
        ).fetchone()

        if invoice is None:
            return {"error": "Cannot record an unknown invoice."}

        if abs(float(invoice["amount"]) - float(amount)) > 0.001:
            return {
                "error": "Amount does not match the source invoice."
            }

        if invoice["due_date"] != parsed_date.isoformat():
            return {
                "error": "Due date does not match the source invoice."
            }

        existing = connection.execute(
            """
            SELECT *
            FROM internal_records
            WHERE invoice_id = ?
            """,
            (invoice_id.strip(),),
        ).fetchone()

        if existing is not None:
            return {
                "status": "already_exists",
                "record": dict(existing),
            }

        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()

        connection.execute(
            """
            INSERT INTO internal_records (
                record_id,
                invoice_id,
                supplier,
                amount,
                due_date,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                invoice_id.strip(),
                invoice["supplier"],
                float(amount),
                parsed_date.isoformat(),
                created_at,
            ),
        )

        connection.commit()

        saved_record = connection.execute(
            """
            SELECT *
            FROM internal_records
            WHERE record_id = ?
            """,
            (record_id,),
        ).fetchone()

    return {
        "status": "created",
        "record": dict(saved_record),
    }


def verify_record(invoice_id: str) -> dict:
    """Independently compare the saved record to the source invoice."""

    with get_connection() as connection:
        source = connection.execute(
            """
            SELECT *
            FROM invoices
            WHERE invoice_id = ?
            """,
            (invoice_id.strip(),),
        ).fetchone()

        saved = connection.execute(
            """
            SELECT *
            FROM internal_records
            WHERE invoice_id = ?
            """,
            (invoice_id.strip(),),
        ).fetchone()

    if source is None:
        return {
            "verified": False,
            "reason": "Source invoice not found.",
        }

    if saved is None:
        return {
            "verified": False,
            "reason": "No internal record was saved.",
        }

    matches = (
        source["supplier"] == saved["supplier"]
        and abs(
            float(source["amount"]) - float(saved["amount"])
        ) < 0.001
        and source["due_date"] == saved["due_date"]
    )

    return {
        "verified": matches,
        "invoice_id": invoice_id,
        "source": dict(source),
        "saved_record": dict(saved),
        "reason": (
            "Saved record matches the source invoice."
            if matches
            else "Saved record does not match the source invoice."
        ),
    }
