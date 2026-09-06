import React from 'react';
import { useSecurity } from '../../context/SecurityContext';
import { HistoryIcon, ShieldIcon } from '../icons/Icons';

export const SecurityAuditTrail: React.FC = () => {
  const { auditEvents } = useSecurity();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <HistoryIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>SECURITY AUDIT TRAIL</span>
        </div>
        <span style={styles.countBadge}>{auditEvents.length} Recorded</span>
      </div>

      {auditEvents.length === 0 ? (
        <div style={styles.emptyState}>
          <span>No security audit events recorded in this session.</span>
        </div>
      ) : (
        <div style={styles.auditList}>
          {auditEvents.map((evt) => {
            let badgeBg = 'var(--accent-green-subtle)';
            let badgeColor = 'var(--accent-green)';
            if (evt.result === 'BLOCKED' || evt.result === 'DENIED') {
              badgeBg = 'var(--accent-red-subtle)';
              badgeColor = 'var(--accent-red)';
            } else if (evt.result === 'PREEMPTED') {
              badgeBg = 'var(--accent-primary-subtle)';
              badgeColor = 'var(--accent-primary)';
            }

            return (
              <div key={evt.id} style={styles.auditItem}>
                <div style={styles.itemTop}>
                  <span style={styles.actionText}>{evt.action}</span>
                  <span style={{ ...styles.resultBadge, backgroundColor: badgeBg, color: badgeColor }}>
                    {evt.result}
                  </span>
                </div>

                <div style={styles.targetRow}>
                  <span style={styles.targetText}>Target: {evt.target}</span>
                  <span style={styles.timeText}>{evt.timestamp}</span>
                </div>

                {evt.details && <span style={styles.detailText}>{evt.details}</span>}
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
  countBadge: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  emptyState: {
    padding: '16px',
    textAlign: 'center',
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  auditList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    maxHeight: '220px',
    overflowY: 'auto',
  },
  auditItem: {
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '7px 9px',
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  itemTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  actionText: {
    fontSize: '11.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  resultBadge: {
    fontSize: '8.5px',
    fontWeight: 700,
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
  targetRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  targetText: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  timeText: {
    flexShrink: 0,
  },
  detailText: {
    fontSize: '10px',
    color: 'var(--text-secondary)',
    lineHeight: 1.3,
  },
};
