import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { useModelManager } from '../../context/ModelManagerContext';
import { CpuChipIcon } from '../icons/Icons';

export const SystemResourceCard: React.FC = () => {
  const { systemInfo } = useSystem();
  const { activeModel } = useModelManager();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <CpuChipIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>SYSTEM HARDWARE & RUNTIME</span>
        </div>
        <span style={styles.platformBadge}>
          {systemInfo?.platform === 'win32' ? 'Windows 11/10 x64' : systemInfo?.platform || 'Windows'}
        </span>
      </div>

      <div style={styles.resourceGrid}>
        {/* CPU */}
        <div style={styles.rowItem}>
          <span style={styles.label}>Processor:</span>
          <span style={styles.value}>
            {systemInfo ? `${systemInfo.cpuModel} (${systemInfo.cpuCores} Cores)` : 'Unavailable'}
          </span>
        </div>

        {/* Total & Free Memory */}
        <div style={styles.rowItem}>
          <span style={styles.label}>System Memory:</span>
          <span style={styles.value}>
            {systemInfo
              ? `${systemInfo.totalMemory} Total (${systemInfo.freeMemory} Free)`
              : 'Unavailable'}
          </span>
        </div>

        {/* GPU Acceleration */}
        <div style={styles.rowItem}>
          <span style={styles.label}>Graphics Pipeline:</span>
          <span style={styles.value}>Hardware Direct3D 11 (Accelerated)</span>
        </div>

        {/* AI Runtime */}
        <div style={styles.rowItem}>
          <span style={styles.label}>Active AI Engine:</span>
          <span style={{ ...styles.value, color: 'var(--accent-primary)', fontWeight: 600 }}>
            {activeModel ? `${activeModel.name} (${activeModel.provider})` : 'Ready'}
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
    padding: '12px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
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
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  platformBadge: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
  },
  resourceGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  rowItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
    padding: '3px 0',
  },
  label: {
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--text-muted)',
    flexShrink: 0,
  },
  value: {
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    textAlign: 'right',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
};
