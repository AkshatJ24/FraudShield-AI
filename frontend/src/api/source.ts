import { config } from '../config';
import { api } from './client';
import { mockEvent } from './mock';
import type { Health, Metrics, SimStatus, StreamEvent } from './types';

export type StreamStatus = 'open' | 'reconnecting';

/** Everything the startup pipeline and stream controls need. Live and mock implement the same shape. */
export interface DataSource {
  /** `onWait` reports progress while a sleeping server wakes up. */
  checkApi(onWait?: (note: string) => void): Promise<string>;
  checkModel(): Promise<string>;
  checkDb(): Promise<string>;
  /** Resolves once the stream is open; returns a close function. */
  connect(onEvent: (e: StreamEvent) => void, onStatus: (s: StreamStatus) => void): Promise<() => void>;
  /** Starts, or resumes where stop() left off. */
  start(): Promise<void>;
  stop(): Promise<void>;
  /** Rewinds the replay to the first row. */
  reset(): Promise<void>;
  status(): Promise<SimStatus>;
  metrics(): Promise<Metrics>;
}

/** Free hosts put the API to sleep when idle; waking it and loading the model can take a few minutes. */
const WAKE_TIMEOUT_MS = 180_000;
const WAKE_RETRY_MS = 5_000;
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function createLiveSource(): DataSource {
  let health: Health | null = null;
  return {
    async checkApi(onWait) {
      const t0 = Date.now();
      for (;;) {
        try {
          health = await api.health(20_000);
          break;
        } catch (e) {
          // Not reachable yet, a proxy's error page, or a timeout: keep trying until the deadline.
          const waited = Date.now() - t0;
          if (waited + WAKE_RETRY_MS > WAKE_TIMEOUT_MS) throw e;
          onWait?.(`The server is waking up. This can take a minute or two (${Math.round(waited / 1000)} s)…`);
          await sleep(WAKE_RETRY_MS);
        }
      }
      if (health.status === 'down') throw new Error('GET /health reports status "down"');
      return 'GET /health · ok';
    },
    async checkModel() {
      if (!health?.model_loaded) throw new Error('The model is not loaded yet. Check the API logs.');
      return `${health.n_trees.toLocaleString()} trees`;
    },
    async checkDb() {
      const db = await api.dbHealth().catch((e: unknown) => {
        if (e instanceof Error && e.message.endsWith('503')) throw new Error('GET /health/db: PostgreSQL is unreachable. Is `docker compose up -d db` running?');
        throw e;
      });
      return db.latency_ms != null ? `${Math.round(db.latency_ms)} ms` : 'connected';
    },
    connect(onEvent, onStatus) {
      return new Promise((resolve, reject) => {
        const es = new EventSource(api.streamUrl);
        let opened = false;
        es.onopen = () => {
          onStatus('open');
          if (!opened) {
            opened = true;
            resolve(() => es.close());
          }
        };
        es.onmessage = (m) => {
          try {
            onEvent(JSON.parse(m.data) as StreamEvent);
          } catch {
            // ignore malformed payloads
          }
        };
        es.onerror = () => {
          if (!opened) {
            es.close();
            reject(new Error(`Could not open ${api.streamUrl.replace(config.apiBase, '')}`));
          } else {
            onStatus('reconnecting'); // EventSource retries on its own
          }
        };
      });
    },
    async start() {
      await api.startSimulator();
    },
    async stop() {
      await api.stopSimulator();
    },
    async reset() {
      await api.resetSimulator();
    },
    status: api.simulatorStatus,
    metrics: api.metrics,
  };
}

/** Rough size of the downsampled holdout replay, so the mock progress reads like the real one. */
const MOCK_TOTAL = 61660;

function createMockSource(): DataSource {
  let active = false;
  let position = 0;
  let timer: number | undefined;
  let emit: ((e: StreamEvent) => void) | null = null;
  const loop = () => {
    if (active && emit) {
      emit(mockEvent());
      position = (position + 1) % MOCK_TOTAL;
    }
    const gap = config.mockRate === 'demo' ? 350 + Math.random() * 850 : 500 + Math.random() * 1500;
    timer = window.setTimeout(loop, gap);
  };
  return {
    checkApi: async () => 'GET /health · ok',
    checkModel: async () => `${config.model.trees.toLocaleString()} trees`,
    checkDb: async () => 'connected',
    async connect(onEvent, onStatus) {
      emit = onEvent;
      onStatus('open');
      window.clearTimeout(timer);
      timer = window.setTimeout(loop, 250);
      return () => {
        window.clearTimeout(timer);
        emit = null;
      };
    },
    async start() {
      active = true;
    },
    async stop() {
      active = false;
    },
    async reset() {
      position = 0;
    },
    status: async () => ({ running: active, position, total: MOCK_TOTAL, warmed_up: true, loading: false }),
    // Offline sections are a snapshot of ml/artifacts taken from GET /metrics; live sections start empty.
    metrics: async () => (await import('./metricsSnapshot.json')).default as unknown as Metrics,
  };
}

export const createDataSource = (): DataSource => (config.dataSource === 'mock' ? createMockSource() : createLiveSource());
