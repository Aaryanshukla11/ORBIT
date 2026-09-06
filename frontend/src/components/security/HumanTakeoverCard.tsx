import React, { useState } from 'react';
import { useSecurity } from '../../context/SecurityContext';
import { ShieldIcon, StopIcon, CheckCircleIcon } from '../icons/Icons';

export const HumanTakeoverCard: React.FC = () => {
  const { safetyState, triggerEmergencyStop } = useSecurity();
  const [isHalted, setIsHalted] = useState(false);

  const handleStop = async () => {
    setIsHalted(true);
    await triggerEmergencyStop();
  };

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <ShieldIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>HUMAN TAKEOVER & FAIL-SAFE</span>
        </div>
        <span style={styles.guardPill}>
          <CheckCircleIcon size={10} color="var(--accent-green)" />
          {safetyState.guardStatus}
        </span>
      </div>

      <div style={styles.grid}>
        <div style={styles.gridItem}>
          <span style={styles.label}>Takeover Guard:</span>
          <span style={{ ...styles.value, color: 'var(--accent-green)' }}>
            {safetyState.activeTakeoverPreempting ? 'Operator Preempted' : 'Armed (Low-Level Hooks)'}
          </span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Watchdog Timer:</span>
          <span style={styles.value}>Active (Heartbeat OK)</span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Physical Lockout:</span>
          <span style={styles.value}>Hardware Sanitized</span>
        </div>

        <div style={styles.gridItem}>
          <span style={styles.label}>Preemption Policy:</span>
          <span style={styles.value}>Immediate Human Priority</span>
        </div>
      </div>

      <div style={styles.actionStrip}>
        <button
          type="button"
          style={{
            ...styles.emergencyBtn,
            backgroundColor: isHalted ? 'var(--accent-red)' : 'var(--bg-surface)',
            color: isHalted ? '#ffffff' : 'var(--accent-red)',
          }}
          onClick={handleStop}
        >
          <StopIcon size={12} color="currentColor" />
          <span>{isHalted ? 'Emergency Stop Engaged' : 'Trigger Emergency Fail-Safe Stop'}</span>
        </button>
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
  guardPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
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
  value: {
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  actionStrip: {
    marginTop: '4px',
  },
  emergencyBtn: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding: '6px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--accent-red)',
    fontSize: '11px',
    fontWeight: 700,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
