import json
import logging
import threading
import uuid

import httpx
from langchain.agents import create_agent
from langchain_ollama import ChatOllama
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel, Field

from app.config import (
    MAX_AGENT_STEPS,
    OLLAMA_HOST,
    OLLAMA_MODEL,
    OLLAMA_TIMEOUT_SECONDS,
)
from app.agent.langchain_tools import INVOICE_TOOLS
from app.tools.invoice_tools import verify_record


logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """
You are an autonomous invoice-processing worker.

Use the provided tools to complete the user's task.

For an invoice-processing task:
1. Search for the requested supplier's invoices.
2. Check the supplier field of the results. If they contain more than one
   different supplier, call ask_user_tool and ask which supplier was meant.
3. If the user requests the latest invoice, choose the greatest invoice_date.
4. Read the selected invoice before saving it.
5. Use the amount and due date returned by the source invoice.
6. Save the invoice using the save tool.
7. Always call the verification tool after saving, even if the save tool
   reports that the invoice already exists.
8. Never claim success without a verified result.
9. If a tool fails, examine the error and recover when safe.
10. Never invent invoice details or tool results.

If the user only asks for information, answer it from tool results
and do not save anything.

If the request is ambiguous, no matching invoice exists, or you cannot
safely continue, call ask_user_tool with one specific question instead
of guessing. Never offer to create or invent invoices.
"""


READ_ONLY_TOOL_NAMES = {
    "search_invoice_tool",
    "read_invoice_tool",
    "ask_user_tool",
}


class TaskIntent(BaseModel):
    requires_save: bool = Field(
        description=(
            "True if the user wants an invoice saved, recorded or entered "
            "into the internal system. False if they only want information."
        )
    )


llm = ChatOllama(
    model=OLLAMA_MODEL,
    base_url=OLLAMA_HOST,
    temperature=0,
    client_kwargs={"timeout": OLLAMA_TIMEOUT_SECONDS},
)

intent_classifier = llm.with_structured_output(TaskIntent)

checkpointer = InMemorySaver()

agent = create_agent(
    model=llm,
    tools=INVOICE_TOOLS,
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)

read_only_agent = create_agent(
    model=llm,
    tools=[t for t in INVOICE_TOOLS if t.name in READ_ONLY_TOOL_NAMES],
    system_prompt=SYSTEM_PROMPT,
    checkpointer=checkpointer,
)

RECURSION_LIMIT = MAX_AGENT_STEPS * 2 + 1

_runs: dict[str, dict] = {}
_runs_lock = threading.Lock()


def run_task(task: str) -> dict:
    """Start a new run for a natural-language task."""

    run_id = str(uuid.uuid4())

    with _runs_lock:
        _runs[run_id] = {"requests": [task], "status": "running"}

    return _execute(run_id, task)


def continue_task(run_id: str, reply: str) -> dict:
    """Resume a run that is waiting for the user's answer."""

    with _runs_lock:
        run = _runs.get(run_id)

        if run is None:
            raise KeyError(run_id)

        if run["status"] != "needs_clarification":
            raise ValueError(
                f"Run is {run['status']!r}, not waiting for a reply."
            )

        run["requests"].append(reply)
        run["status"] = "running"

    return _execute(run_id, reply)


def _execute(run_id: str, message: str) -> dict:
    config = {
        "configurable": {"thread_id": run_id},
        "recursion_limit": RECURSION_LIMIT,
    }
    error = None

    try:
        requires_save = _classify_intent(run_id)
        selected_agent = agent if requires_save else read_only_agent
        selected_agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config=config,
        )
    except GraphRecursionError:
        requires_save = _runs[run_id].get("requires_save", True)
        error = (
            f"Stopped after reaching the limit of {MAX_AGENT_STEPS} "
            "agent steps without finishing the task."
        )
    except httpx.TimeoutException:
        requires_save = _runs[run_id].get("requires_save", True)
        error = (
            f"The language model did not respond within "
            f"{OLLAMA_TIMEOUT_SECONDS:.0f} seconds."
        )
    except (httpx.ConnectError, ConnectionError):
        requires_save = _runs[run_id].get("requires_save", True)
        error = (
            f"Could not reach the language model at {OLLAMA_HOST}. "
            "Is Ollama running?"
        )
    except Exception as exc:
        logger.exception("Agent run %s failed", run_id)
        requires_save = _runs[run_id].get("requires_save", True)
        error = f"Agent error: {type(exc).__name__}: {exc}"

    state = agent.get_state(config).values
    messages = state.get("messages", [])

    result = _build_result(run_id, messages, requires_save, error)

    with _runs_lock:
        _runs[run_id]["status"] = result["status"]

    return result


def _classify_intent(run_id: str) -> bool:
    """Decide whether the task needs a saved, verified record."""

    request = "\n".join(_runs[run_id]["requests"])

    try:
        intent = intent_classifier.invoke(
            "Classify this request for an invoice-processing worker.\n\n"
            f"Request:\n{request}"
        )
        requires_save = bool(intent.requires_save)
    except (httpx.HTTPError, ConnectionError):
        raise
    except Exception:
        logger.warning("Intent classification failed; assuming a save")
        requires_save = True

    with _runs_lock:
        _runs[run_id]["requires_save"] = requires_save

    return requires_save


def _build_result(
    run_id: str,
    messages: list,
    requires_save: bool,
    error: str | None,
) -> dict:
    tool_trace = []
    saved_invoice_ids = set()
    verification_tool_passed = set()
    successful_tool_results = 0

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
                tool_name != "ask_user_tool"
                and isinstance(observation, dict)
                and "error" not in observation
            ):
                successful_tool_results += 1

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

    question = _pending_question(messages)
    answer = _final_answer(messages)

    if error:
        status, reason = "failed", error
        answer = answer or error
    elif question:
        status = "needs_clarification"
        reason = "The agent needs more information to continue safely."
        answer = question
    elif requires_save and verified_ids:
        status = "completed"
        reason = (
            "Saved record(s) passed both the agent's verification "
            "and an independent database check."
        )
    elif requires_save:
        status = "failed"
        reason = (
            "The task required saving an invoice, but no record passed "
            "verification."
        )
    elif successful_tool_results:
        status = "completed"
        reason = "Answered from tool results; no records were changed."
    else:
        status = "failed"
        reason = "The agent answered without any successful tool result."

    return {
        "run_id": run_id,
        "status": status,
        "reason": reason,
        "question": question,
        "requires_save": requires_save,
        "task": _runs[run_id]["requests"][0],
        "answer": answer or "The agent returned no response.",
        "model": OLLAMA_MODEL,
        "message_count": len(messages),
        "tool_trace": tool_trace,
        "verification": independent_checks,
        "verified_invoice_ids": verified_ids,
    }


def _pending_question(messages: list) -> str | None:
    """Return the question if the run ended on ask_user_tool."""

    if not messages:
        return None

    last = messages[-1]

    if (
        getattr(last, "type", "") != "tool"
        or getattr(last, "name", "") != "ask_user_tool"
    ):
        return None

    try:
        return json.loads(last.content).get("question")
    except (ValueError, TypeError, AttributeError):
        return str(last.content)


def _final_answer(messages: list) -> str:
    for message in reversed(messages):
        if getattr(message, "type", "") == "ai" and message.content:
            return str(message.content)

    return ""
