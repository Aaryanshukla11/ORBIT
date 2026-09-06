import React from 'react';
import { ActivityHeader } from './ActivityHeader';
import { CurrentRunningTaskCard } from './CurrentRunningTaskCard';
import { ActivityFilters } from './ActivityFilters';
import { ExecutionTimeline } from './ExecutionTimeline';
import { ExecutionDetailView } from './ExecutionDetailView';
import { useActivityHistory } from '../../context/ActivityHistoryContext';

export const ActivityView: React.FC = () => {
  const { selectedExecution } = useActivityHistory();

  if (selectedExecution) {
    return <ExecutionDetailView />;
  }

  return (
    <div style={styles.container}>
      {/* 1. Header with Task Counters */}
      <ActivityHeader />

      {/* 2. Scrollable Body */}
      <div style={styles.scrollArea}>
        {/* Active Task Execution Card */}
        <CurrentRunningTaskCard />

        {/* Filters and Search Bar */}
        <ActivityFilters />

        {/* Historical Timeline List */}
        <ExecutionTimeline />
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
