import { useEffect, useState } from "react";
import {
  getHealth,
  getInvoices,
  getRecords,
  replyToRun,
  runTask,
} from "./api";
import "./App.css";

const EXAMPLES = [
  {
    label: "Save latest Acme Corp invoice",
    task:
      "Find the latest invoice from Acme Corp, read its amount and due date, " +
      "save it in the internal system, and verify that it was saved correctly.",
  },
  {
    label: "Ask about Northwind",
    task: "What is the amount and due date of the latest Northwind Ltd invoice?",
  },
  {
    label: "Ambiguous supplier",
    task: "Save the latest invoice from Acme into the internal system.",
  },
  {
    label: "Unknown supplier",
    task: "Record the latest invoice from Wayne Enterprises.",
  },
];

const STATUS_LABELS = {
  completed: "Completed",
  needs_clarification: "Needs your input",
  failed: "Failed",
};

const STATUS_ICONS = {
  completed: "✓",
  needs_clarification: "?",
  failed: "✕",
};

const TOOL_LABELS = {
  search_invoice_tool: "Search invoices",
  read_invoice_tool: "Read invoice",
  save_invoice_tool: "Save to internal system",
  verify_invoice_tool: "Verify saved record",
  ask_user_tool: "Ask the user",
};

const COMPARE_FIELDS = [
  ["supplier", "Supplier"],
  ["amount", "Amount"],
  ["due_date", "Due date"],
];

function errorMessage(err, fallback) {
  return err.response?.data?.detail || err.message || fallback;
}

function formatAmount(value) {
  return Number(value).toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatArgs(args) {
  return Object.entries(args || {})
    .map(([key, value]) => `${key}=${JSON.stringify(value)}`)
    .join(", ");
}

function buildSteps(trace) {
  const steps = [];
  const pending = [];

  for (const entry of trace || []) {
    if (entry.kind === "tool_call") {
      const step = { tool: entry.tool, args: entry.args };
      steps.push(step);
      pending.push(step);
    } else {
      const index = pending.findIndex((step) => step.tool === entry.tool);
      const step =
        index >= 0 ? pending.splice(index, 1)[0] : { tool: entry.tool };

      if (index < 0) steps.push(step);
      step.observation = entry.observation;
    }
  }

  return steps;
}

function describeStep(step) {
  const obs = step.observation;

  if (obs === undefined) {
    return { tone: "pending", icon: "…", text: "No result recorded." };
  }

  if (obs?.error) {
    return { tone: "error", icon: "!", text: obs.error };
  }

  switch (step.tool) {
    case "search_invoice_tool": {
      const ids = (obs.invoices || []).map((i) => i.invoice_id).join(", ");
      return {
        tone: "ok",
        icon: "✓",
        text: `${obs.count} invoice(s) found${ids ? `: ${ids}` : ""}`,
      };
    }
    case "read_invoice_tool": {
      const inv = obs.invoice || {};
      return {
        tone: "ok",
        icon: "✓",
        text: `${inv.supplier} · ${formatAmount(inv.amount)} · due ${inv.due_date}`,
      };
    }
    case "save_invoice_tool":
      return {
        tone: "ok",
        icon: "✓",
        text:
          obs.status === "already_exists"
            ? "Already saved earlier, no duplicate created."
            : "New record created.",
      };
    case "verify_invoice_tool":
      return {
        tone: obs.verified ? "ok" : "error",
        icon: obs.verified ? "✓" : "!",
        text: obs.reason,
      };
    case "ask_user_tool":
      return { tone: "question", icon: "?", text: obs.question };
    default:
      return { tone: "ok", icon: "✓", text: "Done." };
  }
}

function Timeline({ trace }) {
  const steps = buildSteps(trace);

  if (steps.length === 0) {
    return <p className="muted">The agent did not call any tools.</p>;
  }

  return (
    <ol className="timeline">
      {steps.map((step, index) => {
        const { tone, icon, text } = describeStep(step);

        return (
          <li key={index} className={`step step-${tone}`}>
            <span className="step-icon">{icon}</span>
            <div>
              <div className="step-title">
                <strong>{TOOL_LABELS[step.tool] || step.tool}</strong>
                {step.args && (
                  <span className="step-args">{formatArgs(step.args)}</span>
                )}
              </div>
              <p className="step-summary">{text}</p>
              {step.observation !== undefined && (
                <details>
                  <summary>Raw result</summary>
                  <pre>{JSON.stringify(step.observation, null, 2)}</pre>
                </details>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

function Verification({ verification }) {
  const entries = Object.entries(verification || {});

  if (entries.length === 0) {
    return <p className="muted">No records were saved in this run.</p>;
  }

  return entries.map(([invoiceId, check]) => (
    <div key={invoiceId} className="compare">
      <div className="compare-head">
        <code>{invoiceId}</code>
        <span className={`badge badge-${check.verified ? "completed" : "failed"}`}>
          {check.verified ? "✓ Matches source" : "✕ Mismatch"}
        </span>
      </div>

      {check.source && check.saved_record ? (
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Source invoice</th>
              <th>Saved record</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {COMPARE_FIELDS.map(([field, label]) => {
              const source = check.source[field];
              const saved = check.saved_record[field];
              const same =
                field === "amount"
                  ? Math.abs(Number(source) - Number(saved)) < 0.001
                  : source === saved;

              return (
                <tr key={field}>
                  <td>{label}</td>
                  <td>{field === "amount" ? formatAmount(source) : source}</td>
                  <td>{field === "amount" ? formatAmount(saved) : saved}</td>
                  <td className={same ? "match" : "mismatch"}>
                    {same ? "✓" : "✕"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      ) : (
        <p className="muted" style={{ padding: "10px 14px" }}>
          {check.reason}
        </p>
      )}
    </div>
  ));
}

export default function App() {
  const [task, setTask] = useState(EXAMPLES[0].task);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [records, setRecords] = useState([]);
  const [invoices, setInvoices] = useState([]);
  const [error, setError] = useState("");
  const [reply, setReply] = useState("");
  const [online, setOnline] = useState(null);

  function refreshData() {
    return Promise.all([getRecords(), getInvoices()])
      .then(([recordData, invoiceData]) => {
        setRecords(recordData);
        setInvoices(invoiceData);
        setOnline(true);
      })
      .catch((err) => {
        setOnline(false);
        setError(errorMessage(err, "Could not load data from the backend."));
      });
  }

  useEffect(() => {
    getHealth()
      .then(() => setOnline(true))
      .catch(() => setOnline(false));

    Promise.all([getRecords(), getInvoices()])
      .then(([recordData, invoiceData]) => {
        setRecords(recordData);
        setInvoices(invoiceData);
      })
      .catch((err) =>
        setError(errorMessage(err, "Could not load data from the backend."))
      );
  }, []);

  async function execute(request) {
    setRunning(true);
    setError("");

    try {
      setResult(await request());
      await refreshData();
    } catch (err) {
      setError(errorMessage(err, "Task execution failed."));
    } finally {
      setRunning(false);
    }
  }

  async function handleRunTask(event) {
    event.preventDefault();
    setResult(null);
    setReply("");
    await execute(() => runTask(task.trim()));
  }

  async function handleReply(event) {
    event.preventDefault();

    const text = reply.trim();
    if (!text || !result?.run_id) return;

    setReply("");
    await execute(() => replyToRun(result.run_id, text));
  }

  const savedIds = new Set(records.map((record) => record.invoice_id));
  const stepCount = result
    ? (result.tool_trace || []).filter((s) => s.kind === "tool_call").length
    : 0;

  return (
    <main className="container">
      <header className="topbar">
        <div>
          <p className="eyebrow">CentrAlign AI</p>
          <h1>Autonomous Task Worker</h1>
          <p className="subtitle">
            Describe the outcome you want. The agent plans, acts, verifies and
            shows its evidence.
          </p>
        </div>

        <span className="health">
          <span
            className={`dot ${online === null ? "" : online ? "online" : "offline"}`}
          />
          {online === null
            ? "Checking backend…"
            : online
              ? "Backend online"
              : "Backend offline"}
        </span>
      </header>

      <div className="layout">
        <section className="panel sticky">
          <div className="panel-header">
            <h2>Assign a task</h2>
          </div>

          <form onSubmit={handleRunTask}>
            <textarea
              value={task}
              onChange={(event) => setTask(event.target.value)}
              minLength={5}
              maxLength={1000}
              placeholder="e.g. Find the latest invoice from Acme Corp and save it…"
              required
            />

            <div className="examples">
              <p className="examples-label">Try an example</p>
              <div className="chips">
                {EXAMPLES.map((example) => (
                  <button
                    key={example.label}
                    type="button"
                    className="chip"
                    disabled={running}
                    onClick={() => setTask(example.task)}
                  >
                    {example.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="actions">
              <button type="submit" className="button" disabled={running}>
                {running && <span className="spinner" />}
                {running ? "Agent working…" : "Run task"}
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={refreshData}
                disabled={running}
              >
                Refresh data
              </button>
            </div>
          </form>

          {error && <p className="alert">{error}</p>}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Result</h2>
            {result && (
              <span className={`badge badge-${result.status}`}>
                {STATUS_ICONS[result.status]}{" "}
                {STATUS_LABELS[result.status] || result.status}
              </span>
            )}
          </div>

          {!result && running && (
            <div className="empty">
              <div className="working">
                <span className="spinner" />
                <strong>The agent is working on your task…</strong>
              </div>
              <p>A local model can take up to a minute.</p>
            </div>
          )}

          {!result && !running && (
            <div className="empty">
              <strong>No task run yet</strong>
              <p>Pick an example or write your own task, then press Run task.</p>
            </div>
          )}

          {result && (
            <>
              <p className="reason">{result.reason}</p>

              <p
                className={`answer ${
                  result.status === "needs_clarification" ? "question" : ""
                }`}
              >
                {result.answer}
              </p>

              {result.status === "needs_clarification" && (
                <form className="reply-form" onSubmit={handleReply}>
                  <input
                    value={reply}
                    onChange={(event) => setReply(event.target.value)}
                    placeholder="Answer the agent's question…"
                    maxLength={1000}
                    autoFocus
                    required
                  />
                  <button type="submit" className="button" disabled={running}>
                    {running && <span className="spinner" />}
                    {running ? "Continuing…" : "Send reply"}
                  </button>
                </form>
              )}

              <div className="meta">
                <div className="meta-item">
                  <p className="meta-label">Model</p>
                  <p className="meta-value">{result.model || "—"}</p>
                </div>
                <div className="meta-item">
                  <p className="meta-label">Tool calls</p>
                  <p className="meta-value">{stepCount}</p>
                </div>
                <div className="meta-item">
                  <p className="meta-label">Task type</p>
                  <p className="meta-value">
                    {result.requires_save ? "Save & verify" : "Read only"}
                  </p>
                </div>
                <div className="meta-item">
                  <p className="meta-label">Verified</p>
                  <p className="meta-value">
                    {result.verified_invoice_ids?.join(", ") || "—"}
                  </p>
                </div>
              </div>

              <h3>What the agent did</h3>
              <Timeline trace={result.tool_trace} />

              <h3>Verification evidence</h3>
              <Verification verification={result.verification} />
            </>
          )}
        </section>
      </div>

      <div className="tables">
        <section className="panel">
          <div className="panel-header">
            <h2>Source invoices</h2>
            <span className="count">{invoices.length}</span>
          </div>

          {invoices.length === 0 ? (
            <p className="muted">No invoices loaded.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Supplier</th>
                    <th>Date</th>
                    <th className="num">Amount</th>
                    <th>Due</th>
                  </tr>
                </thead>
                <tbody>
                  {invoices.map((invoice) => (
                    <tr
                      key={invoice.invoice_id}
                      className={savedIds.has(invoice.invoice_id) ? "saved" : ""}
                    >
                      <td><code>{invoice.invoice_id}</code></td>
                      <td>{invoice.supplier}</td>
                      <td>{invoice.invoice_date}</td>
                      <td className="num">{formatAmount(invoice.amount)}</td>
                      <td>{invoice.due_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>Internal system records</h2>
            <span className="count">{records.length}</span>
          </div>

          {records.length === 0 ? (
            <p className="muted">No records saved yet.</p>
          ) : (
            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th>Invoice</th>
                    <th>Supplier</th>
                    <th className="num">Amount</th>
                    <th>Due</th>
                    <th>Saved at</th>
                  </tr>
                </thead>
                <tbody>
                  {records.map((record) => (
                    <tr key={record.record_id}>
                      <td><code>{record.invoice_id}</code></td>
                      <td>{record.supplier}</td>
                      <td className="num">{formatAmount(record.amount)}</td>
                      <td>{record.due_date}</td>
                      <td>{new Date(record.created_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
