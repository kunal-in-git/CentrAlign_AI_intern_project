import json

from langchain.agents import create_agent
from langchain_ollama import ChatOllama

from app.config import OLLAMA_HOST, OLLAMA_MODEL
from app.agent.langchain_tools import INVOICE_TOOLS
from app.tools.invoice_tools import verify_record


SYSTEM_PROMPT = """
You are an autonomous invoice-processing worker.

Use the provided tools to complete the user's task.

For an invoice-processing task:
1. Search for the requested supplier's invoices.
2. If the user requests the latest invoice, choose the greatest invoice_date.
3. Read the selected invoice before saving it.
4. Use the amount and due date returned by the source invoice.
5. Save the invoice using the save tool.
6. Call the verification tool after saving.
7. Never claim success without a verified result.
8. If a tool fails, examine the error and recover when safe.
9. Never invent invoice details or tool results.
10. Ask for clarification when the task is ambiguous.
"""


llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_HOST,
    temperature=0,
)

agent = create_agent(
    model=llm,
    tools=INVOICE_TOOLS,
    system_prompt=SYSTEM_PROMPT,
)


def run_task(task: str) -> dict:
    """Run a task and independently verify any invoice the agent saves."""

    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 20},
    )

    messages = result["messages"]
    tool_trace = []
    saved_invoice_ids = set()
    verification_tool_passed = set()

    for message in messages:
        for call in getattr(message, "tool_calls", []) or []:
            name = call.get("name", "")
            args = call.get("args", {}) or {}

            tool_trace.append({
                "kind": "tool_call",
                "tool": name,
                "args": args,
            })

            invoice_id = args.get("invoice_id")

            if name == "save_invoice_tool" and invoice_id:
                saved_invoice_ids.add(invoice_id)

        if getattr(message, "type", "") == "tool":
            content = message.content

            try:
                observation = (
                    json.loads(content)
                    if isinstance(content, str)
                    else content
                )
            except (ValueError, TypeError):
                observation = {"raw_result": str(content)}

            tool_name = getattr(message, "name", "unknown")

            tool_trace.append({
                "kind": "tool_result",
                "tool": tool_name,
                "observation": observation,
            })

            if (
                tool_name == "verify_invoice_tool"
                and isinstance(observation, dict)
                and observation.get("verified") is True
            ):
                invoice_id = observation.get("invoice_id")
                if invoice_id:
                    verification_tool_passed.add(invoice_id)

    independent_checks = {
        invoice_id: verify_record(invoice_id)
        for invoice_id in saved_invoice_ids
    }

    verified_ids = [
        invoice_id
        for invoice_id, check in independent_checks.items()
        if check.get("verified") is True
        and invoice_id in verification_tool_passed
    ]

    last_message = messages[-1] if messages else None
    answer = (
        last_message.content
        if last_message is not None
        else "The agent returned no response."
    )

    if not isinstance(answer, str):
        answer = str(answer)

    completed = bool(verified_ids)

    return {
        "status": "completed" if completed else "failed",
        "task": task,
        "answer": answer,
        "model": OLLAMA_MODEL,
        "message_count": len(messages),
        "tool_trace": tool_trace,
        "verification": {
            invoice_id: check
            for invoice_id, check in independent_checks.items()
        },
        "verified_invoice_ids": verified_ids,
    }
