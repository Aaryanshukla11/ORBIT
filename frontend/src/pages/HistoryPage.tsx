import React from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  HistoryIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
} from '../components/icons/Icons';

export const HistoryPage: React.FC = () => {
  const { connectionState } = useOrbit();
  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Execution History & Audit Trail</h1>
          <p style={styles.description}>
            Historical task logs, multi-step plan outcomes, and session telemetry replays.
          </p>
        </div>
      </div>

      {/* History Card */}
      <div className="card" style={styles.historyCard}>
        <div style={styles.emptyState}>
          <HistoryIcon size={36} color="var(--text-muted)" />
          <div style={styles.emptyTitle}>Session History Ready</div>
          <p style={styles.emptySubtitle}>
            {isConnected
              ? 'Past task executions from current and prior sessions will appear here as tasks are completed.'
              : 'Connect to ORBIT Gateway to retrieve execution history logs.'}
          </p>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
    maxWidth: 1400,
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 'var(--font-size-2xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-1)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
  },
  historyCard: {
    padding: 'var(--space-10)',
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-3)',
    textAlign: 'center',
  },
  emptyTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  emptySubtitle: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-muted)',
    maxWidth: 420,
  },
};
