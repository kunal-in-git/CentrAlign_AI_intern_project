from .database.db import get_connection, init_db

init_db()

with get_connection() as connection:
    invoices = connection.execute(
        "SELECT * FROM invoices ORDER BY invoice_date DESC"
    ).fetchall()

    print("Invoices found:", len(invoices))

    for invoice in invoices:
        print(dict(invoice))
