import { Play, ShieldCheck } from 'lucide-react';
import { useFraudShield } from '../state/FraudShield';
import { GitHubLink } from './ui';

export function StartScreen() {
  const { phase, start } = useFraudShield();
  const leaving = phase === 'leaving';
  return (
    <div className={`fixed inset-0 flex items-center justify-center overflow-hidden p-8 ${leaving ? 'animate-slide-out' : 'animate-fade-up'}`}>
      <div className="glow-left pointer-events-none absolute -bottom-[260px] -left-[220px] h-[620px] w-[620px] rounded-full" />
      <div className="glow-right pointer-events-none absolute -right-[160px] -top-[200px] h-[520px] w-[520px] rounded-full" />
      <GitHubLink floating className="absolute right-6 top-6" />

      <div className="relative flex w-full max-w-[560px] flex-col items-center gap-[22px] text-center">
        <div className="flex h-[72px] w-[72px] items-center justify-center rounded-[22px] bg-brand-grad text-white shadow-[0_18px_40px_rgba(47,63,232,.30)]">
          <ShieldCheck size={34} strokeWidth={2} />
        </div>
        <div className="flex flex-col gap-2.5">
          <h1 className="text-5xl font-bold leading-none tracking-[-.025em]">FraudShield</h1>
          <p className="text-pretty max-w-[440px] text-lg leading-normal text-muted2">
            Real-time fraud scoring for payment transactions. Every decision comes with its reasons.
          </p>
        </div>
        <button
          type="button"
          onClick={start}
          disabled={leaving}
          className="flex h-[58px] cursor-pointer items-center gap-3 rounded-full bg-brand-grad pl-6 pr-[30px] text-[17px] font-bold text-white shadow-[0_18px_40px_rgba(47,63,232,.35)] transition-transform hover:-translate-y-0.5 active:translate-y-0"
        >
          <span className="flex h-[30px] w-[30px] items-center justify-center rounded-full bg-white/20">
            <Play size={14} fill="currentColor" strokeWidth={0} />
          </span>
          Start / Test
        </button>
        <div className="font-mono text-[13px] text-muted">POST /simulate/start · replays the holdout set through /score</div>
      </div>
    </div>
  );
}
