import React from 'react';
import { BotAutoIcon, CheckCircleIcon, CpuChipIcon } from '../icons/Icons';
import { useActivityHistory } from '../../context/ActivityHistoryContext';

export const CurrentRunningTaskCard: React.FC = () => {
  const { activeExecution } = useActivityHistory();

  if (!activeExecution) {
    return (
      <div style={styles.idleCard}>
        <div style={styles.idleHeader}>
          <CheckCircleIcon size={14} color="var(--accent-green)" />
          <span style={styles.idleTitle}>No Active Execution</span>
        </div>
        <p style={styles.idleText}>ORBIT is currently idle. When a task is started, live progress will appear here.</p>
      </div>
    );
  }

  const completed = activeExecution.steps_completed;
  const total = activeExecution.total_steps || activeExecution.steps.length || 1;
  const pct = Math.min(100, Math.round((completed / total) * 100));
  const activeStep = activeExecution.steps.find((s) => s.status === 'ACTIVE');

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <BotAutoIcon size={14} color="var(--accent-primary)" />
          <span style={styles.label}>LIVE EXECUTION</span>
        </div>
        <span style={styles.statusPill}>
          {activeExecution.status === 'REPLANNING' ? 'Replanning' : 'Executing'}
        </span>
      </div>

      <div style={styles.goalText}>"{activeExecution.goal}"</div>

      <div style={styles.progressContainer}>
        <div style={styles.progressTop}>
          <span style={styles.stepText}>
            Step {Math.min(total, completed + 1)} of {total}
          </span>
          <span style={styles.pctText}>{pct}%</span>
        </div>

        <div style={styles.track}>
          <div style={{ ...styles.fill, width: `${pct}%` }} />
        </div>

        {activeStep && (
          <div style={styles.activeStepRow}>
            <div style={styles.pulseDot} />
            <span style={styles.activeStepName}>{activeStep.name}</span>
          </div>
        )}
      </div>

      <div style={styles.metaRow}>
        {activeExecution.active_model && (
          <div style={styles.metaPill}>
            <CpuChipIcon size={11} color="var(--text-secondary)" />
            <span>{activeExecution.active_model}</span>
          </div>
        )}

        {activeExecution.applications_involved.length > 0 && (
          <div style={styles.metaPill}>
            <span>{activeExecution.applications_involved[0]}</span>
          </div>
        )}

        {activeExecution.replanning_count > 0 && (
          <div style={styles.replanPill}>
            <span>{activeExecution.replanning_count} Replans</span>
          </div>
        )}
      </div>
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
  idleCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  idleHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  idleTitle: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  idleText: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    margin: 0,
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
  label: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  statusPill: {
    fontSize: '10px',
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: '10px',
    backgroundColor: 'rgba(37, 99, 235, 0.08)',
    color: 'var(--accent-primary)',
    border: '1px solid rgba(37, 99, 235, 0.2)',
  },
  goalText: {
    fontSize: '12.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.35,
  },
  progressContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '5px',
    backgroundColor: 'var(--bg-app)',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
  },
  progressTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '11px',
    fontWeight: 600,
  },
  stepText: {
    color: 'var(--accent-primary)',
  },
  pctText: {
    color: 'var(--text-muted)',
  },
  track: {
    width: '100%',
    height: '5px',
    backgroundColor: 'var(--border-default)',
    borderRadius: '3px',
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    backgroundColor: 'var(--accent-primary)',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },
  activeStepRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    marginTop: '2px',
  },
  pulseDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
    flexShrink: 0,
  },
  activeStepName: {
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexWrap: 'wrap',
  },
  metaPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '2px 6px',
    borderRadius: '4px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    fontSize: '10px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  replanPill: {
    padding: '2px 6px',
    borderRadius: '4px',
    backgroundColor: 'rgba(245, 158, 11, 0.1)',
    border: '1px solid rgba(245, 158, 11, 0.25)',
    fontSize: '10px',
    color: '#b45309',
    fontWeight: 600,
  },
};
