import React from 'react';
import { ServerIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';

export const SystemConnectionsCard: React.FC = () => {
  const { overview } = useSystemOverview();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'CONNECTED':
      case 'READY':
        return 'var(--accent-green)';
      case 'BUSY':
        return 'var(--accent-primary)';
      case 'RECONNECTING':
        return '#f59e0b';
      case 'DISCONNECTED':
      case 'UNAVAILABLE':
      default:
        return 'var(--text-muted)';
    }
  };

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <ServerIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionLabel}>SYSTEM CONNECTIONS</span>
        </div>
        <span style={styles.originBadge}>LIVE</span>
      </div>

      <div style={styles.connectionsList}>
        {overview.connections.map((conn) => {
          const color = getStatusColor(conn.status);
          return (
            <div key={conn.id} style={styles.connRow}>
              <div style={styles.nameCol}>
                <span
                  style={{
                    ...styles.statusDot,
                    backgroundColor: color,
                  }}
                />
                <span style={styles.connName}>{conn.name}</span>
              </div>

              <div style={styles.statusCol}>
                <span style={styles.connLabel}>{conn.label}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  labelGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  sectionLabel: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  originBadge: {
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.02em',
  },
  connectionsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  connRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 8px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
  },
  nameCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  statusDot: {
    width: '7px',
    height: '7px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  connName: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  statusCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  connLabel: {
    fontSize: '10.5px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
};
