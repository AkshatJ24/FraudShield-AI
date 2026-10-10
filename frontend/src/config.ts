const env = import.meta.env;

export const config = {
  apiBase: (env.VITE_API_URL ?? 'http://localhost:8000').replace(/\/$/, ''),
  apiPrefix: env.VITE_API_PREFIX ?? '/api/v1',
  dataSource: (env.VITE_DATA_SOURCE === 'mock' ? 'mock' : 'live') as 'live' | 'mock',
  decisionColors: (env.VITE_DECISION_COLORS === 'semantic' ? 'semantic' : 'blue') as 'blue' | 'semantic',
  mockRate: (env.VITE_MOCK_RATE === 'realistic' ? 'realistic' : 'demo') as 'demo' | 'realistic',
  repoUrl: 'https://github.com/AkshatJ24/FraudShield-AI',
  /** Fallback until GET /metrics answers (then thresholds.json via the API wins). Review ≥ 5, Block ≥ 16 on the 0–100 score. */
  thresholds: { review: 5, block: 16 },
  /** Fallback holdout metrics for the Model card until GET /metrics answers. The cost averages are only here. */
  model: {
    name: 'LightGBM · Platt-calibrated · time-based holdout',
    prAuc: '0.5633',
    rocAuc: '0.9083',
    recallAt1Fpr: '48.26%',
    precision: '55.83%',
    costSaved: '59.4%',
    missedFraudCost: '$178',
    falseAlertCost: '$16',
    trees: 2316,
  },
  /** Transactions kept in memory. */
  maxTx: 400,
  /** Minimum time each startup step stays on screen, so the pipeline reads. */
  minStepMs: 850,
};
