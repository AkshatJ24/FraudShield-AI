import { config } from '../config';
import type { Decision, Reason, StreamEvent } from './types';

// In-browser stand-in for the simulator (VITE_DATA_SOURCE=mock). Same payload shape the
// patched backend sends: ScoreResponse + true_label + request fields + scored_at.

const R = Math.random;
const pick = <T,>(a: T[]): T => a[Math.floor(R() * a.length)];
function sample<T>(a: T[], n: number): T[] {
  const c = a.slice();
  const out: T[] = [];
  while (out.length < n && c.length) out.push(c.splice(Math.floor(R() * c.length), 1)[0]);
  return out;
}
const ULID = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

export function mockEvent(): StreamEvent {
  const { review, block } = config.thresholds;
  const fraud = R() < 0.06;
  let score: number;
  if (fraud) score = R() < 0.75 ? block + Math.floor(R() * 80) : review + Math.floor(R() * (block - review));
  else {
    const r = R();
    score = r < 0.86 ? Math.floor(R() * review) : r < 0.965 ? review + Math.floor(R() * (block - review)) : block + Math.floor(R() * 26);
  }
  score = Math.min(100, score);
  const decision: Decision = score >= block ? 'BLOCK' : score >= review ? 'REVIEW' : 'APPROVE';

  const amt = fraud && R() < 0.35 ? 1 + R() * 9 : fraud ? 180 + R() * 2200 : Math.min(1800, Math.exp(2.4 + R() * 3.4));
  const ProductCD = fraud && R() < 0.45 ? 'C' : pick(['W', 'W', 'W', 'W', 'H', 'C', 'S', 'R']);
  const card4 = pick(['visa', 'visa', 'visa', 'mastercard', 'mastercard', 'american express', 'discover']);
  const card6 = fraud ? (R() < 0.7 ? 'credit' : 'debit') : R() < 0.75 ? 'debit' : 'credit';
  const P_emaildomain =
    fraud && R() < 0.3 ? 'protonmail.com' : pick<string | null>(['gmail.com', 'gmail.com', 'yahoo.com', 'hotmail.com', 'anonymous.com', 'outlook.com', 'icloud.com', null]);
  const DeviceType = R() < (fraud ? 0.25 : 0.55) ? null : R() < (fraud ? 0.7 : 0.45) ? 'mobile' : 'desktop';

  let reasons: Reason[];
  if (decision === 'APPROVE') {
    const pool = [
      "Amount is in line with this card's history",
      'Device has been seen with this card before',
      `Card first seen ${30 + Math.floor(R() * 400)} days ago`,
      'No other transactions on this card in the last hour',
      'Email domain matches the card history',
    ];
    let c = 0.5 + R() * 0.8;
    reasons = sample(pool, 3).map((text) => {
      const r: Reason = { text, contribution: -Number(c.toFixed(3)), kind: 'specific' };
      c *= 0.55 + R() * 0.25;
      return r;
    });
  } else {
    const pool: (() => string)[] = [
      () => `Amount is ${(3 + R() * 7).toFixed(1)}× this card's average`,
      () => 'First time this device is seen with this card',
      () => `${2 + Math.floor(R() * 5)} transactions on this card in the last 10 minutes`,
      () => 'New email domain for this card',
      () => (P_emaildomain ? `Purchaser email domain ${P_emaildomain} has an elevated fraud rate` : 'Purchaser email domain is missing'),
      () => `Only ${5 + Math.floor(R() * 40)} s since the previous transaction on this card`,
      () => 'New billing address for this card',
      () => `Product code ${ProductCD} carries elevated fraud risk`,
    ];
    const anon = ['Anonymized count feature C13 is unusually high', 'Anonymized match flag M4 differs from card history', 'Anonymized timing feature D15 is low'];
    const three = sample(pool, 3);
    const picked: Omit<Reason, 'contribution'>[] = [
      { text: three[0](), kind: 'specific' },
      { text: three[1](), kind: 'specific' },
      R() < 0.5 ? { text: pick(anon), kind: 'anonymized' } : { text: three[2](), kind: 'specific' },
    ];
    let c = 0.9 + R() * 1.6;
    reasons = picked.map((r) => {
      const o: Reason = { ...r, contribution: Number(c.toFixed(3)) };
      c *= 0.5 + R() * 0.3;
      return o;
    });
  }

  const prob = Math.min(0.99, Math.pow(score / 100, 1.7) + 0.0008 + R() * 0.0005);
  return {
    transaction_id: 'tx_01' + Array.from({ length: 9 }, () => ULID[Math.floor(R() * 32)]).join(''),
    score,
    decision,
    reasons,
    calibrated_prob: Number(prob.toFixed(4)),
    raw_score: Number((prob * 0.92).toFixed(4)),
    latency_ms: Number((24 + R() * 40 + (R() < 0.05 ? 45 : 0)).toFixed(1)),
    what_if: false,
    true_label: fraud,
    TransactionAmt: Number(amt.toFixed(2)),
    ProductCD,
    card1: 1000 + Math.floor(R() * 17000),
    card4,
    card6,
    P_emaildomain,
    DeviceType,
    scored_at: Date.now(),
  };
}
