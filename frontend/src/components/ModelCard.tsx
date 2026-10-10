import { config } from '../config';
import { useFraudShield } from '../state/FraudShield';
import { pct } from '../lib/format';

export function ModelCard() {
  const { metrics, thresholds } = useFraudShield();
  const { review, block } = thresholds;
  // Until GET /metrics answers, fall back to the tracker numbers in config.ts.
  const h = metrics?.holdout_natural_rate;
  const m = config.model;
  const fixed = (v: number | undefined, fallback: string) => (v == null ? fallback : v.toFixed(4));
  const share = (v: number | undefined, fallback: string) => (v == null ? fallback : pct(v, 2));
  const metricsRows = [
    ['PR-AUC', fixed(h?.pr_auc, m.prAuc)],
    ['ROC-AUC', fixed(h?.roc_auc, m.rocAuc)],
    ['Recall @ 1% FPR', share(h?.recall_at_1_fpr, m.recallAt1Fpr)],
    ['Precision', share(h?.precision, m.precision)],
  ];
  const trees = metrics?.model.n_trees ?? m.trees;
  return (
    <section className="fs-card flex min-w-0 flex-[1_1_320px] flex-col gap-4 px-6 py-[22px]">
      <div className="flex flex-col gap-1">
        <h2 className="text-[22px] font-bold tracking-[-.01em]">Model</h2>
        <p className="text-sm text-muted2">{m.name}</p>
      </div>
      <div className="grid grid-cols-2 gap-3">
        {metricsRows.map(([label, value]) => (
          <div key={label} className="rounded-2xl bg-bg px-4 py-3.5">
            <div className="text-xs font-medium text-muted2">{label}</div>
            <div className="text-[22px] font-bold">{value}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3 rounded-2xl bg-hero-grad p-4 text-white">
        <div>
          <div className="text-xs opacity-85">Cost saved vs. no model</div>
          <div className="text-[26px] font-bold">{metrics?.cost.savings_pct != null ? pct(metrics.cost.savings_pct) : m.costSaved}</div>
        </div>
        <div className="text-right text-xs leading-normal opacity-85">
          {/* Average costs from the Phase 4 notebook (not in the artifacts). */}
          {m.missedFraudCost} missed fraud
          <br />
          {m.falseAlertCost} false alert
        </div>
      </div>
      <div className="flex flex-wrap gap-2">
        <span className="rounded-full px-3 py-1.5 text-xs font-bold" style={{ background: 'var(--review-bg)', color: 'var(--review-fg)' }}>
          Review ≥ {review}
        </span>
        <span className="rounded-full px-3 py-1.5 text-xs font-bold" style={{ background: 'var(--block-bg)', color: 'var(--block-fg)' }}>
          Block ≥ {block}
        </span>
        <span className="rounded-full bg-bg px-3 py-1.5 text-xs font-medium text-muted2">{trees.toLocaleString()} trees</span>
      </div>
    </section>
  );
}
