import React from 'react';
import { DiagnosticSummaryHeader } from './DiagnosticSummaryHeader';
import { AttentionRequiredCard } from './AttentionRequiredCard';
import { SubsystemHealthList } from './SubsystemHealthList';
import { SystemConnectionsCard } from './SystemConnectionsCard';
import { RecentIssuesSection } from './RecentIssuesSection';
import { DiagnosticActionsBar } from './DiagnosticActionsBar';
import { TabId } from '../navigation/HorizontalNav';

interface DiagnosticsViewProps {
  onNavigateTab?: (tab: TabId) => void;
}

export const DiagnosticsView: React.FC<DiagnosticsViewProps> = ({ onNavigateTab }) => {
  return (
    <div style={styles.container}>
      <div style={styles.scrollArea}>
        {/* 1. Overall Diagnostic Health Header */}
        <DiagnosticSummaryHeader />

        {/* 2. Attention Required / Active System Alert Banner */}
        <AttentionRequiredCard onNavigateTab={onNavigateTab} />

        {/* 3. Subsystem Health Breakdown (8 Live Subsystems) */}
        <SubsystemHealthList />

        {/* 4. Live System Connections & Socket Bridge States */}
        <SystemConnectionsCard />

        {/* 5. Active Issues & Structured Failures */}
        <RecentIssuesSection />

        {/* 6. Diagnostic Actions & Copy Report */}
        <DiagnosticActionsBar onNavigateTab={onNavigateTab} />
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
    width: '100%',
    height: '100%',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '10px 14px 24px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    scrollbarWidth: 'thin',
  },
};
