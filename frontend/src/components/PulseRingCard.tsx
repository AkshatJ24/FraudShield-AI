import { useMemo } from 'react';
import { useFraudShield, useNow } from '../state/FraudShield';
import { decisionKey, decisionTokens, money } from '../lib/format';
import { CardTitle } from './ui';

const C = 160;
const WINDOW = 60000;

/** Radius for a score: inner band = approve, middle = review, outer = block. */
function radiusFor(s: number, { review, block }: { review: number; block: number }) {
  if (s < review) return 22 + (s / Math.max(1, review - 1)) * 44;
  if (s < block) return 80 + ((s - review) / Math.max(1, block - review - 1)) * 22;
  return 116 + Math.min(1, (s - block) / 60) * 30;
}

export function PulseRingCard() {
  const { txs, t0, select, thresholds } = useFraudShield();
  const now = useNow(1000);
  const recent = useMemo(() => txs.filter((t) => now - t.ts < WINDOW), [txs, now]);
  // Negative delay keeps the sweep hand in phase with t0 across remounts.
  const sweepDelay = useMemo(() => -((Date.now() - t0) % WINDOW), [t0]);
  const band = { approve: 0, review: 0, block: 0 };
  recent.forEach((t) => band[decisionKey(t.decision)]++);
  const { review, block } = thresholds;

  const legend = [
    { key: 'block' as const, label: 'Block', note: `outer ring · score ≥ ${block}` },
    { key: 'review' as const, label: 'Review', note: `middle ring · score ${review}–${block - 1}` },
    { key: 'approve' as const, label: 'Approve', note: `inner ring · score 0–${review - 1}` },
  ];

  return (
    <section className="fs-card flex flex-col gap-4 px-6 py-[22px]">
      <CardTitle
        title="Last 60 seconds"
        subtitle="Each dot is one transaction. Further out means higher risk."
        right={<div className="flex h-8 items-center whitespace-nowrap rounded-full bg-bg px-3.5 text-[13px] font-bold text-brand">{recent.length} in window</div>}
      />
      <div className="flex flex-wrap items-center gap-7">
        <div className="min-w-[240px] max-w-[340px] flex-[1_1_260px]">
          <svg viewBox="0 0 320 320" className="block h-auto w-full overflow-visible" role="img" aria-label={`${recent.length} transactions in the last 60 seconds`}>
            <defs>
              <linearGradient id="fsSweep" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0" style={{ stopColor: 'var(--brand)', stopOpacity: 0 }} />
                <stop offset="1" style={{ stopColor: 'var(--brand)', stopOpacity: 0.22 }} />
              </linearGradient>
            </defs>
            <circle cx={C} cy={C} r={150} style={{ fill: 'var(--ring-b)' }} />
            <circle cx={C} cy={C} r={108} style={{ fill: 'var(--ring-r)', stroke: 'var(--card)', strokeWidth: 3 }} />
            <circle cx={C} cy={C} r={72} style={{ fill: 'var(--ring-a)', stroke: 'var(--card)', strokeWidth: 3 }} />
            {Array.from({ length: 12 }, (_, i) => {
              const a = (i * Math.PI) / 6;
              return (
                <line
                  key={i}
                  x1={C + 146 * Math.sin(a)}
                  y1={C - 146 * Math.cos(a)}
                  x2={C + 152 * Math.sin(a)}
                  y2={C - 152 * Math.cos(a)}
                  style={{ stroke: 'var(--muted)', strokeWidth: 2, strokeLinecap: 'round', opacity: 0.5 }}
                />
              );
            })}
            <g className="animate-sweep" style={{ transformOrigin: '160px 160px', animationDelay: `${sweepDelay}ms` }}>
              <path d="M160 160 L63.6 45.1 A150 150 0 0 1 160 10 Z" style={{ fill: 'url(#fsSweep)' }} />
              <line x1={C} y1={C} x2={C} y2={10} style={{ stroke: 'var(--brand)', strokeWidth: 2.5, strokeLinecap: 'round' }} />
              <circle cx={C} cy={10} r={4} style={{ fill: 'var(--brand)' }} />
            </g>
            {recent
              .slice()
              .reverse()
              .map((tx) => {
                const age = now - tx.ts;
                const a = (((tx.ts - t0) % WINDOW) / WINDOW) * Math.PI * 2;
                const r = radiusFor(tx.score, thresholds);
                const x = C + r * Math.sin(a);
                const y = C - r * Math.cos(a);
                const size = tx.decision === 'BLOCK' ? 7 : tx.decision === 'REVIEW' ? 5.5 : 4;
                const d = decisionTokens(tx.decision);
                return (
                  <g key={tx.transaction_id} className="cursor-pointer" onClick={() => select(tx.transaction_id)}>
                    {age < 1600 && (
                      <circle cx={x} cy={y} r={size} className="animate-dot-ping" style={{ fill: d.dot, transformBox: 'fill-box', transformOrigin: 'center' }} />
                    )}
                    <circle cx={x} cy={y} r={size + 5} style={{ fill: 'transparent' }} />
                    <circle
                      cx={x}
                      cy={y}
                      r={size}
                      style={{
                        fill: d.dot,
                        opacity: Math.max(0.2, 1 - age / WINDOW),
                        transition: 'opacity 1s linear',
                        stroke: tx.decision === 'BLOCK' ? 'var(--card)' : 'none',
                        strokeWidth: 1.5,
                      }}
                    />
                    <title>{`${money(tx.TransactionAmt)} · score ${tx.score} · ${d.label}`}</title>
                  </g>
                );
              })}
            <circle cx={C} cy={C} r={27} style={{ fill: 'var(--card)', filter: 'drop-shadow(0 4px 10px rgba(47,63,232,.18))' }} />
            <text x={C} y={C + 2} textAnchor="middle" style={{ fill: 'var(--ink)', font: "700 17px 'DM Sans', sans-serif" }}>
              {recent.length}
            </text>
            <text x={C} y={C + 15} textAnchor="middle" style={{ fill: 'var(--muted)', font: "500 9px 'DM Sans', sans-serif" }}>
              in 60 s
            </text>
          </svg>
        </div>

        <div className="flex min-w-[150px] flex-[1_1_160px] flex-col gap-3.5">
          {legend.map(({ key, label, note }) => (
            <div key={key} className="flex items-center gap-3">
              <span className="h-3 w-3 flex-none rounded-full" style={{ background: `var(--${key}-dot)` }} />
              <div className="flex-1">
                <div className="text-[15px] font-bold">{label}</div>
                <div className="text-xs text-muted">{note}</div>
              </div>
              <div className="text-lg font-bold">{band[key]}</div>
            </div>
          ))}
          <p className="border-t border-line pt-3 text-xs leading-normal text-muted">The hand marks now and sweeps once a minute. Click a dot to open it.</p>
        </div>
      </div>
    </section>
  );
}
