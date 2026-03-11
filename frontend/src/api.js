import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 30000,
});

// Watchlist
export const getStocks = () => api.get("/api/stocks").then((r) => r.data);
export const addStock = (symbol, name, sector = "Other") =>
  api.post("/api/stocks", { symbol, name, sector }).then((r) => r.data);
export const removeStock = (symbol) =>
  api.delete(`/api/stocks/${symbol}`).then((r) => r.data);

// Trash & Restore
export const getDeletedStocks = () =>
  api.get("/api/stocks/deleted").then((r) => r.data);
export const restoreStock = (symbol) =>
  api.post(`/api/stocks/${symbol}/restore`).then((r) => r.data);
export const purgeStock = (symbol) =>
  api.delete(`/api/stocks/${symbol}/purge`).then((r) => r.data);

// Dashboard & Analysis
export const getDashboard = () => api.get("/api/dashboard").then((r) => r.data);
export const analyzeStock = (symbol) =>
  api.get(`/api/analyze/${symbol}`).then((r) => r.data);

// Scheduler
export const getSchedulerStatus = () =>
  api.get("/api/scheduler/status").then((r) => r.data);
export const forceRefresh = (symbol) =>
  api.post(`/api/scheduler/refresh/${symbol}`).then((r) => r.data);

// Settings / Config
export const getConfig = () => api.get("/api/config").then((r) => r.data);
export const updateConfig = (key, value) =>
  api.put(`/api/config/${key}`, { value }).then((r) => r.data);

// Logs
export const getLogs = (limit = 200) =>
  api.get(`/api/logs?limit=${limit}`).then((r) => r.data);

export default api;
