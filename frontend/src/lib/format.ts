import type { Decision, Tx } from '../api/types';

export const fmtTime = (ts: number) => {
  const d = new Date(ts);
  return [d.getHours(), d.getMinutes(), d.getSeconds()].map((n) => String(n).padStart(2, '0')).join(':');
};

export const money = (n?: number | null) =>
  n == null ? '—' : '$' + n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const cap = (s?: string | null) => (s ? s.replace(/\b\w/g, (c) => c.toUpperCase()) : '—');

export const network = (s?: string | null) => (s === 'american express' ? 'Amex' : cap(s));

export const cardLabel = (tx: Tx) => (tx.card4 || tx.card6 ? `${network(tx.card4)} · ${tx.card6 ?? '—'}` : '—');

export const txTime = (tx: Tx) => fmtTime(tx.scored_at ?? tx.ts);

export type DecisionKey = 'approve' | 'review' | 'block';

export const decisionKey = (d: Decision): DecisionKey => (d === 'BLOCK' ? 'block' : d === 'REVIEW' ? 'review' : 'approve');

/** CSS-variable colours for a decision; the palette switches via `data-dec` on <html>. */
export function decisionTokens(d: Decision) {
  const k = decisionKey(d);
  return { key: k, label: k[0].toUpperCase() + k.slice(1), bg: `var(--${k}-bg)`, fg: `var(--${k}-fg)`, dot: `var(--${k}-dot)` };
}

/** True when the decision matched ground truth (flagged ⇔ fraud). */
export const isCorrect = (tx: Tx) => (tx.decision !== 'APPROVE') === !!tx.true_label;

/** 0.5936 → "59.4%" */
export const pct = (v?: number | null, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`);

/** Whole dollars: 306225.6 → "$306,226"; compact: "$306k" */
export const usd = (v?: number | null, compact = false) =>
  v == null
    ? '—'
    : compact && Math.abs(v) >= 1000
      ? `$${(v / 1000).toLocaleString('en-US', { maximumFractionDigits: Math.abs(v) >= 100000 ? 0 : 1 })}k`
      : '$' + Math.round(v).toLocaleString('en-US');
