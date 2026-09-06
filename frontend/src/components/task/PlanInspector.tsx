import React, { useState } from 'react';
import { ExecutionPlan, Step, ActionTier, TaskStatus } from '../../types/task';
import { TerminalIcon, CheckCircleIcon, XCircleIcon, RefreshIcon, ShieldIcon, ChevronRightIcon } from '../icons/Icons';

interface PlanInspectorProps {
  plan: ExecutionPlan | null;
  currentStepIndex?: number;
}

export const PlanInspector: React.FC<PlanInspectorProps> = ({ plan, currentStepIndex = 0 }) => {
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);

  if (!plan) {
    return (
      <div className="card" style={styles.emptyContainer}>
        <TerminalIcon size={24} color="var(--text-muted)" />
        <span style={styles.emptyText}>No execution plan active</span>
      </div>
    );
  }

  const toggleStep = (stepId: string) => {
    setExpandedStepId(prev => prev === stepId ? null : stepId);
  };

  return (
    <div className="card" style={styles.container}>
      {/* Plan Header */}
      <div style={styles.header}>
        <div style={styles.titleGroup}>
          <span style={styles.planBadge}>M1.8 EXECUTION PLAN</span>
          <h4 style={styles.planGoal}>{plan.description}</h4>
        </div>
        <span style={styles.stepsCountBadge}>
          {plan.steps.length} {plan.steps.length === 1 ? 'Step' : 'Steps'}
        </span>
      </div>

      {/* Steps List */}
      <div style={styles.stepsList}>
        {plan.steps.map((step, idx) => {
          const isCurrent = idx === currentStepIndex;
          const isDone = step.status === 'COMPLETED';
          const isFailed = step.status === 'FAILED';
          const isExpanded = expandedStepId === step.step_id;

          return (
            <div
              key={step.step_id || idx}
              style={{
                ...styles.stepItem,
                borderColor: isCurrent
                  ? 'var(--accent-primary-border)'
                  : isDone
                  ? 'var(--status-online-border)'
                  : isFailed
                  ? 'var(--status-error-border)'
                  : 'var(--border-subtle)',
                backgroundColor: isCurrent
                  ? 'var(--bg-surface-elevated)'
                  : 'var(--bg-input)',
              }}
            >
              <div style={styles.stepHeader} onClick={() => toggleStep(step.step_id)}>
                <div style={styles.stepTitleRow}>
                  <span style={{
                    ...styles.stepIndexCircle,
                    backgroundColor: isDone
                      ? 'var(--status-online)'
                      : isCurrent
                      ? 'var(--accent-primary)'
                      : isFailed
                      ? 'var(--status-error)'
                      : 'var(--bg-surface-hover)',
                    color: isDone || isCurrent || isFailed ? '#ffffff' : 'var(--text-muted)',
                  }}>
                    {isDone ? <CheckCircleIcon size={11} /> : idx + 1}
                  </span>

                  <span style={{
                    ...styles.stepDesc,
                    color: isCurrent ? 'var(--text-primary)' : 'var(--text-secondary)',
                    fontWeight: isCurrent ? 600 : 500,
                  }}>
                    {step.description}
                  </span>
                </div>

                <div style={styles.stepMetaRow}>
                  <span className={`badge ${
                    isDone ? 'badge-online' :
                    isFailed ? 'badge-error' :
                    isCurrent ? 'badge-busy' : 'badge-offline'
                  }`}>
                    {step.status || (isCurrent ? 'RUNNING' : 'PENDING')}
                  </span>

                  {step.actions && step.actions.length > 0 && (
                    <span style={styles.actionCountTag}>
                      {step.actions.length} {step.actions.length === 1 ? 'action' : 'actions'}
                    </span>
                  )}
                </div>
              </div>

              {/* Expanded Action List Breakdown */}
              {isExpanded && step.actions && step.actions.length > 0 && (
                <div style={styles.actionsContainer}>
                  {step.actions.map((act, actIdx) => (
                    <div key={act.action_id || actIdx} style={styles.actionRow}>
                      <span style={styles.actionTypeMono}>
                        {act.action_type || 'action'}
                      </span>
                      <span className={`badge ${
                        act.tier === 'TIER_3_HIGH_IMPACT' ? 'badge-warning' : 'badge-offline'
                      }`}>
                        {act.tier || 'TIER_1_SAFE'}
                      </span>
                      <span style={styles.actionStageText}>{act.stage}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
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
    borderRadius: 'var(--radius-lg)',
  },
  emptyContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-2)',
    padding: 'var(--space-4)',
    color: 'var(--text-muted)',
  },
  emptyText: {
    fontSize: 'var(--font-size-xs)',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingBottom: 'var(--space-2)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  planBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-primary)',
    letterSpacing: '0.06em',
  },
  planGoal: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.3,
  },
  stepsCountBadge: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-surface-elevated)',
    padding: '2px 8px',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--border-subtle)',
    fontFamily: 'var(--font-mono)',
  },
  stepsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  stepItem: {
    borderRadius: 'var(--radius-md)',
    border: '1px solid',
    padding: 'var(--space-2) var(--space-3)',
    transition: 'all var(--transition-fast)',
  },
  stepHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    cursor: 'pointer',
    userSelect: 'none',
  },
  stepTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
    flex: 1,
  },
  stepIndexCircle: {
    width: 18,
    height: 18,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '10px',
    fontWeight: 700,
    flexShrink: 0,
  },
  stepDesc: {
    fontSize: 'var(--font-size-xs)',
    lineHeight: 1.4,
  },
  stepMetaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  actionCountTag: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  actionsContainer: {
    marginTop: 'var(--space-2)',
    paddingTop: 'var(--space-2)',
    borderTop: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  actionRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '3px 6px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-xs)',
    fontSize: '11px',
  },
  actionTypeMono: {
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-cyan)',
    fontSize: '10.5px',
  },
  actionStageText: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
};
