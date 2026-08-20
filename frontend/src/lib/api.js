import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 120000 });

export const SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];

export const SEV_COLOR = {
  CRITICAL: "#ff3b30",
  HIGH: "#ff7a1a",
  MEDIUM: "#ffcc00",
  LOW: "#007aff",
  INFO: "#6b7280",
};

export const STATUS_COLOR = {
  QUEUED: "#6b7280",
  RUNNING: "#007aff",
  COMPLETED: "#34c759",
  FAILED_VALIDATION: "#ff3b30",
  ERROR: "#ff3b30",
};

export const NODE_COLOR = {
  PENDING: "#6b7280",
  RUNNING: "#007aff",
  SUCCESS: "#34c759",
  FAILED: "#ff3b30",
  SKIPPED: "#3d3d3d",
};

export const fmtMs = (ms) => {
  if (!ms && ms !== 0) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

export const fmtUsd = (v) => `$${Number(v || 0).toFixed(4)}`;

export const fmtTime = (iso) => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
};

export const relTime = (iso) => {
  if (!iso) return "—";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
