import React from 'react';
import { SystemHeader } from './SystemHeader';
import { DisplayOverview } from './DisplayOverview';
import { WorkspaceContextCard } from './WorkspaceContextCard';
import { CapabilitiesList } from './CapabilitiesList';
import { SystemResourceCard } from './SystemResourceCard';
import { RunningAppContext } from './RunningAppContext';
import { SystemHealthFooter } from './SystemHealthFooter';

export const SystemDisplaysView: React.FC = () => {
  return (
    <div style={styles.container}>
      {/* 1. Compact Header */}
      <div style={styles.headerWrapper}>
        <SystemHeader />
      </div>

      {/* 2. Scrollable Section Body */}
      <div style={styles.scrollArea}>
        {/* Connected Displays Overview */}
        <DisplayOverview />

        {/* Desktop Awareness & Active Workspace */}
        <WorkspaceContextCard />

        {/* System Capabilities & Security */}
        <CapabilitiesList />

        {/* System Hardware & Runtime Resources */}
        <SystemResourceCard />

        {/* Running & Observed Application Context */}
        <RunningAppContext />

        {/* Bottom Health & Topology Summary */}
        <SystemHealthFooter />
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
  headerWrapper: {
    padding: '0 18px',
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
