import React from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  SystemIcon,
  ShieldIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
} from '../components/icons/Icons';

export const SystemMonitorPage: React.FC = () => {
  const { connectionState, systemHealth } = useOrbit();
  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>System Diagnostics & Display Topology</h1>
          <p style={styles.description}>
            Win32 coordinate translation, low-level mouse/keyboard hook watchdog, and system health telemetry.
          </p>
        </div>
      </div>

      {/* Grid */}
      <div style={styles.grid}>
        {/* Watchdog & Safety Subsystem Card */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <ShieldIcon size={18} color="var(--accent-primary)" />
              <h3 style={styles.cardTitle}>Win32 Subsystem Health</h3>
            </div>
            <span className={`badge ${systemHealth.watchdogActive ? 'badge-online' : 'badge-offline'}`}>
              {systemHealth.watchdogActive ? 'Watchdog Online' : 'Standby'}
            </span>
          </div>

          <div style={styles.metricList}>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>Pointer Hook Guard</span>
              <span className={`badge ${isConnected ? 'badge-online' : 'badge-offline'}`}>
                {isConnected ? 'Active (Win32 SendInput)' : 'Offline'}
              </span>
            </div>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>Keyboard Injection Guard</span>
              <span className={`badge ${isConnected ? 'badge-online' : 'badge-offline'}`}>
                {isConnected ? 'Active (Scan Codes)' : 'Offline'}
              </span>
            </div>
            <div style={styles.metricItem}>
              <span style={styles.metricLabel}>Human Preemption Guard</span>
              <span className={`badge ${systemHealth.takeoverArmed ? 'badge-warning' : 'badge-online'}`}>
                {systemHealth.takeoverArmed ? 'Takeover Armed' : 'Monitoring'}
              </span>
            </div>
          </div>
        </div>

        {/* Display Coordinates Card */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <SystemIcon size={18} color="var(--accent-cyan)" />
              <h3 style={styles.cardTitle}>Virtual Screen & Topology</h3>
            </div>
            <span className="badge badge-online">Primary Display</span>
          </div>

          <div style={styles.topologyInfo}>
            <p style={styles.topologyText}>
              ORBIT utilizes sub-pixel precise normalized bounding box grounding translated to Win32 screen coordinates.
            </p>
            <div style={styles.metricList}>
              <div style={styles.metricItem}>
                <span style={styles.metricLabel}>Virtual Screen Coordinates</span>
                <span style={styles.monoValue}>Normalized [0.0, 1.0] $\leftrightarrow$ Physical Px</span>
              </div>
              <div style={styles.metricItem}>
                <span style={styles.metricLabel}>DPI Scaling Compensation</span>
                <span style={styles.monoValue}>Win32 Per-Monitor V2 DPI-Aware</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
    maxWidth: 1400,
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 'var(--font-size-2xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-1)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: 'var(--space-5)',
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 'var(--space-3)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  cardTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  cardTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  metricList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  metricItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 'var(--space-2) 0',
    borderBottom: '1px solid var(--border-subtle)',
  },
  metricLabel: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-secondary)',
  },
  monoValue: {
    fontSize: 'var(--font-size-xs)',
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-cyan)',
  },
  topologyInfo: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  topologyText: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: 1.5,
  },
};
