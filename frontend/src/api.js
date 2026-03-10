import axios from "axios";

const api = axios.create({
  baseURL: "http://localhost:8000",
  timeout: 30000,
});

export const getStocks = () => api.get("/api/stocks").then((r) => r.data);
export const addStock = (symbol, name) =>
  api.post("/api/stocks", { symbol, name }).then((r) => r.data);
export const removeStock = (symbol) =>
  api.delete(`/api/stocks/${symbol}`).then((r) => r.data);
export const getDashboard = () => api.get("/api/dashboard").then((r) => r.data);
export const analyzeStock = (symbol) =>
  api.get(`/api/analyze/${symbol}`).then((r) => r.data);
export const getSchedulerStatus = () =>
  api.get("/api/scheduler/status").then((r) => r.data);
export const forceRefresh = (symbol) =>
  api.post(`/api/scheduler/refresh/${symbol}`).then((r) => r.data);

export default api;
