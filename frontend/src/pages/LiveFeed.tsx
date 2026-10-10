import { useMemo, useState } from 'react';
import { useFraudShield } from '../state/FraudShield';
import { FeedTable } from '../components/FeedTable';

const FILTERS = [
  { key: 'all', label: 'All' },
  { key: 'flagged', label: 'Flagged' },
  { key: 'review', label: 'Review' },
  { key: 'block', label: 'Block' },
] as const;
type Filter = (typeof FILTERS)[number]['key'];

export function LiveFeed() {
  const { txs, running, toggleRun } = useFraudShield();
  const [filter, setFilter] = useState<Filter>('all');

  const counts = useMemo(() => {
    let review = 0, block = 0;
    txs.forEach((t) => (t.decision === 'REVIEW' ? review++ : t.decision === 'BLOCK' ? block++ : 0));
    return { all: txs.length, flagged: review + block, review, block };
  }, [txs]);

  const rows = useMemo(
    () =>
      txs
        .filter((t) => filter === 'all' || (filter === 'flagged' ? t.decision !== 'APPROVE' : t.decision === filter.toUpperCase()))
        .slice(0, 150),
    [txs, filter],
  );

  return (
    <div className="flex animate-fade-up flex-col gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3.5">
        <div className="flex flex-wrap gap-1.5 rounded-full bg-card p-1.5 shadow-card" role="tablist">
          {FILTERS.map(({ key, label }) => {
            const on = filter === key;
            return (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={on}
                onClick={() => setFilter(key)}
                className={`flex h-[38px] cursor-pointer items-center gap-2 whitespace-nowrap rounded-full px-4 text-sm font-bold ${on ? 'bg-brand-grad text-white' : 'text-muted2 hover:text-ink'}`}
              >
                {label}
                <span className="text-xs font-medium opacity-80">{counts[key]}</span>
              </button>
            );
          })}
        </div>
        <div className="flex items-center gap-3 text-sm text-muted2">
          <span>
            Showing {rows.length} of {txs.length}
          </span>
          <button type="button" onClick={toggleRun} className="h-[42px] cursor-pointer rounded-full bg-brand-grad px-5 text-sm font-bold text-white shadow-[0_10px_24px_rgba(47,63,232,.25)]">
            {running ? 'Pause stream' : 'Resume stream'}
          </button>
        </div>
      </div>

      <section className="fs-card min-w-0 px-[18px] pb-2 pt-3.5">
        <FeedTable rows={rows} variant="full" emptyText={txs.length === 0 ? 'Waiting for the first transaction from /stream…' : 'No transactions match this filter yet.'} />
      </section>
    </div>
  );
}
