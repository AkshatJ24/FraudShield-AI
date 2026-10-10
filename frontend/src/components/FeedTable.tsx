import type { Tx } from '../api/types';
import { useFraudShield, useNow } from '../state/FraudShield';
import { cap, cardLabel, decisionTokens, isCorrect, money, txTime } from '../lib/format';

const COMPACT_COLS = '76px minmax(80px,1fr) 60px minmax(110px,1.3fr) 72px minmax(100px,1.1fr) 90px 58px';
const fullCols = (truth: boolean) =>
  `76px minmax(130px,1.1fr) 90px 60px minmax(110px,1fr) minmax(110px,1fr) 72px minmax(100px,1fr) 86px 58px${truth ? ' 74px' : ''}`;

interface Props {
  rows: Tx[];
  variant: 'compact' | 'full';
  emptyText: string;
}

export function FeedTable({ rows, variant, emptyText }: Props) {
  const { select, truth, txs } = useFraudShield();
  const now = useNow(1000);
  const full = variant === 'full';
  const showTruth = full && truth;
  const cols = full ? fullCols(truth) : COMPACT_COLS;
  const headers = full
    ? ['Time', 'Transaction', 'Amount', 'Product', 'Card', 'Email domain', 'Device', 'Risk', 'Decision', 'Latency', ...(showTruth ? ['Truth'] : [])]
    : ['Time', 'Amount', 'Product', 'Card', 'Device', 'Risk', 'Decision', 'Latency'];
  const waiting = txs.length === 0;

  return (
    <div className="overflow-x-auto">
      <div className={full ? 'min-w-[980px]' : 'min-w-[640px]'}>
        <div className="sticky top-0 grid gap-3 border-b border-line bg-card px-2 py-2.5 text-[13px] font-medium text-muted" style={{ gridTemplateColumns: cols }}>
          {headers.map((h) => (
            <span key={h} className={h === 'Latency' ? 'text-right' : ''}>
              {h}
            </span>
          ))}
        </div>

        {rows.length === 0 ? (
          <div className={`flex items-center gap-2.5 px-2 text-muted ${full ? 'justify-center py-10 text-[15px]' : 'py-7 text-sm'}`}>
            {waiting && <span className="h-2 w-2 animate-blink rounded-full bg-brand" />}
            {emptyText}
          </div>
        ) : (
          <div className={full ? 'max-h-[calc(100vh-290px)] min-h-[240px] overflow-y-auto' : ''}>
            {rows.map((tx) => {
              const d = decisionTokens(tx.decision);
              const correct = isCorrect(tx);
              return (
                <div
                  key={tx.transaction_id}
                  role="button"
                  tabIndex={0}
                  onClick={() => select(tx.transaction_id)}
                  onKeyDown={(e) => e.key === 'Enter' && select(tx.transaction_id)}
                  className={`grid cursor-pointer items-center gap-3 rounded-[10px] border-b border-line px-2 py-[11px] text-sm transition-colors duration-700 hover:bg-bg ${now - tx.ts < 1500 ? 'bg-brandsoft' : ''}`}
                  style={{ gridTemplateColumns: cols }}
                >
                  <span className="font-mono text-[13px] text-muted2">{txTime(tx)}</span>
                  {full && <span className="truncate font-mono text-[13px] text-muted2">{tx.transaction_id}</span>}
                  <span className="font-bold">{money(tx.TransactionAmt)}</span>
                  <span>{tx.ProductCD ?? '—'}</span>
                  <span className="truncate">{cardLabel(tx)}</span>
                  {full && <span className="truncate text-muted2">{tx.P_emaildomain ?? '—'}</span>}
                  <span className="text-muted2">{cap(tx.DeviceType)}</span>
                  <span className="flex items-center gap-2">
                    <span className="w-[22px] text-[13px] font-bold">{tx.score}</span>
                    <span className="h-1.5 flex-1 overflow-hidden rounded-[3px] bg-line">
                      <span className="block h-1.5 rounded-[3px]" style={{ width: `${Math.max(4, tx.score)}%`, background: d.dot }} />
                    </span>
                  </span>
                  <span>
                    <span className="inline-flex whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold" style={{ background: d.bg, color: d.fg }}>
                      {d.label}
                    </span>
                  </span>
                  <span className="text-right font-mono text-[13px] text-muted2">{Math.round(tx.latency_ms)} ms</span>
                  {showTruth && (
                    <span className="whitespace-nowrap text-[13px] font-bold" style={{ color: correct ? 'var(--muted-2)' : 'var(--brand)' }}>
                      {tx.true_label == null ? '—' : `${tx.true_label ? 'Fraud' : 'Legit'} ${correct ? '✓' : '✗'}`}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
