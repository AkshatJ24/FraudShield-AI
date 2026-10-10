import { config } from '../config';
import type { DbHealth, Health, Metrics, SimStatus } from './types';

const root = (path: string) => config.apiBase + path;
const v1 = (path: string) => root(config.apiPrefix + path);

async function request<T>(url: string, init?: RequestInit, timeoutMs?: number): Promise<T> {
  const signal = timeoutMs ? AbortSignal.timeout(timeoutMs) : undefined;
  const res = await fetch(url, { signal, ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!res.ok) throw new Error(`${init?.method ?? 'GET'} ${url.replace(config.apiBase, '')} returned ${res.status}`);
  return res.json() as Promise<T>;
}

export const api = {
  /** GET /health (unversioned) */
  health: (timeoutMs?: number) => request<Health>(root('/health'), undefined, timeoutMs),
  /** GET /health/db — SELECT 1 against PostgreSQL; 503 when it's unreachable. */
  dbHealth: () => request<DbHealth>(root('/health/db')),
  metrics: () => request<Metrics>(v1('/metrics')),
  simulatorStatus: () => request<SimStatus>(v1('/simulate/status')),
  /** Starts, or resumes from where /stop left off. */
  startSimulator: () => request<SimStatus & { message: string }>(v1('/simulate/start'), { method: 'POST' }),
  /** Pauses; the replay position is kept. */
  stopSimulator: () => request<SimStatus & { message: string }>(v1('/simulate/stop'), { method: 'POST' }),
  /** Rewinds the replay to the first row. */
  resetSimulator: () => request<SimStatus & { message: string }>(v1('/simulate/reset'), { method: 'POST' }),
  streamUrl: v1('/stream'),
};
