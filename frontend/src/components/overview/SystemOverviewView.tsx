import React from 'react';
import { SystemStatusHeader } from './SystemStatusHeader';
import { QuickActionsBar } from './QuickActionsBar';
import { CurrentOrbitStateCard } from './CurrentOrbitStateCard';
import { AttentionRequiredCard } from './AttentionRequiredCard';
import { ActiveModelCard } from './ActiveModelCard';
import { SystemConnectionsCard } from './SystemConnectionsCard';
import { SafetyStatusCard } from './SafetyStatusCard';
import { RecentActivityCard } from './RecentActivityCard';
import { TabId } from '../navigation/HorizontalNav';

interface SystemOverviewViewProps {
  onNavigateTab: (tab: TabId) => void;
}

export const SystemOverviewView: React.FC<SystemOverviewViewProps> = ({ onNavigateTab }) => {
  return (
    <div style={styles.container}>
      {/* 1. Header with Live Status */}
      <SystemStatusHeader />

      {/* 2. Vertically Scrollable Content Area */}
      <div style={styles.scrollArea}>
        {/* Quick Actions Bar */}
        <QuickActionsBar onNavigateTab={onNavigateTab} />

        {/* Current Activity Card */}
        <CurrentOrbitStateCard onNavigateToChat={() => onNavigateTab('chat')} />

        {/* Attention Required (Rendered when needed) */}
        <AttentionRequiredCard onNavigateTab={onNavigateTab} />

        {/* Active AI Model */}
        <ActiveModelCard onNavigateToModels={() => onNavigateTab('models')} />

        {/* System Connections Status */}
        <SystemConnectionsCard />

        {/* Safety & Permissions State */}
        <SafetyStatusCard onNavigateToSecurity={() => onNavigateTab('security')} />

        {/* Recent Genuine Activity */}
        <RecentActivityCard onNavigateToActivity={() => onNavigateTab('activity')} />
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 18px 24px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
};
