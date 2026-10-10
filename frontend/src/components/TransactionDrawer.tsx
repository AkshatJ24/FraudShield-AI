import { useRef, useState } from 'react';
import { Drawer, DrawerBody, DrawerContent, DrawerOverlay } from '@chakra-ui/react';
import { X } from 'lucide-react';
import { REQUEST_KEYS, type Tx } from '../api/types';
import { useFraudShield } from '../state/FraudShield';
import { cap, cardLabel, decisionTokens, isCorrect, money, txTime } from '../lib/format';

export function TransactionDrawer() {
  const { selected, select } = useFraudShield();
  // Keep the last transaction rendered while the drawer animates closed.
  const last = useRef<Tx | null>(null);
  if (selected) last.current = selected;
  const tx = selected ?? last.current;

  return (
    <Drawer isOpen={!!selected} placement="right" onClose={() => select(null)} size="md">
      <DrawerOverlay bg="rgba(11,20,55,.32)" backdropFilter="blur(3px)" />
      <DrawerContent bg="var(--card)" color="var(--ink)" maxW="min(470px, 100vw)" boxShadow="-24px 0 60px rgba(11,20,55,.18)">
        <DrawerBody p="26px 28px 36px">{tx && <Detail tx={tx} onClose={() => select(null)} />}</DrawerBody>
      </DrawerContent>
    </Drawer>
  );
}

function Detail({ tx, onClose }: { tx: Tx; onClose: () => void }) {
  const { truth, toggleTruth } = useFraudShield();
  const [tab, setTab] = useState<'request' | 'response'>('response');
  const d = decisionTokens(tx.decision);
  const max = Math.max(...tx.reasons.map((r) => Math.abs(r.contribution)), 0.0001);
  const correct = isCorrect(tx);

  const requestFields = Object.fromEntries(REQUEST_KEYS.filter((k) => tx[k] !== undefined).map((k) => [k, tx[k]]));
  const hasRequest = Object.keys(requestFields).length > 0;
  const response = {
    transaction_id: tx.transaction_id,
    score: tx.score,
    decision: tx.decision,
    reasons: tx.reasons,
    calibrated_prob: tx.calibrated_prob,
    raw_score: tx.raw_score,
    latency_ms: tx.latency_ms,
    what_if: tx.what_if,
  };
  const json =
    tab === 'request'
      ? hasRequest
        ? JSON.stringify({ ...requestFields, what_if: tx.what_if }, null, 2)
        : '// This event arrived without request fields.\n// Restart the API so it runs the current backend/app/api/stream.py.'
      : JSON.stringify(response, null, 2);

  const fields: [string, string, boolean?][] = [
    ['Amount', money(tx.TransactionAmt)],
    ['Product', tx.ProductCD ?? '—'],
    ['Card', cardLabel(tx)],
    ['Device', cap(tx.DeviceType)],
    ['Purchaser email domain', tx.P_emaildomain ?? '—', true],
  ];
  const tabBtn = (on: boolean) => `h-[30px] cursor-pointer rounded-full px-3.5 text-[13px] font-bold ${on ? 'bg-card text-brand' : 'text-muted2'}`;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1">
          <div className="text-sm font-medium text-muted2">Transaction</div>
          <div className="break-all font-mono text-[15px] font-medium">{tx.transaction_id}</div>
        </div>
        <button type="button" onClick={onClose} aria-label="Close" className="flex h-[38px] w-[38px] flex-none cursor-pointer items-center justify-center rounded-full bg-bg text-ink">
          <X size={18} strokeWidth={2.2} />
        </button>
      </div>

      <div className="flex items-center gap-[22px] rounded-[20px] bg-bg px-5 py-[18px]">
        <div className="relative h-[100px] w-[170px] flex-none">
          <svg viewBox="0 0 200 110" className="block h-[94px] w-[170px]">
            <path d="M20 100 A80 80 0 0 1 180 100" style={{ fill: 'none', stroke: 'var(--line)', strokeWidth: 16, strokeLinecap: 'round' }} />
            <path
              d="M20 100 A80 80 0 0 1 180 100"
              style={{
                fill: 'none',
                stroke: d.dot,
                strokeWidth: 16,
                strokeLinecap: 'round',
                strokeDasharray: `${((Math.max(2, tx.score) / 100) * 251.3).toFixed(1)} 400`,
                transition: 'stroke-dasharray .8s cubic-bezier(.2,.8,.2,1)',
              }}
            />
          </svg>
          <div className="absolute inset-x-0 bottom-0 text-center">
            <div className="text-[34px] font-bold leading-none">{tx.score}</div>
            <div className="text-[11px] text-muted2">risk score</div>
          </div>
        </div>
        <div className="flex min-w-0 flex-col gap-2">
          <span className="self-start rounded-full px-3.5 py-1.5 text-[13px] font-bold" style={{ background: d.bg, color: d.fg }}>
            {d.label}
          </span>
          <div className="text-[13px] leading-relaxed text-muted2">
            p(fraud) {tx.calibrated_prob.toFixed(4)}
            <br />
            {tx.latency_ms} ms · {txTime(tx)}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-[18px] gap-y-3.5">
        {fields.map(([label, value, wide]) => (
          <div key={label} className={wide ? 'col-span-2' : ''}>
            <div className="text-xs text-muted">{label}</div>
            <div className="text-base font-bold">{value}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-col gap-3.5">
        <h3 className="text-lg font-bold">Why this decision</h3>
        {tx.reasons.map((r, i) => {
          const up = r.contribution > 0;
          return (
            <div key={i} className="flex flex-col gap-[7px]">
              <div className="flex items-baseline justify-between gap-3">
                <div className="text-pretty text-[15px] font-medium">{r.text}</div>
                <div className="flex-none font-mono text-[13px] font-medium text-muted2">
                  {up ? '+' : ''}
                  {r.contribution.toFixed(2)}
                </div>
              </div>
              <div className="h-2 overflow-hidden rounded bg-bg">
                <div className={`h-2 rounded ${up ? 'bg-brand-grad' : 'bg-muted'}`} style={{ width: `${((Math.abs(r.contribution) / max) * 100).toFixed(0)}%` }} />
              </div>
              <div className="text-xs text-muted">
                {up ? 'Raises risk' : 'Lowers risk'}
                {r.kind === 'anonymized' ? ' · anonymized feature' : ''}
              </div>
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between gap-3 rounded-2xl border border-line px-4 py-3.5">
        <div className="flex flex-col gap-0.5">
          <div className="text-xs text-muted">Ground truth (demo only)</div>
          <div className="text-[15px] font-bold">
            {!truth ? 'Hidden' : tx.true_label == null ? 'Not available' : `${tx.true_label ? 'Fraud' : 'Legitimate'} · model ${correct ? 'was right' : 'was wrong'}`}
          </div>
        </div>
        <button type="button" onClick={toggleTruth} className="h-9 cursor-pointer whitespace-nowrap rounded-full bg-bg px-3.5 text-[13px] font-bold text-brand">
          {truth ? 'Hide' : 'Reveal'}
        </button>
      </div>

      <div className="flex flex-col gap-2.5">
        <div className="flex items-center justify-between gap-2.5">
          <h3 className="text-lg font-bold">Inspector</h3>
          <div className="flex gap-1 rounded-full bg-bg p-1" role="tablist">
            <button type="button" role="tab" aria-selected={tab === 'request'} onClick={() => setTab('request')} className={tabBtn(tab === 'request')}>
              Request
            </button>
            <button type="button" role="tab" aria-selected={tab === 'response'} onClick={() => setTab('response')} className={tabBtn(tab === 'response')}>
              Response
            </button>
          </div>
        </div>
        <div className="font-mono text-xs text-muted">{tab === 'request' ? 'POST /score' : `200 OK · ${tx.latency_ms} ms`}</div>
        <pre className="m-0 overflow-x-auto whitespace-pre rounded-2xl bg-bg p-4 font-mono text-[12.5px] leading-relaxed text-ink">{json}</pre>
      </div>
    </div>
  );
}
