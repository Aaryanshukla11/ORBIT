import React, { useState } from 'react';
import { useDiagnostics } from '../../context/DiagnosticsContext';
import { StructuredIssue } from '../../types/diagnostics';
import {
  AlertTriangleIcon,
  XCircleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronRightIcon,
} from '../icons/Icons';

export const RecentIssuesSection: React.FC = () => {
  const { report } = useDiagnostics();
  const [expandedIssueId, setExpandedIssueId] = useState<string | null>(null);

  const issues: StructuredIssue[] = report?.issues || [];

  const toggleExpand = (id: string) => {
    setExpandedIssueId((prev) => (prev === id ? null : id));
  };

  const getSeverityStyle = (severity: string) => {
    switch (severity) {
      case 'CRITICAL':
        return {
          label: 'Critical',
          color: 'var(--accent-rose)',
          bg: 'var(--accent-rose-subtle)',
          icon: XCircleIcon,
        };
      case 'WARNING':
        return {
          label: 'Warning',
          color: '#f59e0b',
          bg: '#fef3c7',
          icon: AlertTriangleIcon,
        };
      default:
        return {
          label: 'Notice',
          color: 'var(--accent-primary)',
          bg: 'var(--accent-primary-subtle)',
          icon: AlertTriangleIcon,
        };
    }
  };

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <span style={styles.title}>Active Issues & Anomalies</span>
        <span
          style={{
            ...styles.badge,
            backgroundColor: issues.length > 0 ? '#fef3c7' : 'var(--accent-green-subtle)',
            color: issues.length > 0 ? '#b45309' : 'var(--accent-green)',
          }}
        >
          {issues.length > 0 ? `${issues.length} Issues Found` : '0 Active Issues'}
        </span>
      </div>

      {issues.length === 0 ? (
        <div style={styles.emptyState}>
          <CheckCircleIcon size={18} color="var(--accent-green)" />
          <div style={styles.emptyText}>
            <div style={styles.emptyTitle}>All Systems Verified Nominal</div>
            <div style={styles.emptyDesc}>
              No active runtime faults, lockouts, or unhandled exceptions detected.
            </div>
          </div>
        </div>
      ) : (
        <div style={styles.issuesList}>
          {issues.map((iss) => {
            const isExpanded = expandedIssueId === iss.issue_id;
            const sev = getSeverityStyle(iss.severity);
            const Icon = sev.icon;

            return (
              <div key={iss.issue_id} style={styles.issueCard}>
                <div
                  style={styles.issueHeader}
                  onClick={() => toggleExpand(iss.issue_id)}
                >
                  <div style={styles.issueLeft}>
                    <Icon size={15} color={sev.color} />
                    <div style={styles.issueTitleWrap}>
                      <div style={styles.issueTitle}>{iss.title}</div>
                      <div style={styles.issueSubsystem}>
                        Subsystem: {iss.subsystem}
                      </div>
                    </div>
                  </div>

                  <div style={styles.issueRight}>
                    <span
                      style={{
                        ...styles.sevPill,
                        backgroundColor: sev.bg,
                        color: sev.color,
                      }}
                    >
                      {sev.label}
                    </span>
                    {isExpanded ? (
                      <ChevronDownIcon size={13} color="var(--text-muted)" />
                    ) : (
                      <ChevronRightIcon size={13} color="var(--text-muted)" />
                    )}
                  </div>
                </div>

                <div style={styles.issueBody}>
                  <div style={styles.issueDesc}>{iss.description}</div>
                  {iss.remediation && (
                    <div style={styles.remediationBox}>
                      <span style={styles.remediationLabel}>Remediation:</span>{' '}
                      <span style={styles.remediationText}>{iss.remediation}</span>
                    </div>
                  )}
                </div>

                {/* Optional Technical Details Drawer */}
                {isExpanded && iss.technical_details && (
                  <div style={styles.techDrawer}>
                    <div style={styles.techTitle}>Diagnostic Trace / Evidence:</div>
                    <pre style={styles.techPre}>{iss.technical_details}</pre>
                  </div>
                )}
              </div>
            );
          })}
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
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '2px',
  },
  title: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  badge: {
    fontSize: '10px',
    fontWeight: 600,
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
  },
  emptyState: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
  },
  emptyText: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
  },
  emptyTitle: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  emptyDesc: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    lineHeight: 1.3,
  },
  issuesList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  issueCard: {
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  issueHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    cursor: 'pointer',
    userSelect: 'none',
    gap: '8px',
  },
  issueLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    minWidth: 0,
    flex: 1,
  },
  issueTitleWrap: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  issueTitle: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  issueSubsystem: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    marginTop: '1px',
  },
  issueRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  sevPill: {
    fontSize: '9.5px',
    fontWeight: 700,
    padding: '2px 5px',
    borderRadius: 'var(--radius-sm)',
    textTransform: 'uppercase',
  },
  issueBody: {
    padding: '0 10px 8px 10px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  issueDesc: {
    fontSize: '10.5px',
    color: 'var(--text-secondary)',
    lineHeight: 1.35,
  },
  remediationBox: {
    fontSize: '10px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-sm)',
    padding: '4px 6px',
    lineHeight: 1.3,
  },
  remediationLabel: {
    fontWeight: 700,
    color: 'var(--accent-primary)',
  },
  remediationText: {
    color: 'var(--text-primary)',
  },
  techDrawer: {
    padding: '8px 10px',
    backgroundColor: '#0f172a',
    borderTop: '1px solid var(--border-subtle)',
    color: '#e2e8f0',
  },
  techTitle: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: '#94a3b8',
    marginBottom: '4px',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  techPre: {
    margin: 0,
    fontSize: '10px',
    fontFamily: 'monospace',
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-all',
    color: '#38bdf8',
  },
};
