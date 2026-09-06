import React from 'react';
import { useModelManager } from '../../context/ModelManagerContext';
import { ServerIcon, ShieldIcon } from '../icons/Icons';

export const SystemModelStatus: React.FC = () => {
  const { systemStatus, activeModel } = useModelManager();

  return (
    <div style={styles.container}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <ServerIcon size={13} color="var(--text-muted)" />
          <span style={styles.title}>AI RUNTIME STATE</span>
        </div>
        <span style={styles.readyBadge}>SYSTEM STABLE</span>
      </div>

      <div style={styles.grid}>
        {/* Runtime State */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Runtime:</span>
          <span style={styles.itemValue}>{systemStatus.runtimeState}</span>
        </div>

        {/* Active Provider */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Provider:</span>
          <span style={styles.itemValue}>
            {activeModel?.type === 'local' ? 'Local Runtime' : 'Cloud API'}
          </span>
        </div>

        {/* Model Availability */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Availability:</span>
          <span style={{ ...styles.itemValue, color: 'var(--accent-green)' }}>
            {systemStatus.modelAvailability}
          </span>
        </div>

        {/* Gateway Connection */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Gateway:</span>
          <span
            style={{
              ...styles.itemValue,
              color: systemStatus.gatewayConnection === 'Connected' ? 'var(--accent-green)' : 'var(--accent-red)',
            }}
          >
            {systemStatus.gatewayConnection}
          </span>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    boxShadow: 'var(--shadow-card)',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '6px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  title: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.06em',
  },
  readyBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    letterSpacing: '0.04em',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '6px 12px',
  },
  gridItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  itemLabel: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  itemValue: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
};
