import React from 'react';
import { OrbitGradientLogo, RefreshIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';
import { useActivityHistory } from '../../context/ActivityHistoryContext';

export const SystemStatusHeader: React.FC = () => {
  const { overview } = useSystemOverview();
  const { refreshHistory, isLoading } = useActivityHistory();
  const isOnline = overview.isBackendConnected;

  return (
    <div style={styles.header}>
      <div style={styles.topRow}>
        <div style={styles.titleGroup}>
          <OrbitGradientLogo size={22} />
          <div>
            <h1 style={styles.title}>System Overview</h1>
            <p style={styles.subtitle}>ORBIT Autonomous Control Surface</p>
          </div>
        </div>

        <button
          type="button"
          style={{
            ...styles.refreshBtn,
            opacity: isLoading ? 0.6 : 1,
          }}
          onClick={() => refreshHistory()}
          title="Refresh System State"
        >
          <RefreshIcon size={14} color="var(--text-secondary)" />
        </button>
      </div>

      {/* State Summary Badge */}
      <div style={styles.badgeRow}>
        <div
          style={{
            ...styles.statusBadge,
            backgroundColor: isOnline ? 'var(--bg-green-soft)' : 'rgba(239, 68, 68, 0.08)',
            borderColor: isOnline ? 'rgba(34, 197, 94, 0.25)' : 'rgba(239, 68, 68, 0.25)',
          }}
        >
          <span
            style={{
              ...styles.statusDot,
              backgroundColor: isOnline ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          />
          <span
            style={{
              ...styles.statusText,
              color: isOnline ? '#166534' : '#991b1b',
            }}
          >
            {overview.stateLabel}
          </span>
        </div>

        <div style={styles.livePill}>
          <span style={styles.liveDot} />
          <span style={styles.liveText}>LIVE TELEMETRY</span>
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
    gap: '10px',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
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
    transition: 'all var(--transition-fast)',
    backgroundColor: 'var(--bg-app)',
  },
  badgeRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: '12px',
    border: '1px solid',
  },
  statusDot: {
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  statusText: {
    fontSize: '11.5px',
    fontWeight: 700,
    letterSpacing: '-0.01em',
  },
  livePill: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 8px',
    borderRadius: '6px',
    backgroundColor: 'rgba(37, 99, 235, 0.06)',
    border: '1px solid rgba(37, 99, 235, 0.15)',
  },
  liveDot: {
    width: '5px',
    height: '5px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
  },
  liveText: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    letterSpacing: '0.04em',
  },
};
