
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 600000,
  headers: {
    "Content-Type": "application/json",
  },
});

export async function runTask(task) {
  const response = await api.post("/run-task", { task });
  return response.data;
}

export async function replyToRun(runId, reply) {
  const response = await api.post(`/runs/${runId}/reply`, { reply });
  return response.data;
}

export async function getRecords() {
  const response = await api.get("/records");
  return response.data.records;
}

export async function getHealth() {
  const response = await api.get("/health", { timeout: 5000 });
  return response.data;
}

export async function getInvoices() {
  const response = await api.get("/invoices");
  return response.data.invoices;
}

export default api;
