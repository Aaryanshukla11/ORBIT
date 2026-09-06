import React from 'react';
import { ActivityTabIcon, ChevronRightIcon, CheckCircleIcon, XCircleIcon, AlertTriangleIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';
import { useActivityHistory } from '../../context/ActivityHistoryContext';
import { ExecutionRecord } from '../../types/activity';

interface RecentActivityCardProps {
  onNavigateToActivity?: () => void;
}

export const RecentActivityCard: React.FC<RecentActivityCardProps> = ({ onNavigateToActivity }) => {
  const { recentActivities } = useSystemOverview();
  const { selectExecution } = useActivityHistory();

  const formatRelativeTime = (timestamp: string) => {
    try {
      const diffMs = Date.now() - new Date(timestamp).getTime();
      const diffSec = Math.max(0, Math.floor(diffMs / 1000));
      if (diffSec < 60) return `${diffSec}s ago`;
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      return `${diffHr}h ago`;
    } catch {
      return '';
    }
  };

  const formatDuration = (ms: number) => {
    if (!ms || ms <= 0) return '';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    const sec = (ms / 1000).toFixed(1);
    return `${sec}s`;
  };

  const renderStatusIcon = (status: string) => {
    switch (status) {
      case 'COMPLETED':
        return <CheckCircleIcon size={14} color="var(--accent-green)" />;
      case 'FAILED':
        return <XCircleIcon size={14} color="var(--accent-red)" />;
      case 'CANCELLED':
        return <AlertTriangleIcon size={14} color="var(--text-muted)" />;
      case 'RUNNING':
      case 'REPLANNING':
        return <span style={styles.runningDot} />;
      default:
        return <span style={styles.idleDot} />;
    }
  };

  const handleItemClick = (record: ExecutionRecord) => {
    selectExecution(record.execution_id);
    if (onNavigateToActivity) {
      onNavigateToActivity();
    }
  };

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <ActivityTabIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionLabel}>RECENT ACTIVITY</span>
        </div>
        {onNavigateToActivity && (
          <button
            type="button"
            style={styles.viewAllBtn}
            onClick={onNavigateToActivity}
          >
            <span>Full History</span>
            <ChevronRightIcon size={12} color="var(--accent-primary)" />
          </button>
        )}
      </div>

      {recentActivities.length > 0 ? (
        <div style={styles.activityList}>
          {recentActivities.map((rec) => (
            <div
              key={rec.execution_id}
              style={styles.activityItem}
              onClick={() => handleItemClick(rec)}
              title="Click to inspect task detail in Activity view"
            >
              <div style={styles.iconCol}>{renderStatusIcon(rec.status)}</div>

              <div style={styles.infoCol}>
                <span style={styles.goalText}>{rec.goal}</span>
                <div style={styles.metaRow}>
                  <span style={styles.timeText}>{formatRelativeTime(rec.started_at)}</span>
                  {rec.duration_ms > 0 && <span style={styles.durText}>• {formatDuration(rec.duration_ms)}</span>}
                  {rec.active_model && <span style={styles.modelTag}>{rec.active_model.split(':')[0]}</span>}
                </div>
              </div>

              <ChevronRightIcon size={13} color="var(--text-muted)" />
            </div>
          ))}
        </div>
      ) : (
        <div style={styles.emptyState}>
          <p style={styles.emptyText}>No historical executions recorded yet.</p>
          <span style={styles.emptyHint}>Completed and running tasks will appear here automatically.</span>
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
  viewAllBtn: {
    background: 'none',
    border: 'none',
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    cursor: 'pointer',
  },
  activityList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  activityItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 8px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    cursor: 'pointer',
    transition: 'background-color var(--transition-fast)',
  },
  iconCol: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  infoCol: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  goalText: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  timeText: {
    color: 'var(--text-muted)',
  },
  durText: {
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  modelTag: {
    padding: '0 4px',
    borderRadius: '3px',
    backgroundColor: 'var(--border-default)',
    color: 'var(--text-secondary)',
    fontSize: '9px',
    fontWeight: 600,
  },
  runningDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
  },
  idleDot: {
    width: '8px',
    height: '8px',
    borderRadius: '50%',
    backgroundColor: 'var(--text-muted)',
  },
  emptyState: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    padding: '8px 0',
  },
  emptyText: {
    fontSize: '11.5px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    margin: 0,
  },
  emptyHint: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
};
