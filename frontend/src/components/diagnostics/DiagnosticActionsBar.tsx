import React from 'react';
import { useDiagnostics } from '../../context/DiagnosticsContext';
import {
  ClipboardCopyIcon,
  RefreshIcon,
  CheckCircleIcon,
  SettingsIcon,
  ShieldIcon,
} from '../icons/Icons';

interface DiagnosticActionsBarProps {
  onNavigateTab?: (tab: string) => void;
}

export const DiagnosticActionsBar: React.FC<DiagnosticActionsBarProps> = ({ onNavigateTab }) => {
  const { runDiagnostics, copyDiagnosticSummary, isProbing, copiedToast } = useDiagnostics();

  return (
    <div style={styles.card}>
      <div style={styles.titleRow}>
        <span style={styles.title}>Diagnostic Actions</span>
        {copiedToast && (
          <div style={styles.toast}>
            <CheckCircleIcon size={12} color="var(--accent-green)" />
            <span>Sanitized summary copied to clipboard</span>
          </div>
        )}
      </div>

      <div style={styles.btnGrid}>
        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => copyDiagnosticSummary()}
          title="Copy sanitized system health report for troubleshooting (zero secrets/tokens)"
        >
          <ClipboardCopyIcon size={14} color="var(--accent-primary)" />
          <span>Copy Health Report</span>
        </button>

        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => runDiagnostics()}
          disabled={isProbing}
          title="Probe all hardware and runtime subsystems"
        >
          <RefreshIcon
            size={14}
            color="var(--accent-primary)"
            style={{
              animation: isProbing ? 'spin 1s linear infinite' : 'none',
            }}
          />
          <span>{isProbing ? 'Probing...' : 'Refresh Telemetry'}</span>
        </button>
      </div>

      {onNavigateTab && (
        <div style={styles.navRow}>
          <button
            type="button"
            style={styles.navLinkBtn}
            onClick={() => onNavigateTab('settings')}
          >
            <SettingsIcon size={12} color="var(--text-muted)" />
            <span>Preferences</span>
          </button>
          <div style={styles.navDivider} />
          <button
            type="button"
            style={styles.navLinkBtn}
            onClick={() => onNavigateTab('security')}
          >
            <ShieldIcon size={12} color="var(--text-muted)" />
            <span>Security Gates</span>
          </button>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    boxShadow: 'var(--shadow-card)',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: '20px',
  },
  title: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    animation: 'fadeIn 0.2s ease',
  },
  btnGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '8px',
  },
  actionBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding: '7px 8px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    color: 'var(--text-primary)',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  navRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '12px',
    paddingTop: '4px',
    borderTop: '1px solid var(--border-subtle)',
  },
  navLinkBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: '10.5px',
    cursor: 'pointer',
    padding: '2px 4px',
    transition: 'color var(--transition-fast)',
  },
  navDivider: {
    width: 1,
    height: 12,
    backgroundColor: 'var(--border-subtle)',
  },
};
