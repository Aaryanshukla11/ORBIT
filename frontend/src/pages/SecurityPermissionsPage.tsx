import React from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  SecurityIcon,
  ShieldIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
} from '../components/icons/Icons';

export const SecurityPermissionsPage: React.FC = () => {
  const { connectionState, systemHealth } = useOrbit();
  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Security & Authorization Guardrails</h1>
          <p style={styles.description}>
            Zero-Trust autonomous execution policies, human takeover thresholds, and permission constraints.
          </p>
        </div>
      </div>

      {/* Policies Grid */}
      <div style={styles.grid}>
        {/* Zero Trust Verification Card */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <SecurityIcon size={18} color="var(--accent-primary)" />
              <h3 style={styles.cardTitle}>Zero-Trust Execution Policy</h3>
            </div>
            <span className="badge badge-online">Enforced</span>
          </div>

          <div style={styles.policyList}>
            <div style={styles.policyItem}>
              <CheckCircleIcon size={16} color="var(--status-online)" />
              <div>
                <div style={styles.policyTitle}>Pre-Action Bounds Validation</div>
                <div style={styles.policyDetail}>Every cursor movement and click is mathematically validated against screen limits.</div>
              </div>
            </div>

            <div style={styles.policyItem}>
              <CheckCircleIcon size={16} color="var(--status-online)" />
              <div>
                <div style={styles.policyTitle}>Atomic Plan Verification</div>
                <div style={styles.policyDetail}>Multi-step plans require deterministic verification before runtime execution.</div>
              </div>
            </div>

            <div style={styles.policyItem}>
              <CheckCircleIcon size={16} color="var(--status-online)" />
              <div>
                <div style={styles.policyTitle}>Sub-Millisecond Physical Lockout Release</div>
                <div style={styles.policyDetail}>Physical human mouse movement instantly preempts AI synthetic inputs.</div>
              </div>
            </div>
          </div>
        </div>

        {/* Permission Whitelist Card */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <ShieldIcon size={18} color="var(--status-warning)" />
              <h3 style={styles.cardTitle}>Application Permissions</h3>
            </div>
            <span className="badge badge-warning">Strict Sandbox</span>
          </div>

          <div style={styles.permList}>
            <div style={styles.permRow}>
              <span style={styles.permName}>Synthetic Pointer Injection</span>
              <span className="badge badge-online">Allowed (Win32)</span>
            </div>
            <div style={styles.permRow}>
              <span style={styles.permName}>Keyboard Virtual Scan Codes</span>
              <span className="badge badge-online">Allowed</span>
            </div>
            <div style={styles.permRow}>
              <span style={styles.permName}>Destructive Shell Execution</span>
              <span className="badge badge-error">Blocked by Default</span>
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
  policyList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  policyItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: 'var(--space-3)',
    padding: 'var(--space-3)',
    backgroundColor: 'var(--bg-surface-elevated)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
  },
  policyTitle: {
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  policyDetail: {
    fontSize: '11.5px',
    color: 'var(--text-muted)',
    marginTop: '2px',
  },
  permList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  permRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 'var(--space-2) 0',
    borderBottom: '1px solid var(--border-subtle)',
  },
  permName: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-secondary)',
  },
};
