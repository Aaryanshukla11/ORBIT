import React from 'react';
import { RefreshIcon } from '../icons/Icons';
import { useSystem } from '../../context/SystemContext';

export const SystemHeader: React.FC = () => {
  const { refreshSystemState, isLoading, healthSummary } = useSystem();

  return (
    <div style={styles.header}>
      <div style={styles.leftGroup}>
        <h2 style={styles.title}>System & Displays</h2>
        <span style={styles.subtitle}>Windows Environment & Topology</span>
      </div>

      <div style={styles.rightGroup}>
        <button
          type="button"
          onClick={refreshSystemState}
          style={styles.refreshBtn}
          title="Scan Displays & Hardware"
        >
          <RefreshIcon size={14} color="var(--text-muted)" />
        </button>

        <span style={styles.statusBadge}>
          <span style={styles.statusDot} />
          {isLoading ? 'Scanning...' : 'System Ready'}
        </span>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 0 12px 0',
    borderBottom: '1px solid var(--border-subtle)',
    userSelect: 'none',
  },
  leftGroup: {
    display: 'flex',
    flexDirection: 'column',
  },
  title: {
    fontSize: '14px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    marginTop: '1px',
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  refreshBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 26,
    height: 26,
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--bg-surface)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '2px 8px',
    borderRadius: 'var(--radius-full)',
    backgroundColor: 'var(--accent-green-subtle)',
    color: 'var(--accent-green)',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    fontSize: '10.5px',
    fontWeight: 700,
    letterSpacing: '0.02em',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
  },
};
