import { useFraudShield } from '../state/FraudShield';
import { StatsStrip } from '../components/StatsStrip';
import { PulseRingCard } from '../components/PulseRingCard';
import { FlaggedCard } from '../components/FlaggedCard';
import { FeedTable } from '../components/FeedTable';
import { ModelCard } from '../components/ModelCard';
import { LinkButton } from '../components/ui';

export function Overview({ onViewAll }: { onViewAll: () => void }) {
  const { txs } = useFraudShield();
  return (
    <div className="flex animate-fade-up flex-col gap-5">
      <StatsStrip />
      <div className="grid gap-5" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 440px), 1fr))' }}>
        <PulseRingCard />
        <FlaggedCard />
      </div>
      <div className="flex flex-wrap items-start gap-5">
        <section className="fs-card flex min-w-0 flex-[2_1_560px] flex-col gap-3 px-6 py-[22px]">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-[22px] font-bold tracking-[-.01em]">Live feed</h2>
            <LinkButton onClick={onViewAll}>View all</LinkButton>
          </div>
          <FeedTable rows={txs.slice(0, 6)} variant="compact" emptyText="Waiting for the first transaction from /stream…" />
        </section>
        <ModelCard />
      </div>
    </div>
  );
}
