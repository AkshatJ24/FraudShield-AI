export type Decision = 'APPROVE' | 'REVIEW' | 'BLOCK';

/** Mirrors backend/app/schemas/score.py → Reason */
export interface Reason {
  text: string;
  contribution: number;
  kind: 'specific' | 'anonymized' | 'fallback';
}

/** Mirrors backend/app/schemas/score.py → ScoreResponse */
export interface ScoreResponse {
  transaction_id: string;
  score: number;
  decision: Decision;
  reasons: Reason[];
  calibrated_prob: number;
  raw_score: number;
  latency_ms: number;
  what_if: boolean;
}

/** Request fields the UI displays, added to each stream event by backend/app/api/stream.py. */
export interface RequestFields {
  TransactionAmt?: number | null;
  ProductCD?: string | null;
  card1?: number | null;
  card4?: string | null;
  card6?: string | null;
  P_emaildomain?: string | null;
  DeviceType?: string | null;
}

export const REQUEST_KEYS = ['TransactionAmt', 'ProductCD', 'card1', 'card4', 'card6', 'P_emaildomain', 'DeviceType'] as const;

/** One `data:` payload from GET /api/v1/stream */
export interface StreamEvent extends ScoreResponse, RequestFields {
  true_label?: boolean | null;
  /** Server epoch ms (added by the backend patch). */
  scored_at?: number;
}

/** A stream event plus the client receipt time, which drives the radar and row flash. */
export interface Tx extends StreamEvent {
  ts: number;
}

/** Mirrors backend/app/schemas/score.py → HealthResponse */
export interface Health {
  status: 'ok' | 'degraded' | 'down';
  model_loaded: boolean;
  model_version: string;
  n_trees: number;
  n_features: number;
  card_store_size: number;
}

/** GET /health/db */
export interface DbHealth {
  status: 'ok' | 'down';
  latency_ms: number | null;
  server_version: string | null;
  error: string | null;
}

/** GET /api/v1/simulate/status. `total` is null until the replay set has loaded. */
export interface SimStatus {
  running: boolean;
  position: number;
  total: number | null;
  warmed_up: boolean;
  loading: boolean;
}

/** One point on the flag-rate sweep in ml/artifacts/cost_curve.json. */
export interface CurvePoint {
  flagged_share: number;
  threshold: number | null;
  risk_score: number | null;
  recall: number;
  precision: number | null;
  cost: number;
  savings: number;
}

export interface Band {
  count: number;
  share: number;
  fraud_rate: number;
  fraud_caught: number;
}

/** GET /api/v1/metrics (backend/app/api/metrics.py) */
export interface Metrics {
  live_demo_stream: {
    total_transactions: number;
    decision_counts: Record<Decision, number>;
    p50_latency_ms: number;
    p95_latency_ms: number;
    p99_latency_ms: number;
    review_queue_size: number;
    analyst_reviewed: number;
    analyst_confirmed_precision: number;
    first_at: string | null;
    last_at: string | null;
    ground_truth: {
      labelled: number;
      fraud: number;
      flagged_true_positive: number;
      flagged_false_positive: number;
      precision_flagged: number | null;
      recall_flagged: number | null;
      precision_block: number | null;
      recall_block: number | null;
    };
  };
  holdout_natural_rate: {
    n?: number;
    fraud_rate?: number;
    pr_auc?: number;
    roc_auc?: number;
    recall_at_1_fpr?: number;
    precision_at_1_fpr?: number;
    fpr_target?: number;
    precision?: number;
    recall?: number;
    fpr?: number;
    calibration?: { brier?: number; log_loss?: number; ece?: number; mean_pred?: number; observed_rate?: number };
    baseline_logreg?: { pr_auc?: number; roc_auc?: number; recall_at_1_fpr?: number };
  };
  bands: Partial<Record<Decision, Band>>;
  cost: {
    model: Record<string, number>;
    savings?: number;
    savings_pct?: number;
    savings_pct_90ci?: [number, number];
    savings_per_100k_txns?: number;
    cost_total?: number;
    cost_approve_all?: number;
    breakdown: { missed_fraud_cost?: number; blocked_legit_cost?: number; review_cost_total?: number };
    recall_review_or_block?: number;
    recall_block_only?: number;
    strategies: { name: string; cost: number; savings_pct: number }[];
  };
  curves: { validation: CurvePoint[]; holdout: CurvePoint[] };
  thresholds: {
    review_risk_score?: number;
    block_risk_score?: number;
    review_capacity_cap?: number;
    review_raw?: number;
    block_raw?: number;
  };
  top_features: { feature: string; mean_abs_shap: number }[];
  model: {
    version?: string;
    trained_at_utc?: string;
    model_type?: string;
    calibration_method?: string;
    n_trees?: number;
    n_features?: number;
    validation: { pr_auc?: number; roc_auc?: number; recall_at_fpr?: number };
  };
}
