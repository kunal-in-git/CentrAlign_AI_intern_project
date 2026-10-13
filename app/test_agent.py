from app.database.db import init_db
from app.agent.worker import run_task


if __name__ == "__main__":
    init_db()

    task = (
        "Find the latest invoice from Acme Corp, "
        "read its amount and due date, save it in the "
        "internal system, and verify that it was saved correctly."
    )

    result = run_task(task)

    print("\nFINAL RESULT")
    print(result["answer"])

    print("\nMODEL")
    print(result["model"])

    print("\nMESSAGE COUNT")
    print(result["message_count"])

    print("\nSTATUS")
    print(result["status"], result["verified_invoice_ids"])

    print("\nTOOL TRACE")
    for step in result["tool_trace"]:
        if step["kind"] == "tool_call":
            print(f"-> {step['tool']}({step['args']})")
        else:
            print(f"<- {step['tool']}: {step['observation']}")