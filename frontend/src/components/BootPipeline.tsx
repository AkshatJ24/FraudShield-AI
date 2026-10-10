import { Fragment } from 'react';
import { Cpu, Database, Radio, Server, type LucideIcon } from 'lucide-react';
import { config } from '../config';
import { useFraudShield } from '../state/FraudShield';

const NODES: { label: string; icon: LucideIcon }[] = [
  { label: 'FastAPI', icon: Server },
  { label: 'Model', icon: Cpu },
  { label: 'PostgreSQL', icon: Database },
  { label: 'SSE stream', icon: Radio },
];
const MESSAGES = [
  'Calling GET /health…',
  'Loading LightGBM model and calibrator…',
  'Connecting to PostgreSQL…',
  'Opening SSE stream at /stream…',
  'All systems ready',
];
const NODE_STYLE = {
  done: 'bg-brand-grad text-white border-transparent shadow-[0_12px_26px_rgba(47,63,232,.32)]',
  active: 'bg-card text-brand border-brand animate-pulse-ring',
  error: 'bg-card text-[var(--error)] border-[var(--error)]',
  idle: 'bg-bg text-muted border-line',
};

export function BootPipeline() {
  const { bootStep, bootDetails, bootError, retryBoot } = useFraudShield();
  const stateOf = (i: number) => (bootError?.step === i ? 'error' : bootStep > i ? 'done' : bootStep === i && !bootError ? 'active' : 'idle');
  const detailOf = (i: number, s: keyof typeof NODE_STYLE) => (s === 'done' ? bootDetails[i] : s === 'active' ? 'connecting…' : s === 'error' ? 'failed' : 'waiting');

  return (
    <div className="flex min-h-[62vh] flex-1 items-center justify-center">
      <div className="fs-card flex w-full max-w-[860px] animate-fade-up-late flex-col gap-[34px] rounded-[28px] px-12 py-11">
        <div className="flex flex-col gap-1.5">
          <h2 className="text-[26px] font-bold tracking-[-.02em]">{bootError ? 'Startup stopped' : 'Connecting to FraudShield'}</h2>
          <p className="text-base text-muted2">{bootError ? bootError.message : MESSAGES[Math.min(4, bootStep)]}</p>
        </div>

        <div className="flex items-start">
          {NODES.map(({ label, icon: Icon }, i) => {
            const s = stateOf(i);
            return (
              <Fragment key={label}>
                {i > 0 && (
                  <div className="mt-8 h-1 flex-1 overflow-hidden rounded-sm bg-line">
                    <div className={`h-1 bg-brand-grad transition-[width] duration-700 ease-out ${bootStep >= i ? 'w-full' : 'w-0'}`} />
                  </div>
                )}
                <div className="flex w-24 flex-none flex-col items-center gap-2.5">
                  <div className={`flex h-[68px] w-[68px] items-center justify-center rounded-full border-2 transition-all duration-300 ${NODE_STYLE[s]}`}>
                    <Icon size={28} strokeWidth={2} />
                  </div>
                  <div className="text-[15px] font-bold">{label}</div>
                  <div className="text-center font-mono text-xs text-muted">{detailOf(i, s)}</div>
                </div>
              </Fragment>
            );
          })}
        </div>

        {bootError ? (
          <div className="flex flex-wrap items-center justify-between gap-4 rounded-2xl bg-bg px-5 py-4">
            <div className="flex flex-col gap-1 text-sm text-muted2">
              <span>
                Is the API running at <span className="font-mono text-ink">{config.apiBase}</span>?
              </span>
              <span>
                To run without a backend, set <span className="font-mono text-ink">VITE_DATA_SOURCE=mock</span>.
              </span>
            </div>
            <button type="button" onClick={retryBoot} className="h-[42px] cursor-pointer rounded-full bg-brand-grad px-5 text-sm font-bold text-white">
              Retry
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2.5">
            <div className="h-2 overflow-hidden rounded bg-bg">
              <div className="h-2 rounded bg-brand-grad transition-[width] duration-700 ease-linear" style={{ width: `${(bootStep / 4) * 100}%` }} />
            </div>
            <div className="font-mono text-xs text-muted">GET /health → model → GET /health/db → GET /stream</div>
          </div>
        )}
      </div>
    </div>
  );
}
