import React from 'react';
import { ShieldIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';

export const SafetyStatusCard: React.FC = () => {
  const { overview } = useSystemOverview();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <ShieldIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionLabel}>SAFETY & PERMISSIONS GUARDRAILS</span>
        </div>
        <span style={styles.activePill}>ACTIVE ENFORCEMENT</span>
      </div>

      <div style={styles.safetyGrid}>
        {overview.safetyStatuses.map((item) => (
          <div key={item.id} style={styles.safetyItem}>
            <div style={styles.itemHeader}>
              <span style={styles.itemName}>{item.name}</span>
              <span
                style={{
                  ...styles.statusTag,
                  backgroundColor:
                    item.status === 'ACTIVE'
                      ? 'rgba(37, 99, 235, 0.08)'
                      : item.status === 'READY' || item.status === 'AVAILABLE'
                      ? 'var(--bg-green-soft)'
                      : 'rgba(239, 68, 68, 0.08)',
                  color:
                    item.status === 'ACTIVE'
                      ? 'var(--accent-primary)'
                      : item.status === 'READY' || item.status === 'AVAILABLE'
                      ? '#166534'
                      : '#991b1b',
                }}
              >
                {item.label}
              </span>
            </div>
            {item.detail && <span style={styles.itemDetail}>{item.detail}</span>}
          </div>
        ))}
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
  activePill: {
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    backgroundColor: 'rgba(37, 99, 235, 0.08)',
    padding: '2px 6px',
    borderRadius: '4px',
    letterSpacing: '0.03em',
  },
  safetyGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  safetyItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    padding: '6px 8px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
  },
  itemHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '6px',
  },
  itemName: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  statusTag: {
    fontSize: '9.5px',
    fontWeight: 700,
    padding: '1px 6px',
    borderRadius: '4px',
  },
  itemDetail: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
};
