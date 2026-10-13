
import axios from "axios";

const api = axios.create({
  baseURL: "/api",
  timeout: 180000,
  headers: {
    "Content-Type": "application/json",
  },
});

export async function runTask(task) {
  const response = await api.post("/run-task", { task });
  return response.data;
}

export async function getRecords() {
  const response = await api.get("/records");
  return response.data.records;
}

export async function getInvoices() {
  const response = await api.get("/invoices");
  return response.data.invoices;
}

export default api;
