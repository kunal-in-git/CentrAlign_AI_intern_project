from app.database.db import init_db
from app.tools.invoice_tools import (
    search_invoices,
    read_invoice,
    record_invoice,
    verify_record,
)


def test_invoice_workflow():
    init_db()

    result = search_invoices("Acme Corp")

    assert result["count"] >= 1

    latest = max(
        result["invoices"],
        key=lambda invoice: invoice["invoice_date"],
    )

    invoice_id = latest["invoice_id"]
    result = read_invoice(invoice_id)

    assert "invoice" in result
    invoice = result["invoice"]

    result = record_invoice(
        invoice_id=invoice_id,
        amount=invoice["amount"],
        due_date=invoice["due_date"],
    )

    assert result["status"] in {
        "created",
        "already_exists",
    }

    result = verify_record(invoice_id)

    assert result["verified"] is True


def test_wrong_amount_is_rejected():
    init_db()

    result = record_invoice(
        invoice_id="INV-ACME-1002",
        amount=1.0,
        due_date="2026-10-25",
    )

    assert "error" in result


def test_missing_invoice_cannot_be_verified():
    init_db()

    result = verify_record("DOES-NOT-EXIST")

    assert result["verified"] is False
