import React from 'react';
import { BotAutoIcon, CheckCircleIcon, StopIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';

interface CurrentOrbitStateCardProps {
  onNavigateToChat?: () => void;
}

export const CurrentOrbitStateCard: React.FC<CurrentOrbitStateCardProps> = ({ onNavigateToChat }) => {
  const { overview, stopCurrentTask } = useSystemOverview();
  const isExecuting = overview.operationalState === 'EXECUTING' || overview.operationalState === 'REPLANNING' || overview.operationalState === 'PLANNING';
  const progress = overview.activeTaskProgress;

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <BotAutoIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionLabel}>CURRENT ACTIVITY</span>
        </div>
        <span
          style={{
            ...styles.statePill,
            backgroundColor: isExecuting ? 'rgba(37, 99, 235, 0.08)' : 'var(--bg-app)',
            color: isExecuting ? 'var(--accent-primary)' : 'var(--text-muted)',
            borderColor: isExecuting ? 'rgba(37, 99, 235, 0.2)' : 'var(--border-default)',
          }}
        >
          {isExecuting ? overview.stateLabel : 'Idle & Ready'}
        </span>
      </div>

      {isExecuting ? (
        <div style={styles.activeContent}>
          <div style={styles.goalTitle}>"{overview.activeTaskPrompt || 'Autonomous Task'}"</div>

          {progress && (
            <div style={styles.progressSection}>
              <div style={styles.progressHeader}>
                <span style={styles.stepCount}>
                  Step {progress.current} of {progress.total}
                </span>
                <span style={styles.percentText}>
                  {Math.round((progress.current / Math.max(1, progress.total)) * 100)}%
                </span>
              </div>

              <div style={styles.progressBarTrack}>
                <div
                  style={{
                    ...styles.progressBarFill,
                    width: `${Math.min(100, Math.round((progress.current / Math.max(1, progress.total)) * 100))}%`,
                  }}
                />
              </div>

              {progress.stepName && (
                <div style={styles.currentStepRow}>
                  <div style={styles.pulseDot} />
                  <span style={styles.currentStepText}>{progress.stepName}</span>
                </div>
              )}
            </div>
          )}

          <div style={styles.activeActions}>
            <button
              type="button"
              style={styles.stopBtn}
              onClick={() => stopCurrentTask()}
              title="Stop current task execution"
            >
              <StopIcon size={13} color="#dc2626" />
              <span>Stop Task</span>
            </button>
            {onNavigateToChat && (
              <button
                type="button"
                style={styles.viewChatBtn}
                onClick={onNavigateToChat}
                title="View in Chat Console"
              >
                <span>View Console</span>
              </button>
            )}
          </div>
        </div>
      ) : (
        <div style={styles.idleContent}>
          <div style={styles.idleCheckRow}>
            <CheckCircleIcon size={16} color="var(--accent-green)" />
            <span style={styles.idleTitle}>ORBIT is ready for a new task.</span>
          </div>
          <p style={styles.idleSubtitle}>
            No autonomous execution active. Enter an instruction in Chat or launch an action to begin.
          </p>
          {onNavigateToChat && (
            <button
              type="button"
              style={styles.startBtn}
              onClick={onNavigateToChat}
            >
              Start New Task
            </button>
          )}
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
    gap: '10px',
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
  statePill: {
    fontSize: '10px',
    fontWeight: 700,
    padding: '2px 8px',
    borderRadius: '10px',
    border: '1px solid',
  },
  activeContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  goalTitle: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.35,
    wordBreak: 'break-word',
  },
  progressSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    backgroundColor: 'var(--bg-app)',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
  },
  progressHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  stepCount: {
    color: 'var(--accent-primary)',
  },
  percentText: {
    color: 'var(--text-muted)',
  },
  progressBarTrack: {
    width: '100%',
    height: '5px',
    backgroundColor: 'var(--border-default)',
    borderRadius: '3px',
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: 'var(--accent-primary)',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },
  currentStepRow: {
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
  currentStepText: {
    fontSize: '11px',
    color: 'var(--text-primary)',
    fontWeight: 500,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  activeActions: {
    display: 'flex',
    gap: '8px',
  },
  stopBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '5px 10px',
    backgroundColor: 'rgba(220, 38, 38, 0.08)',
    border: '1px solid rgba(220, 38, 38, 0.2)',
    borderRadius: 'var(--radius-md)',
    color: '#dc2626',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  viewChatBtn: {
    padding: '5px 10px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  idleContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  idleCheckRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '7px',
  },
  idleTitle: {
    fontSize: '12.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  idleSubtitle: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    margin: 0,
    lineHeight: 1.4,
  },
  startBtn: {
    alignSelf: 'flex-start',
    marginTop: '4px',
    padding: '5px 12px',
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
  },
};
