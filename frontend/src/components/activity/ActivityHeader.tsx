import React from 'react';
import { ActivityTabIcon, RefreshIcon } from '../icons/Icons';
import { useActivityHistory } from '../../context/ActivityHistoryContext';

export const ActivityHeader: React.FC = () => {
  const { totalCount, runningCount, completedCount, failedCount, refreshHistory, isLoading } = useActivityHistory();

  return (
    <div style={styles.header}>
      <div style={styles.topRow}>
        <div style={styles.titleGroup}>
          <ActivityTabIcon size={18} color="var(--accent-primary)" />
          <div>
            <h1 style={styles.title}>Execution History</h1>
            <p style={styles.subtitle}>Audit-Grade Activity Records</p>
          </div>
        </div>

        <button
          type="button"
          style={{
            ...styles.refreshBtn,
            opacity: isLoading ? 0.6 : 1,
          }}
          onClick={() => refreshHistory()}
          title="Refresh History from Backend"
        >
          <RefreshIcon size={14} color="var(--text-secondary)" />
        </button>
      </div>

      <div style={styles.summaryRow}>
        <span style={styles.totalBadge}>
          {totalCount} {totalCount === 1 ? 'Task' : 'Tasks'}
        </span>

        <div style={styles.statsGroup}>
          {runningCount > 0 && (
            <span style={styles.runningStat}>
              <span style={styles.runningDot} />
              {runningCount} Running
            </span>
          )}
          <span style={styles.completedStat}>{completedCount} Completed</span>
          {failedCount > 0 && <span style={styles.failedStat}>{failedCount} Failed</span>}
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    padding: '12px 18px 8px 18px',
    borderBottom: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  title: {
    fontSize: '15px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: 0,
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    margin: 0,
  },
  refreshBtn: {
    background: 'none',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '6px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'var(--bg-app)',
    transition: 'all var(--transition-fast)',
  },
  summaryRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  totalBadge: {
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--text-secondary)',
  },
  statsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '10.5px',
  },
  runningStat: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
  },
  runningDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
  },
  completedStat: {
    fontWeight: 600,
    color: '#166534',
  },
  failedStat: {
    fontWeight: 600,
    color: '#991b1b',
  },
};
