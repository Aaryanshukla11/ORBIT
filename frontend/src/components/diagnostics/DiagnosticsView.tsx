import React from 'react';
import { DiagnosticSummaryHeader } from './DiagnosticSummaryHeader';
import { SubsystemHealthList } from './SubsystemHealthList';
import { RecentIssuesSection } from './RecentIssuesSection';
import { DiagnosticActionsBar } from './DiagnosticActionsBar';

interface DiagnosticsViewProps {
  onNavigateTab?: (tab: string) => void;
}

export const DiagnosticsView: React.FC<DiagnosticsViewProps> = ({ onNavigateTab }) => {
  return (
    <div style={styles.container}>
      <div style={styles.scrollArea}>
        {/* 1. Overall Diagnostic Health Header */}
        <DiagnosticSummaryHeader />

        {/* 2. Subsystem Health Breakdown (8 Live Subsystems) */}
        <SubsystemHealthList />

        {/* 3. Active Issues & Structured Failures */}
        <RecentIssuesSection />

        {/* 4. Diagnostic Actions & Copy Report */}
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
