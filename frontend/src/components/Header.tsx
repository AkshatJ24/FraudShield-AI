import { useColorMode } from '@chakra-ui/react';
import { Eye, Moon, Sun } from 'lucide-react';
import { useFraudShield, useNow } from '../state/FraudShield';
import { GitHubLink } from './ui';

export function Header({ title }: { title: string }) {
  const { phase, running, txs, truth, toggleTruth, streamStatus } = useFraudShield();
  const { colorMode, toggleColorMode } = useColorMode();
  const now = useNow(1000);
  const inApp = phase === 'app';
  const rate = (txs.filter((t) => now - t.ts < 10000).length / 10).toFixed(1);
  const live = inApp && running && streamStatus === 'open';
  const label = !inApp ? 'Connecting…' : streamStatus === 'reconnecting' ? 'Reconnecting…' : running ? `Live · ${rate} tx/s` : 'Paused';
  const light = colorMode === 'light';

  return (
    <header className="flex flex-wrap items-end justify-between gap-4">
      <div className="flex flex-col gap-1">
        <div className="text-sm font-medium text-muted2">Pages / {title}</div>
        <h1 className="text-[34px] font-bold leading-tight tracking-[-.02em]">{title}</h1>
      </div>

      <div className="flex flex-wrap items-center gap-2.5 rounded-full bg-card p-2 shadow-card">
        <div className="flex h-10 items-center gap-2 whitespace-nowrap rounded-full bg-bg px-4 text-sm font-medium" aria-live="polite">
          <span className={`h-2 w-2 rounded-full ${live ? 'animate-blink bg-brand' : 'bg-muted'}`} />
          {label}
        </div>
        <button
          type="button"
          onClick={toggleTruth}
          aria-pressed={truth}
          className={`flex h-10 cursor-pointer items-center gap-2 whitespace-nowrap rounded-full px-3.5 text-sm font-medium ${truth ? 'bg-brand text-white' : 'text-muted2 hover:text-ink'}`}
        >
          <Eye size={18} strokeWidth={2} />
          Ground truth
        </button>
        <GitHubLink />
        <button
          type="button"
          onClick={toggleColorMode}
          aria-label={light ? 'Switch to dark mode' : 'Switch to light mode'}
          className="relative mx-1.5 h-8 w-[62px] flex-none cursor-pointer rounded-full bg-brand"
        >
          <span
            className={`absolute left-[3px] top-[3px] flex h-[26px] w-[26px] items-center justify-center rounded-full bg-white text-[#2F3FE8] transition-transform duration-200 ${light ? 'translate-x-[30px]' : 'translate-x-0'}`}
          >
            {light ? <Sun size={16} strokeWidth={2.2} /> : <Moon size={15} strokeWidth={2.2} />}
          </span>
        </button>
      </div>
    </header>
  );
}
