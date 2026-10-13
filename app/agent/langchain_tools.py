import json

from langchain.tools import tool

from app.tools.invoice_tools import (
    search_invoices,
    read_invoice,
    record_invoice,
    verify_record,
)


@tool
def search_invoice_tool(supplier: str, limit: int = 10) -> str:
    """Search source invoices for a supplier.
    Returns matching invoices, including their dates and amounts.
    Use this to find the latest invoice for a supplier.
    """
    result = search_invoices(supplier, limit)
    return json.dumps(result)


@tool
def read_invoice_tool(invoice_id: str) -> str:
    """Read the complete details of a source invoice.
    Use the exact invoice ID returned by the search tool.
    """
    result = read_invoice(invoice_id)
    return json.dumps(result)


@tool
def save_invoice_tool(
    invoice_id: str,
    amount: float,
    due_date: str,
) -> str:
    """Save an invoice to the simulated internal system.
    Use the amount and due date obtained from the source invoice.
    The due date must use YYYY-MM-DD format.
    """
    result = record_invoice(invoice_id, amount, due_date)
    return json.dumps(result)


@tool
def verify_invoice_tool(invoice_id: str) -> str:
    """Independently verify that the internal record exists
    and its supplier, amount, and due date match the source invoice.
    """
    result = verify_record(invoice_id)
    return json.dumps(result)


@tool(return_direct=True)
def ask_user_tool(question: str) -> str:
    """Pause the task and ask the user a clarifying question.
    Use this when the request is ambiguous, when no matching invoice
    exists, or when you cannot safely continue without more information.
    Ask one specific question.
    """
    return json.dumps({"question": question})


INVOICE_TOOLS = [
    search_invoice_tool,
    read_invoice_tool,
    save_invoice_tool,
    verify_invoice_tool,
    ask_user_tool,
]