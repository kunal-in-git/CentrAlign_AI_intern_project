
import { useEffect, useState } from "react";
import { getRecords, runTask } from "./api";
import "./App.css";

const DEFAULT_TASK =
  "Find the latest invoice from Acme Corp, read its amount and due date, " +
  "save it in the internal system, and verify that it was saved correctly.";

export default function App() {
  const [task, setTask] = useState(DEFAULT_TASK);
  const [status, setStatus] = useState("Ready");
  const [result, setResult] = useState(null);
  const [records, setRecords] = useState([]);
  const [error, setError] = useState("");

  async function refreshRecords() {
    try {
      const data = await getRecords();
      setRecords(data);
    } catch (err) {
      setError(
        err.response?.data?.detail || err.message
      );
    }
  }

  useEffect(() => {
    refreshRecords();
  }, []);

  async function handleRunTask(event) {
    event.preventDefault();

    setStatus("Running");
    setResult(null);
    setError("");

    try {
      const data = await runTask(task.trim());
      setResult(data);

      setStatus(
        data.status === "completed" ? "Completed" : "Not verified"
      );

      await refreshRecords();
    } catch (err) {
      setStatus("Failed");
      setError(
        err.response?.data?.detail ||
        err.message ||
        "Task execution failed."
      );
    }
  }

  return (
    <main className="container">
      <header>
        <p className="eyebrow">CENTRALIGN AI</p>
        <h1>Autonomous Task Worker</h1>
        <p>Give the agent a task. Inspect its actions and evidence.</p>
      </header>

      <section className="panel">
        <h2>Assign a task</h2>

        <form onSubmit={handleRunTask}>
          <textarea
            value={task}
            onChange={(event) => setTask(event.target.value)}
            minLength={5}
            maxLength={1000}
            required
          />

          <div className="actions">
            <button type="submit" disabled={status === "Running"}>
              {status === "Running" ? "Executing..." : "Run task"}
            </button>

            <button
              type="button"
              className="secondary"
              onClick={refreshRecords}
            >
              Refresh records
            </button>
          </div>
        </form>

        <p className="muted">Status: {status}</p>

        {error && <p className="error">{error}</p>}
      </section>

      <section className="panel">
        <h2>Agent response</h2>

        {!result ? (
          <p className="muted">Run a task to see the result.</p>
        ) : (
          <>
            <p className="result-text">{result.answer}</p>
            <p>
              Model: {result.model || "Not reported"}
            </p>

            <h3>Verified invoice IDs</h3>
            <p>
              {result.verified_invoice_ids?.join(", ") || "None"}
            </p>

            <h3>Execution trace</h3>
            <pre>
              {JSON.stringify(result.tool_trace || [], null, 2)}
            </pre>

            <h3>Verification evidence</h3>
            <pre>
              {JSON.stringify(result.verification || {}, null, 2)}
            </pre>
          </>
        )}
      </section>

      <section className="panel">
        <h2>Internal system records</h2>

        {records.length === 0 ? (
          <p className="muted">No records saved yet.</p>
        ) : (
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>Invoice ID</th>
                  <th>Supplier</th>
                  <th>Amount</th>
                  <th>Due date</th>
                </tr>
              </thead>

              <tbody>
                {records.map((record) => (
                  <tr key={record.record_id}>
                    <td>{record.invoice_id}</td>
                    <td>{record.supplier}</td>
                    <td>{Number(record.amount).toFixed(2)}</td>
                    <td>{record.due_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
