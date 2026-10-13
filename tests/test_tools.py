import json

import pytest

from app.agent.langchain_tools import (
    INVOICE_TOOLS,
    ask_user_tool,
    read_invoice_tool,
    save_invoice_tool,
    search_invoice_tool,
)
from app.database.db import SEED_INVOICES, get_connection, init_db
from app.tools.invoice_tools import (
    search_invoices,
    read_invoice,
    record_invoice,
    verify_record,
)


def count_records():
    with get_connection() as connection:
        return connection.execute(
            "SELECT COUNT(*) FROM internal_records"
        ).fetchone()[0]


def test_invoice_workflow():
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

    assert result["status"] == "created"

    result = verify_record(invoice_id)

    assert result["verified"] is True


def test_init_db_is_idempotent():
    init_db()
    init_db()

    with get_connection() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM invoices"
        ).fetchone()[0]

    assert count == len(SEED_INVOICES)


def test_search_returns_newest_first():
    result = search_invoices("Acme Corp")
    dates = [invoice["invoice_date"] for invoice in result["invoices"]]

    assert result["count"] == 3
    assert dates == sorted(dates, reverse=True)
    assert result["invoices"][0]["invoice_id"] == "INV-ACME-1002"


def test_search_is_case_insensitive():
    result = search_invoices("northwind ltd")

    assert result["count"] == 2
    assert all(
        invoice["supplier"] == "Northwind Ltd"
        for invoice in result["invoices"]
    )


def test_ambiguous_supplier_returns_candidates_instead_of_invoices():
    result = search_invoices("Acme")

    assert result["count"] == 0
    assert result["invoices"] == []
    assert "more than one supplier" in result["error"]
    assert result["matching_suppliers"] == ["Acme Corp", "Acme Logistics"]


def test_exact_supplier_name_is_not_ambiguous():
    result = search_invoices("acme corp")
    suppliers = {invoice["supplier"] for invoice in result["invoices"]}

    assert suppliers == {"Acme Corp"}


def test_partial_name_matching_one_supplier_is_allowed():
    result = search_invoices("Globex")

    assert result["count"] == 2
    assert "error" not in result


def test_search_unknown_supplier_returns_nothing():
    result = search_invoices("Wayne Enterprises")

    assert result == {"invoices": [], "count": 0}


@pytest.mark.parametrize("supplier", ["", "   "])
def test_search_blank_supplier_returns_nothing(supplier):
    assert search_invoices(supplier) == {"invoices": [], "count": 0}


@pytest.mark.parametrize(
    "limit, expected",
    [(0, 1), (-5, 1), (2, 2), (100, 3)],
)
def test_search_limit_is_clamped(limit, expected):
    result = search_invoices("Acme Corp", limit=limit)

    assert result["count"] == expected


def test_read_invoice_returns_full_details():
    result = read_invoice("INV-GLOBEX-4100")

    assert result["invoice"] == {
        "invoice_id": "INV-GLOBEX-4100",
        "supplier": "Globex Industries",
        "invoice_date": "2026-10-09",
        "amount": 12500.00,
        "due_date": "2026-11-08",
        "description": "Annual software licence renewal",
    }


def test_read_invoice_strips_whitespace():
    result = read_invoice("  INV-INITECH-501  ")

    assert result["invoice"]["supplier"] == "Initech"


def test_read_missing_invoice_returns_error():
    result = read_invoice("DOES-NOT-EXIST")

    assert "error" in result
    assert "not found" in result["error"]


def test_wrong_amount_is_rejected():
    result = record_invoice(
        invoice_id="INV-ACME-1002",
        amount=1.0,
        due_date="2026-10-25",
    )

    assert "error" in result
    assert count_records() == 0


def test_wrong_due_date_is_rejected():
    result = record_invoice(
        invoice_id="INV-ACME-1002",
        amount=1845.75,
        due_date="2026-10-26",
    )

    assert result == {
        "error": "Due date does not match the source invoice."
    }
    assert count_records() == 0


@pytest.mark.parametrize(
    "due_date",
    ["25-10-2026", "2026/10/25", "October 25, 2026", "", "2026-13-01"],
)
def test_badly_formatted_due_date_is_rejected(due_date):
    result = record_invoice(
        invoice_id="INV-ACME-1002",
        amount=1845.75,
        due_date=due_date,
    )

    assert result == {"error": "Due date must use YYYY-MM-DD format."}
    assert count_records() == 0


def test_unknown_invoice_cannot_be_recorded():
    result = record_invoice(
        invoice_id="INV-FAKE-0001",
        amount=100.0,
        due_date="2026-10-25",
    )

    assert result == {"error": "Cannot record an unknown invoice."}
    assert count_records() == 0


def test_amount_within_tolerance_is_accepted():
    result = record_invoice(
        invoice_id="INV-INITECH-501",
        amount=78.9901,
        due_date="2026-10-31",
    )

    assert result["status"] == "created"


def test_record_copies_supplier_from_source():
    result = record_invoice(
        invoice_id="INV-STARK-7001",
        amount=5400.00,
        due_date="2026-11-09",
    )

    assert result["record"]["supplier"] == "Stark Supplies"
    assert result["record"]["invoice_id"] == "INV-STARK-7001"


def test_saving_twice_does_not_duplicate():
    first = record_invoice("INV-NORTH-2001", 920.00, "2026-10-28")
    second = record_invoice("INV-NORTH-2001", 920.00, "2026-10-28")

    assert first["status"] == "created"
    assert second["status"] == "already_exists"
    assert second["record"]["record_id"] == first["record"]["record_id"]
    assert count_records() == 1


def test_invoice_id_whitespace_is_normalised_on_save():
    first = record_invoice(" INV-NORTH-2001 ", 920.00, "2026-10-28")
    second = record_invoice("INV-NORTH-2001", 920.00, "2026-10-28")

    assert first["record"]["invoice_id"] == "INV-NORTH-2001"
    assert second["status"] == "already_exists"


def test_same_day_invoices_are_saved_separately():
    first = record_invoice("INV-STARK-7001", 5400.00, "2026-11-09")
    second = record_invoice("INV-STARK-7002", 210.00, "2026-11-09")

    assert first["status"] == "created"
    assert second["status"] == "created"
    assert count_records() == 2


def test_missing_invoice_cannot_be_verified():
    result = verify_record("DOES-NOT-EXIST")

    assert result["verified"] is False
    assert result["reason"] == "Source invoice not found."


def test_unsaved_invoice_is_not_verified():
    result = verify_record("INV-GLOBEX-4087")

    assert result["verified"] is False
    assert result["reason"] == "No internal record was saved."


def test_tampered_record_fails_verification():
    record_invoice("INV-ACMELOG-3001", 3120.00, "2026-11-06")

    with get_connection() as connection:
        connection.execute(
            "UPDATE internal_records SET amount = ? WHERE invoice_id = ?",
            (9999.99, "INV-ACMELOG-3001"),
        )
        connection.commit()

    result = verify_record("INV-ACMELOG-3001")

    assert result["verified"] is False
    assert result["reason"] == (
        "Saved record does not match the source invoice."
    )


def test_every_seed_invoice_can_be_saved_and_verified():
    for invoice_id, _, _, amount, due_date, _ in SEED_INVOICES:
        result = record_invoice(invoice_id, amount, due_date)

        assert result["status"] == "created", invoice_id
        assert verify_record(invoice_id)["verified"] is True, invoice_id

    assert count_records() == len(SEED_INVOICES)


def test_agent_tools_have_descriptions():
    for agent_tool in INVOICE_TOOLS:
        assert agent_tool.description.strip(), agent_tool.name


def test_search_tool_returns_json():
    output = search_invoice_tool.invoke({"supplier": "Initech"})
    data = json.loads(output)

    assert data["count"] == 1
    assert data["invoices"][0]["invoice_id"] == "INV-INITECH-501"


def test_read_tool_returns_error_as_json():
    output = read_invoice_tool.invoke({"invoice_id": "NOPE"})

    assert "error" in json.loads(output)


def test_save_tool_rejects_wrong_amount():
    output = save_invoice_tool.invoke({
        "invoice_id": "INV-UMBRELLA-88",
        "amount": 15.00,
        "due_date": "2026-08-19",
    })

    assert "error" in json.loads(output)
    assert count_records() == 0


def test_ask_user_tool_returns_question_and_stops_agent():
    output = ask_user_tool.invoke({"question": "Which Acme supplier?"})

    assert json.loads(output) == {"question": "Which Acme supplier?"}
    assert ask_user_tool.return_direct is True
