import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useToast } from '@chakra-ui/react';
import { config } from '../config';
import { createDataSource, type StreamStatus } from '../api/source';
import type { Metrics, SimStatus, StreamEvent, Tx } from '../api/types';

export type Phase = 'start' | 'leaving' | 'boot' | 'app';
export interface BootError {
  step: number;
  message: string;
}

interface FraudShieldState {
  phase: Phase;
  start: () => void;
  bootStep: number;
  bootDetails: string[];
  bootError: BootError | null;
  retryBoot: () => void;
  txs: Tx[];
  /** When the stream started; the radar sweep and dot angles are measured from here. */
  t0: number;
  streamStatus: StreamStatus;
  running: boolean;
  toggleRun: () => void;
  truth: boolean;
  toggleTruth: () => void;
  selected: Tx | null;
  select: (id: string | null) => void;
  stackIdx: number;
  setStackIdx: (i: number) => void;
  /** GET /metrics; null until the first response. Refreshed every METRICS_MS while in the app. */
  metrics: Metrics | null;
  metricsError: string | null;
  refreshMetrics: () => void;
  /** Replay progress from GET /simulate/status. */
  sim: SimStatus | null;
  /** Rewinds the holdout replay to the first row (keeps running / paused as it was). */
  restartReplay: () => void;
  /** Review / Block cut-offs on the 0–100 score, from the API when available. */
  thresholds: { review: number; block: number };
}

const METRICS_MS = 10000;
const STATUS_MS = 4000;

const Ctx = createContext<FraudShieldState | null>(null);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export const errorMessage = (e: unknown) =>
  e instanceof TypeError ? `Can't reach the API at ${config.apiBase}` : e instanceof Error ? e.message : String(e);

export function FraudShieldProvider({ children }: { children: ReactNode }) {
  const source = useMemo(createDataSource, []);
  const toast = useToast();
  const [phase, setPhase] = useState<Phase>('start');
  const [bootStep, setBootStep] = useState(0);
  const [bootDetails, setBootDetails] = useState<string[]>([]);
  const [bootError, setBootError] = useState<BootError | null>(null);
  const [txs, setTxs] = useState<Tx[]>([]);
  const [t0, setT0] = useState(() => Date.now());
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('open');
  const [running, setRunning] = useState(true);
  const [truth, setTruth] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [stackIdx, setStackIdx] = useState(0);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [metricsError, setMetricsError] = useState<string | null>(null);
  const [sim, setSim] = useState<SimStatus | null>(null);
  const closeStream = useRef<(() => void) | null>(null);

  useEffect(() => () => closeStream.current?.(), []);

  const push = useCallback((ev: StreamEvent) => {
    const tx: Tx = { ...ev, ts: Date.now() };
    setTxs((prev) => [tx, ...prev].slice(0, config.maxTx));
    // Keep the card the user is looking at in place when a new flagged one lands on top.
    if (tx.decision !== 'APPROVE') setStackIdx((i) => (i > 0 ? i + 1 : i));
  }, []);

  const runBoot = useCallback(async () => {
    setBootError(null);
    setBootStep(0);
    setBootDetails([]);
    const steps: (() => Promise<string>)[] = [
      source.checkApi,
      source.checkModel,
      source.checkDb,
      async () => {
        closeStream.current?.();
        closeStream.current = await source.connect(push, setStreamStatus);
        await source.start();
        return 'streaming';
      },
    ];
    for (let i = 0; i < steps.length; i++) {
      try {
        const [detail] = await Promise.all([steps[i](), sleep(config.minStepMs)]);
        setBootDetails((d) => {
          const n = [...d];
          n[i] = detail;
          return n;
        });
        setBootStep(i + 1);
      } catch (e) {
        setBootError({ step: i, message: errorMessage(e) });
        return;
      }
    }
    await sleep(600);
    setT0(Date.now());
    setRunning(true);
    setPhase('app');
  }, [source, push]);

  const start = useCallback(() => {
    if (phase !== 'start') return;
    setPhase('leaving');
    setTimeout(() => {
      setPhase('boot');
      void runBoot();
    }, 420);
  }, [phase, runBoot]);

  const refreshMetrics = useCallback(async () => {
    try {
      setMetrics(await source.metrics());
      setMetricsError(null);
    } catch (e) {
      setMetricsError(errorMessage(e));
    }
  }, [source]);

  const refreshStatus = useCallback(async () => {
    try {
      setSim(await source.status());
    } catch {
      // keep the last known progress; the header already shows stream trouble
    }
  }, [source]);

  useEffect(() => {
    if (phase !== 'app') return;
    void refreshMetrics();
    void refreshStatus();
    const m = setInterval(() => void refreshMetrics(), METRICS_MS);
    const s = setInterval(() => void refreshStatus(), STATUS_MS);
    return () => {
      clearInterval(m);
      clearInterval(s);
    };
  }, [phase, refreshMetrics, refreshStatus]);

  const toggleRun = useCallback(async () => {
    if (phase !== 'app') return;
    const next = !running;
    setRunning(next);
    try {
      await (next ? source.start() : source.stop());
      void refreshStatus();
    } catch (e) {
      setRunning(!next);
      toast({ status: 'error', title: next ? 'Could not resume the simulator' : 'Could not pause the simulator', description: errorMessage(e), position: 'bottom-right' });
    }
  }, [phase, running, source, toast, refreshStatus]);

  const restartReplay = useCallback(async () => {
    try {
      await source.reset();
      await refreshStatus();
      toast({ status: 'info', title: 'Replay rewound', description: 'The simulator continues from the first holdout transaction.', position: 'bottom-right' });
    } catch (e) {
      toast({ status: 'error', title: 'Could not rewind the replay', description: errorMessage(e), position: 'bottom-right' });
    }
  }, [source, refreshStatus, toast]);

  const thresholds = useMemo(
    () => ({
      review: metrics?.thresholds.review_risk_score ?? config.thresholds.review,
      block: metrics?.thresholds.block_risk_score ?? config.thresholds.block,
    }),
    [metrics],
  );

  const selected = useMemo(() => (selectedId ? txs.find((t) => t.transaction_id === selectedId) ?? null : null), [selectedId, txs]);

  const value: FraudShieldState = {
    phase,
    start,
    bootStep,
    bootDetails,
    bootError,
    retryBoot: () => void runBoot(),
    txs,
    t0,
    streamStatus,
    running,
    toggleRun: () => void toggleRun(),
    truth,
    toggleTruth: () => setTruth((t) => !t),
    selected,
    select: setSelectedId,
    stackIdx,
    setStackIdx,
    metrics,
    metricsError,
    refreshMetrics: () => void refreshMetrics(),
    sim,
    restartReplay: () => void restartReplay(),
    thresholds,
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useFraudShield() {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('useFraudShield must be used inside <FraudShieldProvider>');
  return ctx;
}

/** Re-renders every `ms` so ages, fades and the tx/s rate stay current. */
export function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(t);
  }, [ms]);
  return now;
}
