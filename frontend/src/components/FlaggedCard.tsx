import { useMemo } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useFraudShield, useNow } from '../state/FraudShield';
import { cap, decisionTokens, money, network, txTime } from '../lib/format';
import { CardTitle, LinkButton } from './ui';

const BACKS = [
  'linear-gradient(135deg,#7B8BFF 0%,#2F3FE8 62%,#2230C8 100%)',
  'linear-gradient(135deg,#A4AEFF,#6C7BFF)',
  'linear-gradient(135deg,#CDD3FF,#A4AEFF)',
];

export function FlaggedCard() {
  const { txs, stackIdx, setStackIdx, select } = useFraudShield();
  const now = useNow(1000);
  const flagged = useMemo(() => txs.filter((t) => t.decision !== 'APPROVE'), [txs]);
  const idx = Math.min(stackIdx, Math.max(0, flagged.length - 1));
  const top = flagged[idx];
  const visible = flagged.slice(idx, idx + 3);
  const canPrev = idx > 0;
  const canNext = idx < flagged.length - 1;

  const navBtn = 'flex h-[34px] w-[34px] cursor-pointer items-center justify-center rounded-full bg-bg text-ink disabled:cursor-default disabled:opacity-40';

  return (
    <section className="fs-card flex flex-col gap-4 px-6 py-[22px]">
      <CardTitle
        title="Flagged"
        subtitle="Review and Block, newest on top"
        right={
          <div className="flex items-center gap-2">
            <div className="min-w-[52px] text-right text-[13px] font-bold text-muted2">{flagged.length ? `${idx + 1} / ${flagged.length}` : '0 / 0'}</div>
            <button type="button" aria-label="Newer" disabled={!canPrev} onClick={() => setStackIdx(Math.max(0, idx - 1))} className={navBtn}>
              <ChevronLeft size={18} strokeWidth={2.2} />
            </button>
            <button type="button" aria-label="Older" disabled={!canNext} onClick={() => setStackIdx(Math.min(flagged.length - 1, idx + 1))} className={navBtn}>
              <ChevronRight size={18} strokeWidth={2.2} />
            </button>
          </div>
        }
      />

      <div className="pt-1">
        {!top ? (
          <div className="flex h-[236px] max-w-[460px] items-center justify-center rounded-3xl border-2 border-dashed border-line text-[15px] text-muted">No flagged transactions yet</div>
        ) : (
          <div className="relative h-[240px] max-w-[460px]">
            {visible.map((tx, i) => {
              const isTop = i === 0;
              const d = decisionTokens(tx.decision);
              const fresh = isTop && idx === 0 && now - tx.ts < 1300;
              return (
                <div
                  key={tx.transaction_id}
                  role={isTop ? 'button' : undefined}
                  tabIndex={isTop ? 0 : -1}
                  onClick={isTop ? () => select(tx.transaction_id) : undefined}
                  onKeyDown={isTop ? (e) => e.key === 'Enter' && select(tx.transaction_id) : undefined}
                  className={`absolute inset-x-0 top-0 flex h-[200px] flex-col overflow-hidden rounded-[26px] px-[26px] py-[22px] text-white ${fresh ? 'animate-card-in' : ''} ${isTop ? 'cursor-pointer' : ''}`}
                  style={{
                    background: BACKS[i],
                    transform: `translateY(${i * 17}px) scale(${1 - i * 0.055})`,
                    transformOrigin: '50% 100%',
                    zIndex: 3 - i,
                    boxShadow: isTop ? '0 22px 44px rgba(47,63,232,.32)' : '0 10px 24px rgba(47,63,232,.14)',
                    transition: 'transform .55s cubic-bezier(.2,.8,.2,1), box-shadow .55s, background .55s',
                  }}
                >
                  {isTop && (
                    <>
                      <div className="absolute -right-[90px] -top-[120px] h-[260px] w-[260px] rounded-full bg-white/10" />
                      <div className="relative flex items-start justify-between">
                        <div>
                          <div className="text-xs opacity-80">Card</div>
                          <div className="text-lg font-bold">{tx.card4 || tx.card6 ? `${network(tx.card4)} · ${tx.card6 ?? '—'}` : 'Card details pending'}</div>
                        </div>
                        <div className="flex">
                          <span className="h-[30px] w-[30px] rounded-full bg-white/55" />
                          <span className="-ml-3 h-[30px] w-[30px] rounded-full bg-white/30" />
                        </div>
                      </div>
                      <div className="relative mt-3.5 text-base tracking-[.18em] opacity-90">•••• •••• •••• {tx.card1 != null ? String(tx.card1).slice(-4) : '····'}</div>
                      <div className="relative mt-auto flex items-end justify-between">
                        <div>
                          <div className="text-xs opacity-80">Amount</div>
                          <div className="text-[28px] font-bold tracking-[-.01em]">{money(tx.TransactionAmt)}</div>
                        </div>
                        <div className="flex flex-none flex-col items-end gap-1.5">
                          <span
                            className="whitespace-nowrap rounded-full border border-white/45 px-3 py-[5px] text-xs font-bold"
                            style={{ background: tx.decision === 'BLOCK' ? '#fff' : 'rgba(255,255,255,.2)', color: tx.decision === 'BLOCK' ? '#2F3FE8' : '#fff' }}
                          >
                            {d.label.toUpperCase()} · {tx.score}
                          </span>
                          <span className="font-mono text-[13px] opacity-85">{txTime(tx)}</span>
                        </div>
                      </div>
                    </>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {top && (
        <div className="flex flex-wrap items-center justify-between gap-3.5">
          <div className="flex min-w-0 flex-[1_1_220px] flex-col gap-[3px]">
            <div className="text-xs font-medium text-muted">Top reason</div>
            <div className="text-pretty text-[15px] font-bold">{top.reasons[0]?.text ?? '—'}</div>
            <div className="text-[13px] text-muted2">
              {top.P_emaildomain || 'no email'} · {cap(top.DeviceType)} · product {top.ProductCD ?? '—'}
            </div>
          </div>
          <LinkButton onClick={() => select(top.transaction_id)}>Open details</LinkButton>
        </div>
      )}
    </section>
  );
}
