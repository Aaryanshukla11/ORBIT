import React from 'react';
import { CheckCircleIcon, XCircleIcon, AlertTriangleIcon, ChevronRightIcon } from '../icons/Icons';
import { useActivityHistory } from '../../context/ActivityHistoryContext';
import { ExecutionRecord } from '../../types/activity';

export const ExecutionTimeline: React.FC = () => {
  const { records, filter, searchQuery, selectExecution } = useActivityHistory();

  // Apply filters and search
  const filteredRecords = records.filter((r) => {
    // 1. Status Filter
    if (filter === 'RUNNING' && r.status !== 'RUNNING' && r.status !== 'REPLANNING') return false;
    if (filter === 'COMPLETED' && r.status !== 'COMPLETED') return false;
    if (filter === 'FAILED' && r.status !== 'FAILED') return false;
    if (filter === 'CANCELLED' && r.status !== 'CANCELLED') return false;

    // 2. Search Query
    if (searchQuery && searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const inGoal = r.goal.toLowerCase().includes(q);
      const inModel = r.active_model ? r.active_model.toLowerCase().includes(q) : false;
      const inApp = r.applications_involved.some((a) => a.toLowerCase().includes(q));
      const inStatus = r.status.toLowerCase().includes(q);
      if (!inGoal && !inModel && !inApp && !inStatus) return false;
    }

    return true;
  });

  const formatRelativeTime = (timestamp: string) => {
    try {
      const diffMs = Date.now() - new Date(timestamp).getTime();
      const diffSec = Math.max(0, Math.floor(diffMs / 1000));
      if (diffSec < 60) return `${diffSec}s ago`;
      const diffMin = Math.floor(diffSec / 60);
      if (diffMin < 60) return `${diffMin}m ago`;
      const diffHr = Math.floor(diffMin / 60);
      if (diffHr < 24) return `${diffHr}h ago`;
      const diffDays = Math.floor(diffHr / 24);
      return `${diffDays}d ago`;
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
        return <CheckCircleIcon size={15} color="var(--accent-green)" />;
      case 'FAILED':
        return <XCircleIcon size={15} color="var(--accent-red)" />;
      case 'CANCELLED':
        return <AlertTriangleIcon size={15} color="var(--text-muted)" />;
      case 'RUNNING':
      case 'REPLANNING':
        return <span style={styles.runningDot} />;
      default:
        return <span style={styles.idleDot} />;
    }
  };

  if (filteredRecords.length === 0) {
    return (
      <div style={styles.emptyContainer}>
        {searchQuery ? (
          <>
            <p style={styles.emptyTitle}>No matching search results</p>
            <span style={styles.emptyHint}>No executions found for "{searchQuery}".</span>
          </>
        ) : filter !== 'ALL' ? (
          <>
            <p style={styles.emptyTitle}>No {filter.toLowerCase()} tasks</p>
            <span style={styles.emptyHint}>There are no tasks with status '{filter}'.</span>
          </>
        ) : (
          <>
            <p style={styles.emptyTitle}>No execution history</p>
            <span style={styles.emptyHint}>Tasks executed by ORBIT will be persisted and listed here.</span>
          </>
        )}
      </div>
    );
  }

  return (
    <div style={styles.list}>
      {filteredRecords.map((rec) => (
        <div
          key={rec.execution_id}
          style={styles.itemCard}
          onClick={() => selectExecution(rec.execution_id)}
          title="Click to view detailed plan, steps, and diagnostics"
        >
          <div style={styles.leftCol}>{renderStatusIcon(rec.status)}</div>

          <div style={styles.centerCol}>
            <span style={styles.goalText}>{rec.goal}</span>

            <div style={styles.metaRow}>
              <span style={styles.timeText}>{formatRelativeTime(rec.started_at)}</span>
              {rec.duration_ms > 0 && <span style={styles.durText}>• {formatDuration(rec.duration_ms)}</span>}
              {rec.active_model && <span style={styles.tag}>{rec.active_model.split(':')[0]}</span>}
              {rec.applications_involved.length > 0 && (
                <span style={styles.tag}>{rec.applications_involved[0]}</span>
              )}
            </div>
          </div>

          <div style={styles.rightCol}>
            <span
              style={{
                ...styles.statusBadge,
                backgroundColor:
                  rec.status === 'COMPLETED'
                    ? 'var(--bg-green-soft)'
                    : rec.status === 'FAILED'
                    ? 'rgba(239, 68, 68, 0.08)'
                    : rec.status === 'CANCELLED'
                    ? 'var(--bg-app)'
                    : 'rgba(37, 99, 235, 0.08)',
                color:
                  rec.status === 'COMPLETED'
                    ? '#166534'
                    : rec.status === 'FAILED'
                    ? '#991b1b'
                    : rec.status === 'CANCELLED'
                    ? 'var(--text-muted)'
                    : 'var(--accent-primary)',
              }}
            >
              {rec.status}
            </span>
            <ChevronRightIcon size={12} color="var(--text-muted)" />
          </div>
        </div>
      ))}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  itemCard: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    padding: '8px 10px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    boxShadow: 'var(--shadow-card)',
    transition: 'all var(--transition-fast)',
  },
  leftCol: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  centerCol: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  goalText: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.3,
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
    flexWrap: 'wrap',
  },
  timeText: {
    color: 'var(--text-muted)',
  },
  durText: {
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  tag: {
    padding: '0 4px',
    borderRadius: '3px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    fontSize: '9px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  rightCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    flexShrink: 0,
  },
  statusBadge: {
    fontSize: '9px',
    fontWeight: 700,
    padding: '1px 5px',
    borderRadius: '4px',
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
  emptyContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    padding: '24px 12px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    textAlign: 'center',
  },
  emptyTitle: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    margin: 0,
  },
  emptyHint: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
};
