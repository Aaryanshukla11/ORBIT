import React from 'react';
import { Task, TaskStatus, TaskExecutionStage } from '../../types/task';
import { TerminalIcon, CheckCircleIcon, XCircleIcon, AlertTriangleIcon, RefreshIcon } from '../icons/Icons';
import { useOrbit } from '../../context/OrbitContext';

interface TaskExecutionCardProps {
  task: Task;
}

const STAGES: TaskExecutionStage[] = [
  'UNDERSTANDING',
  'PLANNING',
  'READY',
  'EXECUTING',
  'VERIFYING',
  'COMPLETED',
];

export const TaskExecutionCard: React.FC<TaskExecutionCardProps> = ({ task }) => {
  const { activeModel } = useOrbit();

  // Map TaskStatus to Stage progression
  const getActiveStage = (status: TaskStatus): TaskExecutionStage => {
    switch (status) {
      case 'CREATED':
      case 'QUEUED':
        return 'UNDERSTANDING';
      case 'VALIDATING':
        return 'PLANNING';
      case 'READY':
        return 'READY';
      case 'RUNNING':
        return 'EXECUTING';
      case 'VERIFYING':
        return 'VERIFYING';
      case 'COMPLETED':
        return 'COMPLETED';
      case 'FAILED':
        return 'FAILED';
      case 'CANCELLED':
        return 'CANCELLED';
      default:
        return 'UNDERSTANDING';
    }
  };

  const currentStage = getActiveStage(task.status);
  const isFailed = task.status === 'FAILED' || task.status === 'CANCELLED';
  const isCompleted = task.status === 'COMPLETED';

  const totalSteps = task.plan?.steps.length ?? 0;
  const currentStep = task.current_step_index + 1;

  return (
    <div className="card" style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div style={styles.titleRow}>
          <TerminalIcon size={16} color="var(--accent-primary)" />
          <span style={styles.taskLabel}>ACTIVE TASK</span>
          <span style={styles.taskIdMono}>#{task.task_id.substring(0, 8)}</span>
        </div>

        <div style={styles.statusBadgeRow}>
          <span className={`badge ${
            isCompleted ? 'badge-online' :
            isFailed ? 'badge-error' : 'badge-busy'
          }`}>
            {task.status}
          </span>
        </div>
      </div>

      {/* Prompt / Instruction */}
      <div style={styles.promptBox}>
        <span style={styles.promptLabel}>INSTRUCTION:</span>
        <div style={styles.promptText}>{task.prompt}</div>
      </div>

      {/* Stage Progression Bar */}
      <div style={styles.stageTimeline}>
        <div style={styles.stagesRow}>
          {STAGES.map((stage, idx) => {
            const stageIndex = STAGES.indexOf(currentStage);
            const isStageActive = currentStage === stage;
            const isStageDone = !isFailed && stageIndex > idx;
            const isStageFailed = isFailed && (stage === 'FAILED' || stage === 'CANCELLED');

            return (
              <React.Fragment key={stage}>
                <div style={styles.stageNode}>
                  <div style={{
                    ...styles.stageCircle,
                    borderColor: isStageDone || (isCompleted && stage === 'COMPLETED')
                      ? 'var(--status-online)'
                      : isStageActive
                      ? 'var(--accent-primary)'
                      : 'var(--border-default)',
                    backgroundColor: isStageDone || (isCompleted && stage === 'COMPLETED')
                      ? 'var(--status-online-subtle)'
                      : isStageActive
                      ? 'var(--accent-primary-subtle)'
                      : 'var(--bg-input)',
                    color: isStageDone || (isCompleted && stage === 'COMPLETED')
                      ? 'var(--status-online)'
                      : isStageActive
                      ? 'var(--accent-primary)'
                      : 'var(--text-muted)',
                  }}>
                    {isStageDone || (isCompleted && stage === 'COMPLETED') ? (
                      <CheckCircleIcon size={11} />
                    ) : (
                      <span style={{ fontSize: '9px', fontWeight: 700 }}>{idx + 1}</span>
                    )}
                  </div>
                  <span style={{
                    ...styles.stageLabel,
                    color: isStageActive ? 'var(--text-primary)' : 'var(--text-muted)',
                    fontWeight: isStageActive ? 700 : 500,
                  }}>
                    {stage}
                  </span>
                </div>
                {idx < STAGES.length - 1 && (
                  <div style={{
                    ...styles.stageConnector,
                    backgroundColor: stageIndex > idx ? 'var(--status-online)' : 'var(--border-subtle)',
                  }} />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Telemetry Metrics Row */}
      <div style={styles.metricsRow}>
        <div style={styles.metricItem}>
          <span style={styles.metricKey}>PLAN PROGRESS:</span>
          <span style={styles.metricVal}>
            {totalSteps > 0 ? `Step ${currentStep} of ${totalSteps}` : 'Formulating Plan...'}
          </span>
        </div>

        <div style={styles.metricItem}>
          <span style={styles.metricKey}>ACTIVE MODEL:</span>
          <span style={styles.metricValMono}>
            {activeModel ? activeModel.modelId : 'Standby'}
          </span>
        </div>

        {task.error && (
          <div style={styles.errorBanner}>
            <XCircleIcon size={14} color="var(--status-error)" />
            <span>{task.error.message}</span>
          </div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
    padding: 'var(--space-4)',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    boxShadow: 'var(--shadow-sm)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 'var(--space-2)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  taskLabel: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.06em',
    color: 'var(--text-secondary)',
  },
  taskIdMono: {
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    color: 'var(--accent-primary)',
  },
  statusBadgeRow: {
    display: 'flex',
    alignItems: 'center',
  },
  promptBox: {
    padding: 'var(--space-2) var(--space-3)',
    backgroundColor: 'var(--bg-input)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
  },
  promptLabel: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  promptText: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-primary)',
    fontWeight: 500,
    marginTop: '2px',
    lineHeight: 1.4,
  },
  stageTimeline: {
    padding: 'var(--space-2) 0',
  },
  stagesRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    width: '100%',
  },
  stageNode: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '4px',
    zIndex: 1,
  },
  stageCircle: {
    width: 20,
    height: 20,
    borderRadius: '50%',
    border: '1.5px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'all var(--transition-fast)',
  },
  stageLabel: {
    fontSize: '9.5px',
    letterSpacing: '0.02em',
    textAlign: 'center',
  },
  stageConnector: {
    flex: 1,
    height: 2,
    margin: '0 4px',
    marginBottom: '14px',
    transition: 'background var(--transition-fast)',
  },
  metricsRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: 'var(--space-2)',
    borderTop: '1px solid var(--border-subtle)',
    fontSize: '11px',
  },
  metricItem: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  metricKey: {
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  metricVal: {
    color: 'var(--text-secondary)',
  },
  metricValMono: {
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-primary)',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    color: 'var(--status-error)',
    fontSize: '11px',
  },
};
