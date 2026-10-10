import { useEffect, useState } from 'react';
import { useColorMode } from '@chakra-ui/react';
import { config } from './config';
import { useFraudShield } from './state/FraudShield';
import { StartScreen } from './components/StartScreen';
import { Sidebar, type Page } from './components/Sidebar';
import { Header } from './components/Header';
import { BootPipeline } from './components/BootPipeline';
import { TransactionDrawer } from './components/TransactionDrawer';
import { Overview } from './pages/Overview';
import { LiveFeed } from './pages/LiveFeed';
import { MetricsPage } from './pages/Metrics';

export default function App() {
  const { phase } = useFraudShield();
  const { colorMode } = useColorMode();
  const [page, setPage] = useState<Page>('overview');

  useEffect(() => {
    document.documentElement.dataset.theme = colorMode;
    document.documentElement.dataset.dec = config.decisionColors;
  }, [colorMode]);

  if (phase === 'start' || phase === 'leaving') return <StartScreen />;

  const inApp = phase === 'app';
  const TITLES: Record<Page, string> = { overview: 'Overview', feed: 'Live Feed', metrics: 'Metrics' };
  const title = inApp ? TITLES[page] : 'Overview';

  return (
    <div className="flex min-h-screen animate-slide-in">
      <Sidebar page={page} onNavigate={setPage} />
      <main className="flex min-w-0 flex-1 flex-col gap-5 px-7 pb-10 pt-[22px]">
        <Header title={title} />
        {!inApp ? <BootPipeline /> : page === 'overview' ? <Overview onViewAll={() => setPage('feed')} /> : page === 'feed' ? <LiveFeed /> : <MetricsPage />}
      </main>
      <TransactionDrawer />
    </div>
  );
}
