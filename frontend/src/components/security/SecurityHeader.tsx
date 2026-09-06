import React, { useState } from 'react';
import { SecurityIcon, ShieldIcon, StopIcon } from '../icons/Icons';
import { useSecurity } from '../../context/SecurityContext';

export const SecurityHeader: React.FC = () => {
  const { safetyState, triggerEmergencyStop } = useSecurity();
  const [stopTriggered, setStopTriggered] = useState(false);

  const handleEmergencyStop = async () => {
    setStopTriggered(true);
    await triggerEmergencyStop();
    setTimeout(() => {
      setStopTriggered(false);
    }, 2500);
  };

  return (
    <div style={styles.header}>
      <div style={styles.leftGroup}>
        <div style={styles.titleRow}>
          <SecurityIcon size={16} color="var(--accent-primary)" />
          <h2 style={styles.title}>Security & Safety</h2>
        </div>
        <span style={styles.subtitle}>Permissions & Autonomous Access</span>
      </div>

      <div style={styles.rightGroup}>
        <button
          type="button"
          style={{
            ...styles.emergencyBtn,
            backgroundColor: stopTriggered ? 'var(--accent-red)' : 'var(--bg-surface)',
            color: stopTriggered ? '#ffffff' : 'var(--accent-red)',
          }}
          onClick={handleEmergencyStop}
          title="Emergency Stop: Halt all autonomous tasks immediately"
        >
          <StopIcon size={12} color="currentColor" />
          <span>{stopTriggered ? 'STOPPING' : 'Stop'}</span>
        </button>

        <span style={styles.statusBadge}>
          <span style={styles.statusDot} />
          {safetyState.activeTakeoverPreempting ? 'Preempted' : 'Protection Active'}
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
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
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
  emergencyBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 7px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--accent-red)',
    fontSize: '10.5px',
    fontWeight: 700,
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
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
  },
};
