import React from 'react';
import { AlertTriangleIcon, CheckCircleIcon, ChevronRightIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';
import { AttentionItem } from '../../types/systemOverview';
import { TabId } from '../navigation/HorizontalNav';

interface AttentionRequiredCardProps {
  onNavigateTab?: (tab: TabId) => void;
}

export const AttentionRequiredCard: React.FC<AttentionRequiredCardProps> = ({ onNavigateTab }) => {
  const { overview } = useSystemOverview();
  const items = overview.attentionItems;
  const hasIssues = items.length > 0;

  const handleAction = (item: AttentionItem) => {
    if (item.actionTab && onNavigateTab) {
      onNavigateTab(item.actionTab as TabId);
    }
  };

  return (
    <div
      style={{
        ...styles.card,
        borderColor: hasIssues ? 'rgba(239, 68, 68, 0.3)' : 'var(--border-default)',
        backgroundColor: hasIssues ? 'rgba(239, 68, 68, 0.02)' : 'var(--bg-surface)',
      }}
    >
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          {hasIssues ? (
            <AlertTriangleIcon size={14} color="var(--accent-red)" />
          ) : (
            <CheckCircleIcon size={14} color="var(--accent-green)" />
          )}
          <span
            style={{
              ...styles.sectionLabel,
              color: hasIssues ? '#b91c1c' : 'var(--text-muted)',
            }}
          >
            {hasIssues ? 'ATTENTION REQUIRED' : 'SYSTEM HEALTH'}
          </span>
        </div>

        <span
          style={{
            ...styles.countBadge,
            backgroundColor: hasIssues ? 'rgba(239, 68, 68, 0.1)' : 'var(--bg-green-soft)',
            color: hasIssues ? '#b91c1c' : '#166534',
          }}
        >
          {hasIssues ? `${items.length} ${items.length === 1 ? 'Issue' : 'Issues'}` : 'Nominal'}
        </span>
      </div>

      {hasIssues ? (
        <div style={styles.itemsList}>
          {items.map((item) => (
            <div key={item.id} style={styles.issueItem}>
              <div style={styles.issueHeader}>
                <span style={styles.issueTitle}>{item.title}</span>
                {item.actionLabel && (
                  <button
                    type="button"
                    style={styles.actionBtn}
                    onClick={() => handleAction(item)}
                  >
                    <span>{item.actionLabel}</span>
                    <ChevronRightIcon size={11} color="var(--accent-primary)" />
                  </button>
                )}
              </div>
              <p style={styles.issueDesc}>{item.description}</p>
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.cleanState}>
          <span style={styles.cleanText}>All services and telemetry operating within expected parameters.</span>
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
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
    letterSpacing: '0.05em',
  },
  countBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    padding: '1px 6px',
    borderRadius: '4px',
  },
  itemsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  issueItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    padding: '8px 10px',
    backgroundColor: 'var(--bg-surface)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
  },
  issueHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '6px',
  },
  issueTitle: {
    fontSize: '11.5px',
    fontWeight: 700,
    color: '#991b1b',
  },
  actionBtn: {
    background: 'none',
    border: 'none',
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '2px',
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    cursor: 'pointer',
  },
  issueDesc: {
    fontSize: '10.5px',
    color: 'var(--text-secondary)',
    margin: 0,
    lineHeight: 1.35,
  },
  cleanState: {
    padding: '2px 0',
  },
  cleanText: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
  },
};
