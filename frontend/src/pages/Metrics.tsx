import { useEffect, useMemo, useState } from 'react';
import { CircleDollarSign, Crosshair, Gauge, Scale, Target, type LucideIcon } from 'lucide-react';
import type { Decision, Metrics } from '../api/types';
import { useFraudShield } from '../state/FraudShield';
import { CardTitle } from '../components/ui';
import { HBar, Legend, LineChart, type Marker } from '../components/charts';
import { decisionTokens, pct, usd } from '../lib/format';

const DECISIONS: Decision[] = ['APPROVE', 'REVIEW', 'BLOCK'];
const ticks = (max: number, step: number) => Array.from({ length: Math.round(max / step) + 1 }, (_, i) => +(i * step).toFixed(4));
const ms = (v: number) => `${Math.round(v).toLocaleString()} ms`;

export function MetricsPage() {
  const { metrics, metricsError, refreshMetrics } = useFraudShield();

  if (!metrics) {
    return (
      <div className="fs-card flex animate-fade-up flex-col items-center gap-4 px-6 py-16 text-center">
        {metricsError ? (
          <>
            <div className="text-lg font-bold">Couldn't load metrics</div>
            <div className="max-w-[460px] text-sm text-muted2">{metricsError}</div>
            <button type="button" onClick={refreshMetrics} className="h-[42px] cursor-pointer rounded-full bg-brand-grad px-5 text-sm font-bold text-white">
              Retry
            </button>
          </>
        ) : (
          <div className="flex items-center gap-2.5 text-[15px] text-muted">
            <span className="h-2 w-2 animate-blink rounded-full bg-brand" />
            Loading GET /metrics…
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="flex animate-fade-up flex-col gap-5">
      <Headline m={metrics} />
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 460px), 1fr))' }}>
        <PrCurveCard m={metrics} />
        <CostSliderCard m={metrics} />
      </div>
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 460px), 1fr))' }}>
        <BandsCard m={metrics} />
        <CostCard m={metrics} />
      </div>
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 460px), 1fr))' }}>
        <LiveCard m={metrics} />
        <FeaturesCard m={metrics} />
      </div>
      <p className="text-xs text-muted">
        Offline numbers come from <span className="font-mono">ml/artifacts</span> (time-based holdout, natural {pct(metrics.holdout_natural_rate.fraud_rate)} fraud rate,{' '}
        {metrics.holdout_natural_rate.n?.toLocaleString() ?? '—'} transactions). Model {metrics.model.version ?? '—'}
        {metrics.model.trained_at_utc ? `, trained ${new Date(metrics.model.trained_at_utc).toLocaleString()}` : ''}.
      </p>
    </div>
  );
}

/* ── headline tiles ─────────────────────────────────────────────────────────── */

function Headline({ m }: { m: Metrics }) {
  const h = m.holdout_natural_rate;
  const base = h.baseline_logreg;
  const ci = m.cost.savings_pct_90ci;
  const tiles: { label: string; value: string; sub: string; icon: LucideIcon; accent?: boolean }[] = [
    { label: 'PR-AUC', value: h.pr_auc?.toFixed(4) ?? '—', sub: `LogReg baseline ${base?.pr_auc?.toFixed(4) ?? '—'}`, icon: Target },
    { label: 'ROC-AUC', value: h.roc_auc?.toFixed(4) ?? '—', sub: `LogReg baseline ${base?.roc_auc?.toFixed(4) ?? '—'}`, icon: Gauge },
    { label: `Recall @ ${pct(h.fpr_target ?? 0.01, 0)} FPR`, value: pct(h.recall_at_1_fpr), sub: `precision ${pct(h.precision_at_1_fpr)}`, icon: Crosshair },
    { label: 'Calibration (ECE)', value: h.calibration?.ece?.toFixed(4) ?? '—', sub: `Brier ${h.calibration?.brier?.toFixed(4) ?? '—'}`, icon: Scale },
    {
      label: 'Cost saved',
      value: pct(m.cost.savings_pct),
      sub: ci ? `90% CI ${pct(ci[0])}–${pct(ci[1])}` : `${usd(m.cost.savings)} on holdout`,
      icon: CircleDollarSign,
      accent: true,
    },
  ];
  return (
    <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
      {tiles.map(({ label, value, sub, icon: Icon, accent }) => (
        <div key={label} className="fs-card flex items-center gap-4 px-5 py-[18px]">
          <div className={`flex h-[54px] w-[54px] flex-none items-center justify-center rounded-full ${accent ? 'bg-brand-grad text-white' : 'bg-bg text-brand'}`}>
            <Icon size={24} strokeWidth={2} />
          </div>
          <div className="flex min-w-0 flex-col gap-0.5">
            <div className="text-sm font-medium text-muted">{label}</div>
            <div className="text-2xl font-bold">{value}</div>
            <div className="text-xs text-muted2">{sub}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ── operating points from the decision bands ──────────────────────────────── */

function operatingPoints(m: Metrics) {
  const r = m.bands.REVIEW;
  const b = m.bands.BLOCK;
  if (!r || !b) return null;
  return {
    flagged: {
      share: r.share + b.share,
      recall: m.cost.recall_review_or_block ?? 0,
      precision: (r.fraud_caught + b.fraud_caught) / Math.max(1, r.count + b.count),
    },
    block: { share: b.share, recall: m.cost.recall_block_only ?? 0, precision: b.fraud_rate },
  };
}

/* ── precision–recall ──────────────────────────────────────────────────────── */

function PrCurveCard({ m }: { m: Metrics }) {
  const { thresholds } = useFraudShield();
  const hold = useMemo(() => m.curves.holdout.filter((p) => p.precision != null), [m]);
  const val = useMemo(() => m.curves.validation.filter((p) => p.precision != null), [m]);
  const op = operatingPoints(m);
  const markers: Marker[] = op
    ? [
        { x: op.block.recall, y: op.block.precision, label: `Block ≥ ${thresholds.block}` },
        { x: op.flagged.recall, y: op.flagged.precision, label: `Review ≥ ${thresholds.review}` },
      ]
    : [];
  const series = [
    { key: 'holdout', label: 'Holdout', color: 'var(--brand)', points: hold.map((p) => ({ x: p.recall, y: p.precision! })) },
    { key: 'validation', label: 'Validation', color: 'var(--muted)', dashed: true, points: val.map((p) => ({ x: p.recall, y: p.precision! })) },
  ];
  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle title="Precision vs. recall" subtitle="Flagging the riskiest 0–20% of traffic. Dots mark the shipped thresholds." />
      <Legend items={series.map(({ label, color, dashed }) => ({ label, color, dashed }))} />
      <LineChart
        ariaLabel="Precision against recall on the holdout and validation sets"
        series={series}
        markers={markers}
        x={{ domain: [0, 1], ticks: ticks(1, 0.2), format: (v) => pct(v, 0), label: 'Recall (share of fraud caught)' }}
        y={{ domain: [0, 1], ticks: ticks(1, 0.25), format: (v) => pct(v, 0), label: 'Precision' }}
        tooltip={(i) => {
          const p = hold[i];
          const v = val[i];
          return (
            <div className="flex flex-col gap-1">
              <div className="font-bold">Flag top {pct(p.flagged_share)}</div>
              <Row k="Holdout recall" v={pct(p.recall)} />
              <Row k="Holdout precision" v={pct(p.precision)} />
              {v && <Row k="Validation precision" v={pct(v.precision)} />}
              <Row k="Risk score cut-off" v={p.risk_score != null ? `≥ ${Math.round(p.risk_score)}` : '—'} />
            </div>
          );
        }}
      />
    </section>
  );
}

const Row = ({ k, v }: { k: string; v: string }) => (
  <div className="flex justify-between gap-4">
    <span className="text-muted2">{k}</span>
    <span className="font-mono font-medium">{v}</span>
  </div>
);

/* ── cost vs. threshold slider ─────────────────────────────────────────────── */

function CostSliderCard({ m }: { m: Metrics }) {
  const pts = m.curves.holdout;
  const op = operatingPoints(m);
  const best = useMemo(() => pts.reduce((bi, p, i) => (p.savings > pts[bi].savings ? i : bi), 0), [pts]);
  const nearest = (share: number) => pts.reduce((bi, p, i) => (Math.abs(p.flagged_share - share) < Math.abs(pts[bi].flagged_share - share) ? i : bi), 0);
  const [idx, setIdx] = useState(() => (op ? nearest(op.block.share) : best));
  useEffect(() => setIdx((i) => Math.min(i, pts.length - 1)), [pts.length]);
  if (!pts.length) return null;

  const p = pts[idx];
  const approveAll = pts[0]?.cost ?? 0;
  const maxShare = pts[pts.length - 1].flagged_share;
  const maxSavings = Math.max(...pts.map((q) => q.savings));
  const yMax = Math.ceil(maxSavings / 50000) * 50000 || 1;
  const readout: [string, string][] = [
    ['Risk score cut-off', p.risk_score != null ? `≥ ${Math.round(p.risk_score)}` : '—'],
    ['Recall', pct(p.recall)],
    ['Precision', pct(p.precision)],
    ['Total cost', usd(p.cost)],
    ['Saved vs. approve all', `${usd(p.savings)} · ${pct(approveAll ? p.savings / approveAll : null)}`],
  ];

  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle
        title="Cost vs. threshold"
        subtitle="One cut-off, everything above it blocked. Drag to trade missed fraud against false blocks."
        right={
          <button type="button" onClick={() => setIdx(best)} className="h-8 cursor-pointer whitespace-nowrap rounded-full bg-bg px-3.5 text-[13px] font-bold text-brand">
            Cheapest point
          </button>
        }
      />
      <LineChart
        ariaLabel="Savings against the share of traffic flagged, holdout set"
        height={220}
        series={[{ key: 'savings', label: 'Savings', color: 'var(--brand)', points: pts.map((q) => ({ x: q.flagged_share, y: q.savings })) }]}
        pinX={p.flagged_share}
        markers={[{ x: pts[best].flagged_share, y: pts[best].savings, label: 'Cheapest' }]}
        x={{ domain: [0, maxShare], ticks: ticks(maxShare, 0.05), format: (v) => pct(v, 0), label: 'Share of traffic flagged' }}
        y={{ domain: [0, yMax], ticks: ticks(yMax, yMax / 4), format: (v) => usd(v, true), label: 'Saved' }}
        tooltip={(i) => (
          <div className="flex flex-col gap-1">
            <div className="font-bold">Flag top {pct(pts[i].flagged_share)}</div>
            <Row k="Saved" v={usd(pts[i].savings)} />
            <Row k="Recall" v={pct(pts[i].recall)} />
          </div>
        )}
      />
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-sm">
          <label htmlFor="fs-threshold" className="font-medium text-muted2">
            Flag the riskiest
          </label>
          <span className="font-bold">{pct(p.flagged_share)} of traffic</span>
        </div>
        <input
          id="fs-threshold"
          type="range"
          min={0}
          max={pts.length - 1}
          step={1}
          value={idx}
          onChange={(e) => setIdx(Number(e.target.value))}
          className="w-full cursor-pointer accent-[var(--brand)]"
          aria-valuetext={`${pct(p.flagged_share)} flagged, recall ${pct(p.recall)}, saves ${usd(p.savings)}`}
        />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {readout.map(([k, v]) => (
          <div key={k} className="rounded-2xl bg-bg px-4 py-3">
            <div className="text-xs font-medium text-muted2">{k}</div>
            <div className="text-[17px] font-bold">{v}</div>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ── decision bands ────────────────────────────────────────────────────────── */

function BandsCard({ m }: { m: Metrics }) {
  const { thresholds } = useFraudShield();
  const totalFraud = DECISIONS.reduce((s, d) => s + (m.bands[d]?.fraud_caught ?? 0), 0);
  const range: Record<Decision, string> = {
    APPROVE: `score 0–${thresholds.review - 1}`,
    REVIEW: `score ${thresholds.review}–${thresholds.block - 1}`,
    BLOCK: `score ≥ ${thresholds.block}`,
  };
  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle title="Decision bands" subtitle="How the two thresholds split the holdout set" />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-sm">
          <thead>
            <tr className="text-left text-[13px] text-muted">
              {['Decision', 'Traffic', 'Fraud rate', 'Fraud in band'].map((h) => (
                <th key={h} className={`border-b border-line pb-2.5 font-medium ${h === 'Decision' ? '' : 'text-right'}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {DECISIONS.map((d) => {
              const b = m.bands[d];
              const t = decisionTokens(d);
              return (
                <tr key={d} className="border-b border-line">
                  <td className="py-3">
                    <span className="inline-flex rounded-full px-2.5 py-1 text-xs font-bold" style={{ background: t.bg, color: t.fg }}>
                      {t.label}
                    </span>
                    <span className="ml-2 text-xs text-muted">{range[d]}</span>
                  </td>
                  <td className="py-3 text-right">
                    <div className="font-bold">{pct(b?.share)}</div>
                    <div className="text-xs text-muted2">{b?.count.toLocaleString() ?? '—'}</div>
                  </td>
                  <td className="py-3 text-right font-bold">{pct(b?.fraud_rate)}</td>
                  <td className="py-3 text-right">
                    <div className="font-bold">{pct(b && totalFraud ? b.fraud_caught / totalFraud : null)}</div>
                    <div className="text-xs text-muted2">{b?.fraud_caught.toLocaleString() ?? '—'} cases</div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2 text-xs">
        <span className="rounded-full bg-bg px-3 py-1.5 font-medium text-muted2">
          Recall, review or block: <b className="text-ink">{pct(m.cost.recall_review_or_block)}</b>
        </span>
        <span className="rounded-full bg-bg px-3 py-1.5 font-medium text-muted2">
          Recall, block only: <b className="text-ink">{pct(m.cost.recall_block_only)}</b>
        </span>
        {m.thresholds.review_capacity_cap != null && (
          <span className="rounded-full bg-bg px-3 py-1.5 font-medium text-muted2">
            Review capacity cap: <b className="text-ink">{pct(m.thresholds.review_capacity_cap, 0)}</b>
          </span>
        )}
      </div>
    </section>
  );
}

/* ── cost ──────────────────────────────────────────────────────────────────── */

function CostCard({ m }: { m: Metrics }) {
  const c = m.cost;
  const breakdown: [string, number | undefined][] = [
    ['Missed fraud', c.breakdown.missed_fraud_cost],
    ['Blocked legitimate', c.breakdown.blocked_legit_cost],
    ['Analyst reviews', c.breakdown.review_cost_total],
  ];
  const maxB = Math.max(...breakdown.map(([, v]) => v ?? 0));
  const maxS = Math.max(...c.strategies.map((s) => s.savings_pct), 0.0001);
  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle
        title="Cost on the holdout"
        subtitle={`${usd(c.cost_total)} with the model vs. ${usd(c.cost_approve_all)} approving everything`}
        right={<div className="flex h-8 items-center whitespace-nowrap rounded-full bg-bg px-3.5 text-[13px] font-bold text-brand">{usd(c.savings_per_100k_txns)} / 100k txns</div>}
      />
      <div className="flex flex-col gap-2.5">
        <div className="text-xs font-medium text-muted">Where the remaining cost comes from</div>
        {breakdown.map(([k, v]) => (
          <HBar key={k} label={k} value={v ?? 0} max={maxB} display={usd(v, true)} />
        ))}
      </div>
      <div className="flex flex-col gap-2.5 border-t border-line pt-4">
        <div className="text-xs font-medium text-muted">Savings by decision strategy</div>
        {c.strategies.map((s) => (
          <HBar
            key={s.name}
            labelWidth="58%"
            label={<span className={s.name.includes('shipped') ? 'font-bold' : ''}>{s.name}</span>}
            value={s.savings_pct}
            max={maxS}
            display={pct(s.savings_pct)}
            title={`${s.name}: total cost ${usd(s.cost)}`}
          />
        ))}
      </div>
    </section>
  );
}

/* ── live stream (PostgreSQL) ──────────────────────────────────────────────── */

function LiveCard({ m }: { m: Metrics }) {
  const l = m.live_demo_stream;
  const g = l.ground_truth;
  const total = l.total_transactions;
  const tiles: [string, string, string][] = [
    ['Stored transactions', total.toLocaleString(), l.first_at ? `since ${new Date(l.first_at).toLocaleDateString()}` : 'none yet'],
    ['Latency p50', ms(l.p50_latency_ms), `p95 ${ms(l.p95_latency_ms)} · p99 ${ms(l.p99_latency_ms)}`],
    ['Precision, flagged', pct(g.precision_flagged), `${g.flagged_true_positive.toLocaleString()} fraud of ${(g.flagged_true_positive + g.flagged_false_positive).toLocaleString()} flagged`],
    ['Recall, flagged', pct(g.recall_flagged), `${g.fraud.toLocaleString()} fraud in ${g.labelled.toLocaleString()} labelled`],
    ['Review queue', l.review_queue_size.toLocaleString(), 'pending Review decisions'],
    ['Analyst precision', l.analyst_reviewed ? pct(l.analyst_confirmed_precision) : '—', `${l.analyst_reviewed.toLocaleString()} reviewed`],
  ];
  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle title="Live stream" subtitle="Every scored transaction stored in PostgreSQL. Refreshes every 10 s." />
      <div className="flex h-3 overflow-hidden rounded-[4px] bg-bg" role="img" aria-label="Decision mix of stored transactions">
        {DECISIONS.map((d) => {
          const n = l.decision_counts[d] ?? 0;
          return total ? <div key={d} title={`${decisionTokens(d).label}: ${n.toLocaleString()}`} style={{ width: `${(n / total) * 100}%`, background: decisionTokens(d).dot }} className="border-r-2 border-[var(--card)] last:border-r-0" /> : null;
        })}
      </div>
      <div className="flex flex-wrap gap-4 text-xs text-muted2">
        {DECISIONS.map((d) => (
          <span key={d} className="flex items-center gap-1.5">
            <span className="h-2.5 w-2.5 rounded-full" style={{ background: decisionTokens(d).dot }} />
            {decisionTokens(d).label} <b className="text-ink">{(l.decision_counts[d] ?? 0).toLocaleString()}</b>
          </span>
        ))}
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {tiles.map(([k, v, sub]) => (
          <div key={k} className="rounded-2xl bg-bg px-4 py-3">
            <div className="text-xs font-medium text-muted2">{k}</div>
            <div className="text-[19px] font-bold">{v}</div>
            <div className="text-[11px] text-muted">{sub}</div>
          </div>
        ))}
      </div>
      <p className="text-xs leading-normal text-muted">
        Precision and recall use the holdout label on simulated rows. The replay keeps fraud at about 1 in 20 instead of the natural 1 in 29, so these won't match the holdout numbers exactly.
      </p>
    </section>
  );
}

/* ── global feature importance ─────────────────────────────────────────────── */

function FeaturesCard({ m }: { m: Metrics }) {
  const f = m.top_features;
  const max = Math.max(...f.map((x) => x.mean_abs_shap), 0.0001);
  return (
    <section className="fs-card flex min-w-0 flex-col gap-4 px-6 py-[22px]">
      <CardTitle title="What drives the score" subtitle="Mean |SHAP| over a holdout sample, log-odds" />
      <div className="flex flex-col gap-2.5">
        {f.map((x) => (
          <HBar key={x.feature} label={<span className="font-mono">{x.feature}</span>} value={x.mean_abs_shap} max={max} display={x.mean_abs_shap.toFixed(3)} />
        ))}
        {!f.length && <div className="text-sm text-muted">shap_global.json not found in ml/artifacts.</div>}
      </div>
    </section>
  );
}
