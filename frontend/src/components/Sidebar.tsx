import { Tooltip, useMediaQuery } from '@chakra-ui/react';
import { Activity, BarChart3, FlaskConical, Inbox, LayoutDashboard, Pause, Play, RotateCcw, ShieldCheck, type LucideIcon } from 'lucide-react';
import { useFraudShield } from '../state/FraudShield';

export type Page = 'overview' | 'feed' | 'metrics';

const PAGES: { key: Page; label: string; icon: LucideIcon }[] = [
  { key: 'overview', label: 'Overview', icon: LayoutDashboard },
  { key: 'feed', label: 'Live Feed', icon: Activity },
  { key: 'metrics', label: 'Metrics', icon: BarChart3 },
];
const SOON: { label: string; icon: LucideIcon }[] = [
  { label: 'Try a Transaction', icon: FlaskConical },
  { label: 'Review Queue', icon: Inbox },
];

export function Sidebar({ page, onNavigate }: { page: Page; onNavigate: (p: Page) => void }) {
  const { phase, running, toggleRun, sim, restartReplay } = useFraudShield();
  const [narrow] = useMediaQuery('(max-width: 1179px)');
  const inApp = phase === 'app';
  const simTitle = !inApp ? 'Starting…' : running ? 'Replaying holdout' : 'Paused';
  const simText = running
    ? 'Unseen test-set transactions, fraud oversampled to ~1 in 20 for the demo.'
    : 'The stream is paused. Resume picks up where it stopped.';
  const progress = sim?.total ? Math.min(1, sim.position / sim.total) : null;
  const progressText = sim?.loading
    ? 'Warming up the card history…'
    : sim?.total
      ? `${sim.position.toLocaleString()} of ${sim.total.toLocaleString()} replayed`
      : null;
  const simBtn = running ? 'Pause stream' : 'Resume stream';
  const itemPad = narrow ? 'justify-center' : 'pl-[30px]';

  return (
    <aside className={`sticky top-0 z-[2] flex h-screen flex-none flex-col bg-card shadow-card transition-[width] duration-200 ${narrow ? 'w-[88px]' : 'w-[270px]'}`}>
      <div className="flex h-24 flex-none items-center justify-center gap-3 border-b border-line">
        <div className="flex h-[38px] w-[38px] flex-none items-center justify-center rounded-xl bg-brand-grad text-white">
          <ShieldCheck size={20} strokeWidth={2.2} />
        </div>
        {!narrow && (
          <div className="text-[22px] font-bold tracking-[-.02em]">
            Fraud<span className="font-medium">Shield</span>
          </div>
        )}
      </div>

      <nav className="flex flex-col gap-1 py-7">
        {PAGES.map(({ key, label, icon: Icon }) => {
          const on = page === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => inApp && onNavigate(key)}
              aria-current={on ? 'page' : undefined}
              className={`relative flex items-center gap-3.5 py-[11px] text-left text-base ${itemPad} ${on ? 'font-bold text-ink' : 'font-medium text-muted2 hover:text-ink'} ${inApp ? 'cursor-pointer' : 'cursor-default'}`}
            >
              <Icon size={22} strokeWidth={2} className={on ? 'text-brand' : ''} />
              {!narrow && <span>{label}</span>}
              <span className={`absolute bottom-1.5 right-0 top-1.5 w-1 rounded ${on ? 'bg-brand' : 'bg-transparent'}`} />
            </button>
          );
        })}
        {SOON.map(({ label, icon: Icon }) => (
          <Tooltip key={label} label={narrow ? `${label} · coming in a later phase` : 'Coming in a later phase'} placement="right" hasArrow>
            <div className={`flex items-center gap-3.5 py-[11px] text-base font-medium text-muted opacity-70 ${itemPad}`}>
              <Icon size={22} strokeWidth={2} />
              {!narrow && (
                <>
                  <span className="flex-1">{label}</span>
                  <span className="mr-5 rounded-full bg-bg px-2 py-0.5 text-[11px] font-bold">Soon</span>
                </>
              )}
            </div>
          </Tooltip>
        ))}
      </nav>

      <div className="flex-1" />

      {narrow ? (
        <Tooltip label={simBtn} placement="right" hasArrow>
          <button
            type="button"
            onClick={toggleRun}
            aria-label={simBtn}
            className="mx-auto mb-6 flex h-12 w-12 cursor-pointer items-center justify-center rounded-full bg-brand-grad text-white"
          >
            {running ? <Pause size={18} fill="currentColor" strokeWidth={0} /> : <Play size={18} fill="currentColor" strokeWidth={0} />}
          </button>
        </Tooltip>
      ) : (
        <div className="relative mx-5 mb-6 flex flex-col gap-1.5 overflow-hidden rounded-[20px] bg-hero-grad p-5 text-white">
          <div className="absolute -right-10 -top-[50px] h-[120px] w-[120px] rounded-full bg-white/[.12]" />
          <div className="text-xs font-medium opacity-80">Simulator</div>
          <div className="text-[17px] font-bold">{simTitle}</div>
          <div className="text-[13px] leading-snug opacity-85">{simText}</div>
          {progressText && (
            <div className="relative mt-1 flex flex-col gap-1.5">
              <div className="h-1.5 overflow-hidden rounded-full bg-white/25">
                <div className="h-1.5 rounded-full bg-white transition-[width] duration-700" style={{ width: `${((progress ?? 0) * 100).toFixed(2)}%` }} />
              </div>
              <div className="flex items-center justify-between gap-2 text-xs opacity-85">
                <span className="font-mono">{progressText}</span>
                {!!sim?.position && (
                  <Tooltip label="Rewind the replay to the first transaction" placement="top" hasArrow>
                    <button type="button" onClick={restartReplay} aria-label="Restart replay" className="flex h-6 w-6 cursor-pointer items-center justify-center rounded-full hover:bg-white/20">
                      <RotateCcw size={14} strokeWidth={2.2} />
                    </button>
                  </Tooltip>
                )}
              </div>
            </div>
          )}
          <button
            type="button"
            onClick={toggleRun}
            disabled={!inApp}
            className="relative mt-2.5 h-10 cursor-pointer rounded-full bg-white text-sm font-bold text-[#2F3FE8] hover:bg-[#EEF0FF] disabled:cursor-default disabled:opacity-60"
          >
            {simBtn}
          </button>
        </div>
      )}
    </aside>
  );
}
