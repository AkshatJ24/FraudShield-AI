import { useMemo } from 'react';
import { Activity, Ban, CircleCheck, Timer, TriangleAlert, type LucideIcon } from 'lucide-react';
import { useFraudShield, useNow } from '../state/FraudShield';

interface Stat {
  label: string;
  value: string;
  sub: string;
  icon: LucideIcon;
  accent?: boolean;
}

export function StatsStrip() {
  const { txs } = useFraudShield();
  const now = useNow(1000);

  const stats = useMemo<Stat[]>(() => {
    const n = txs.length;
    let ap = 0, rv = 0, bl = 0;
    txs.forEach((t) => (t.decision === 'APPROVE' ? ap++ : t.decision === 'REVIEW' ? rv++ : bl++));
    const pct = (v: number) => (n ? `${((v / n) * 100).toFixed(1)}% of traffic` : '—');
    const lats = txs.slice(0, 200).map((t) => t.latency_ms).sort((a, b) => a - b);
    const q = (p: number) => (lats.length ? `${Math.round(lats[Math.floor(p * (lats.length - 1))])} ms` : '—');
    const rate = (txs.filter((t) => now - t.ts < 10000).length / 10).toFixed(1);
    return [
      { label: 'Scored', value: n.toLocaleString(), sub: `${rate} tx/s`, icon: Activity },
      { label: 'Approved', value: ap.toLocaleString(), sub: pct(ap), icon: CircleCheck },
      { label: 'In review', value: rv.toLocaleString(), sub: pct(rv), icon: TriangleAlert },
      { label: 'Blocked', value: bl.toLocaleString(), sub: pct(bl), icon: Ban, accent: true },
      { label: 'Latency p95', value: q(0.95), sub: `p50 ${q(0.5)}`, icon: Timer },
    ];
  }, [txs, now]);

  return (
    <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))' }}>
      {stats.map(({ label, value, sub, icon: Icon, accent }) => (
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
