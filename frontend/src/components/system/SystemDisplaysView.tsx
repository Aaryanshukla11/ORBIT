import React, { useState } from 'react';
import { SystemHeader } from './SystemHeader';
import { DisplayOverview } from './DisplayOverview';
import { WorkspaceContextCard } from './WorkspaceContextCard';
import { CapabilitiesList } from './CapabilitiesList';
import { SystemResourceCard } from './SystemResourceCard';
import { RunningAppContext } from './RunningAppContext';
import { SystemHealthFooter } from './SystemHealthFooter';
import { DiagnosticsView } from '../diagnostics/DiagnosticsView';
import { SystemIcon, PulseHeartIcon } from '../icons/Icons';
import { TabId } from '../navigation/HorizontalNav';

interface SystemDisplaysViewProps {
  onNavigateTab?: (tab: TabId) => void;
  initialSubTab?: 'displays' | 'health';
}

export const SystemDisplaysView: React.FC<SystemDisplaysViewProps> = ({
  onNavigateTab,
  initialSubTab = 'displays',
}) => {
  const [subTab, setSubTab] = useState<'displays' | 'health'>(initialSubTab);

  return (
    <div style={styles.container}>
      {/* 1. Compact Header */}
      <div style={styles.headerWrapper}>
        <SystemHeader />
      </div>

      {/* 2. Sub-tab Navigation (Displays vs Health) */}
      <div style={styles.subNavWrapper}>
        <div style={styles.subNavGroup}>
          <button
            type="button"
            style={{
              ...styles.subTabBtn,
              backgroundColor: subTab === 'displays' ? 'var(--bg-surface)' : 'transparent',
              color: subTab === 'displays' ? 'var(--accent-primary)' : 'var(--text-secondary)',
              fontWeight: subTab === 'displays' ? 700 : 500,
              boxShadow: subTab === 'displays' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setSubTab('displays')}
          >
            <SystemIcon size={13} color={subTab === 'displays' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
            <span>Displays & Hardware</span>
          </button>

          <button
            type="button"
            style={{
              ...styles.subTabBtn,
              backgroundColor: subTab === 'health' ? 'var(--bg-surface)' : 'transparent',
              color: subTab === 'health' ? 'var(--accent-primary)' : 'var(--text-secondary)',
              fontWeight: subTab === 'health' ? 700 : 500,
              boxShadow: subTab === 'health' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setSubTab('health')}
          >
            <PulseHeartIcon size={13} color={subTab === 'health' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
            <span>Subsystem Health & Diagnostics</span>
          </button>
        </div>
      </div>

      {/* 3. Section Body Content */}
      {subTab === 'displays' ? (
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
      ) : (
        <DiagnosticsView onNavigateTab={onNavigateTab} />
      )}
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
    width: '100%',
    height: '100%',
  },
  headerWrapper: {
    padding: '0 18px',
    flexShrink: 0,
  },
  subNavWrapper: {
    padding: '4px 18px 8px 18px',
    display: 'flex',
    alignItems: 'center',
    flexShrink: 0,
    borderBottom: '1px solid var(--border-subtle)',
  },
  subNavGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
    gap: '2px',
  },
  subTabBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 12px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '11px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
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
