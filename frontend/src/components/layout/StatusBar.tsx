import React from 'react';
import { useOrbit } from '../../context/OrbitContext';

export const StatusBar: React.FC = () => {
  const { connectionState, gatewayUrl, systemHealth, telemetryLogs } = useOrbit();

  return (
    <footer style={styles.statusBar}>
      {/* Left items */}
      <div style={styles.leftGroup}>
        <div style={styles.item}>
          <span style={styles.label}>GATEWAY:</span>
          <span style={styles.value}>{gatewayUrl}</span>
        </div>
        <div style={styles.divider} />
        <div style={styles.item}>
          <span style={styles.label}>SESSION:</span>
          <span style={styles.value}>{systemHealth.activeSessionId || 'Unassigned'}</span>
        </div>
      </div>

      {/* Center items */}
      <div style={styles.centerGroup}>
        <div style={styles.item}>
          <span style={styles.label}>WATCHDOG:</span>
          <span style={{
            ...styles.value,
            color: systemHealth.watchdogActive ? 'var(--status-online)' : 'var(--text-muted)',
          }}>
            {systemHealth.watchdogActive ? 'ACTIVE' : 'STANDBY'}
          </span>
        </div>
        <div style={styles.divider} />
        <div style={styles.item}>
          <span style={styles.label}>TAKEOVER GUARD:</span>
          <span style={{
            ...styles.value,
            color: systemHealth.takeoverArmed ? 'var(--status-warning)' : 'var(--status-online)',
          }}>
            {systemHealth.takeoverArmed ? 'ARMED' : 'READY'}
          </span>
        </div>
      </div>

      {/* Right items */}
      <div style={styles.rightGroup}>
        <div style={styles.item}>
          <span style={styles.label}>LOGS:</span>
          <span style={styles.value}>{telemetryLogs.length} events</span>
        </div>
        <div style={styles.divider} />
        <div style={styles.item}>
          <span style={styles.shortcutTip}>Ctrl+1..8 Switch Views</span>
        </div>
      </div>
    </footer>
  );
};

const styles: Record<string, React.CSSProperties> = {
  statusBar: {
    height: 'var(--statusbar-height)',
    minHeight: 'var(--statusbar-height)',
    backgroundColor: 'var(--bg-surface)',
    borderTop: '1px solid var(--border-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-4)',
    fontSize: '11px',
    color: 'var(--text-muted)',
    userSelect: 'none',
    zIndex: 9,
  },
  leftGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  centerGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  item: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
  },
  label: {
    fontWeight: 600,
    letterSpacing: '0.04em',
    color: 'var(--text-muted)',
  },
  value: {
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-secondary)',
  },
  divider: {
    width: 1,
    height: 12,
    backgroundColor: 'var(--border-subtle)',
  },
  shortcutTip: {
    color: 'var(--text-muted)',
    fontSize: '10.5px',
  },
};
