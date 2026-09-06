import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { ServerIcon } from '../icons/Icons';

export const SystemHealthFooter: React.FC = () => {
  const { healthSummary } = useSystem();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <ServerIcon size={13} color="var(--text-muted)" />
          <span style={styles.cardTitle}>SYSTEM TOPOLOGY HEALTH</span>
        </div>
        <span style={styles.statusPill}>ALL SERVICES OPERATIONAL</span>
      </div>

      <div style={styles.grid}>
        <div style={styles.gridItem}>
          <span style={styles.label}>System Gateway:</span>
          <span
            style={{
              ...styles.val,
              color: healthSummary.systemConnection === 'Connected' ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {healthSummary.systemConnection}
          </span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Desktop Observation:</span>
          <span style={{ ...styles.val, color: 'var(--accent-green)' }}>
            {healthSummary.desktopObservation}
          </span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Automation Layer:</span>
          <span style={{ ...styles.val, color: 'var(--accent-green)' }}>
            {healthSummary.automationLayer}
          </span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Display Access:</span>
          <span style={{ ...styles.val, color: 'var(--accent-green)' }}>
            {healthSummary.displayAccess}
          </span>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 12px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '4px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  cardTitle: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  statusPill: {
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--accent-green)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '4px 10px',
  },
  gridItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  label: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  val: {
    fontSize: '10.5px',
    fontWeight: 600,
  },
};
