import React from 'react';
import {
  ArrowLeftIcon,
  CheckCircleIcon,
  XCircleIcon,
  AlertTriangleIcon,
  CpuChipIcon,
  TerminalIcon,
  ShieldIcon,
  ActiveRadioCircleIcon,
  PendingCircleIcon,
} from '../icons/Icons';
import { useActivityHistory } from '../../context/ActivityHistoryContext';
import { ExecutionRecord, ExecutionStepRecord } from '../../types/activity';

export const ExecutionDetailView: React.FC = () => {
  const { selectedExecution, selectExecution } = useActivityHistory();

  if (!selectedExecution) return null;

  const rec: ExecutionRecord = selectedExecution;

  const formatDateTime = (iso: string) => {
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return iso;
    }
  };

  const formatDuration = (ms: number) => {
    if (!ms || ms <= 0) return 'In progress';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    const sec = (ms / 1000).toFixed(1);
    return `${sec}s`;
  };

  const renderStepIcon = (status: ExecutionStepRecord['status']) => {
    switch (status) {
      case 'COMPLETED':
        return <CheckCircleIcon size={14} color="var(--accent-green)" />;
      case 'ACTIVE':
        return <ActiveRadioCircleIcon size={14} />;
      case 'FAILED':
        return <XCircleIcon size={14} color="var(--accent-red)" />;
      case 'BLOCKED':
        return <AlertTriangleIcon size={14} color="#f59e0b" />;
      case 'PENDING':
      default:
        return <PendingCircleIcon size={14} />;
    }
  };

  return (
    <div style={styles.container}>
      {/* Top Header & Back Button */}
      <div style={styles.topBar}>
        <button
          type="button"
          style={styles.backBtn}
          onClick={() => selectExecution(null)}
          title="Back to timeline list"
        >
          <ArrowLeftIcon size={14} color="var(--accent-primary)" />
          <span>Back to List</span>
        </button>

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
      </div>

      <div style={styles.scrollArea}>
        {/* Goal Section */}
        <div style={styles.sectionCard}>
          <span style={styles.sectionLabel}>NATURAL LANGUAGE GOAL</span>
          <div style={styles.goalText}>"{rec.goal}"</div>
        </div>

        {/* Execution Metadata Grid */}
        <div style={styles.sectionCard}>
          <span style={styles.sectionLabel}>EXECUTION METRICS</span>
          <div style={styles.metaGrid}>
            <div style={styles.metaItem}>
              <span style={styles.metaKey}>Started</span>
              <span style={styles.metaVal}>{formatDateTime(rec.started_at)}</span>
            </div>

            <div style={styles.metaItem}>
              <span style={styles.metaKey}>Completed</span>
              <span style={styles.metaVal}>{rec.completed_at ? formatDateTime(rec.completed_at) : 'In progress'}</span>
            </div>

            <div style={styles.metaItem}>
              <span style={styles.metaKey}>Duration</span>
              <span style={styles.metaVal}>{formatDuration(rec.duration_ms)}</span>
            </div>

            <div style={styles.metaItem}>
              <span style={styles.metaKey}>Model Used</span>
              <span style={styles.metaVal}>{rec.active_model || 'Local Runtime'}</span>
            </div>
          </div>
        </div>

        {/* Applications Involved */}
        {rec.applications_involved.length > 0 && (
          <div style={styles.sectionCard}>
            <span style={styles.sectionLabel}>APPLICATIONS INVOLVED</span>
            <div style={styles.appsList}>
              {rec.applications_involved.map((app, idx) => (
                <div key={idx} style={styles.appTag}>
                  <TerminalIcon size={12} color="var(--accent-primary)" />
                  <span>{app}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Failure Diagnostics (if failed) */}
        {rec.status === 'FAILED' && (
          <div style={{ ...styles.sectionCard, borderColor: 'rgba(239, 68, 68, 0.3)', backgroundColor: 'rgba(239, 68, 68, 0.02)' }}>
            <span style={{ ...styles.sectionLabel, color: '#b91c1c' }}>FAILURE DIAGNOSTICS</span>
            <div style={styles.failContent}>
              <div style={styles.failReason}>
                <strong>Reason:</strong> {rec.failure_reason || 'Execution encountered an unrecoverable failure.'}
              </div>
              {rec.failure_code && (
                <div style={styles.failCode}>
                  <strong>Status Code:</strong> <code>{rec.failure_code}</code>
                </div>
              )}
              {rec.replanning_count > 0 && (
                <div style={styles.failNote}>
                  Dynamic replan attempted {rec.replanning_count} time(s) before stopping safely.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Plan Steps Sequence */}
        {rec.steps && rec.steps.length > 0 && (
          <div style={styles.sectionCard}>
            <div style={styles.stepHeaderRow}>
              <span style={styles.sectionLabel}>PLAN STEPS EXECUTION</span>
              <span style={styles.stepBadge}>
                {rec.steps_completed} of {rec.total_steps || rec.steps.length} Steps
              </span>
            </div>

            <div style={styles.stepsList}>
              {rec.steps.map((step, idx) => (
                <div key={step.step_id || idx} style={styles.stepRow}>
                  <div style={styles.stepIconWrap}>{renderStepIcon(step.status)}</div>
                  <div style={styles.stepInfo}>
                    <div style={styles.stepTop}>
                      <span style={styles.stepName}>{step.name}</span>
                      <span style={styles.stepStatusText}>{step.status}</span>
                    </div>
                    {step.action_type && (
                      <span style={styles.stepActionType}>Action: {step.action_type}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Replanning History */}
        {rec.replan_history && rec.replan_history.length > 0 && (
          <div style={styles.sectionCard}>
            <span style={styles.sectionLabel}>DYNAMIC REPLANNING AUDIT</span>
            <div style={styles.replanList}>
              {rec.replan_history.map((r, idx) => (
                <div key={r.replan_id || idx} style={styles.replanItem}>
                  <div style={styles.replanTop}>
                    <span style={styles.replanTitle}>Plan Revision #{idx + 1}</span>
                    <span style={styles.replanTime}>{formatDateTime(r.timestamp)}</span>
                  </div>
                  <div style={styles.replanReason}>
                    <strong>Reason:</strong> {r.reason}
                  </div>
                  {r.new_strategy && (
                    <div style={styles.replanStrategy}>
                      <strong>New Strategy:</strong> {r.new_strategy}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Verification Evidence (if completed) */}
        {rec.evidence && (
          <div style={styles.sectionCard}>
            <span style={styles.sectionLabel}>VERIFICATION EVIDENCE</span>
            <div style={styles.evidenceContent}>
              {rec.evidence.application_name && (
                <div style={styles.evidenceRow}>
                  <span style={styles.evKey}>Target Window:</span>
                  <span style={styles.evVal}>{rec.evidence.application_name}</span>
                </div>
              )}
              {rec.evidence.ocr_matched_text && (
                <div style={styles.evidenceRow}>
                  <span style={styles.evKey}>OCR Matched:</span>
                  <span style={styles.evVal}>"{rec.evidence.ocr_matched_text}"</span>
                </div>
              )}
              {rec.evidence.ocr_confidence != null && (
                <div style={styles.evidenceRow}>
                  <span style={styles.evKey}>OCR Confidence:</span>
                  <span style={styles.evVal}>{(rec.evidence.ocr_confidence * 100).toFixed(1)}%</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  topBar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    backgroundColor: 'var(--bg-surface)',
    borderBottom: '1px solid var(--border-default)',
  },
  backBtn: {
    background: 'none',
    border: 'none',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '11.5px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    cursor: 'pointer',
    padding: '4px 0',
  },
  statusBadge: {
    fontSize: '10px',
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: '6px',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  sectionCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    boxShadow: 'var(--shadow-card)',
  },
  sectionLabel: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.04em',
  },
  goalText: {
    fontSize: '12.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.35,
    wordBreak: 'break-word',
  },
  metaGrid: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '6px',
    marginTop: '2px',
  },
  metaItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
    backgroundColor: 'var(--bg-app)',
    padding: '5px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
  },
  metaKey: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    fontWeight: 600,
  },
  metaVal: {
    fontSize: '11px',
    color: 'var(--text-primary)',
    fontWeight: 600,
  },
  appsList: {
    display: 'flex',
    gap: '6px',
    flexWrap: 'wrap',
  },
  appTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 8px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-sm)',
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--text-primary)',
  },
  failContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    fontSize: '11px',
    color: 'var(--text-primary)',
  },
  failReason: {
    lineHeight: 1.35,
  },
  failCode: {
    color: 'var(--text-secondary)',
  },
  failNote: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
  stepHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  stepBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
  },
  stepsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    marginTop: '4px',
  },
  stepRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    padding: '5px 8px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
  },
  stepIconWrap: {
    marginTop: '2px',
    flexShrink: 0,
  },
  stepInfo: {
    flex: 1,
    minWidth: 0,
    display: 'flex',
    flexDirection: 'column',
    gap: '1px',
  },
  stepTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '6px',
  },
  stepName: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    wordBreak: 'break-word',
  },
  stepStatusText: {
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--text-muted)',
  },
  stepActionType: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
  },
  replanList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  replanItem: {
    padding: '6px 8px',
    backgroundColor: 'rgba(245, 158, 11, 0.05)',
    border: '1px solid rgba(245, 158, 11, 0.2)',
    borderRadius: 'var(--radius-sm)',
    fontSize: '10.5px',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  replanTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontWeight: 700,
    color: '#b45309',
  },
  replanTitle: {
    fontSize: '10.5px',
  },
  replanTime: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
  },
  replanReason: {
    color: 'var(--text-primary)',
  },
  replanStrategy: {
    color: 'var(--text-secondary)',
  },
  evidenceContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
    fontSize: '11px',
  },
  evidenceRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  evKey: {
    color: 'var(--text-muted)',
    fontWeight: 600,
    fontSize: '10.5px',
  },
  evVal: {
    color: 'var(--text-primary)',
    fontWeight: 500,
  },
};
