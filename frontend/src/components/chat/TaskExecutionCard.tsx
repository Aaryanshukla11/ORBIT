import React, { useState } from 'react';
import { GreenCheckCircleIcon, ActiveRadioCircleIcon, PendingCircleIcon, ChevronDownIcon, ChevronRightIcon } from '../icons/Icons';
import { ExecutionPlan, ErrorDetail } from '../../types/task';

export interface StepItem {
  id: string;
  label: string;
  status: 'completed' | 'active' | 'pending';
  detail?: string;
}

interface TaskExecutionCardProps {
  steps?: StepItem[];
  plan?: ExecutionPlan | null;
  error?: ErrorDetail | null;
}

export const TaskExecutionCard: React.FC<TaskExecutionCardProps> = ({ steps, plan, error }) => {
  const [expandedStepId, setExpandedStepId] = useState<string | null>(null);

  // Derive honest steps from plan if steps are not explicitly passed
  const resolvedSteps: StepItem[] = React.useMemo(() => {
    if (steps && steps.length > 0) return steps;
    if (plan && plan.steps && plan.steps.length > 0) {
      return plan.steps.map((st, idx) => {
        let status: 'completed' | 'active' | 'pending' = 'pending';
        if (st.status === 'COMPLETED') status = 'completed';
        else if (st.status === 'RUNNING' || (st.status as string) === 'EXECUTING' || st.status === 'VERIFYING') status = 'active';

        const actionSummary = st.actions && st.actions.length > 0
          ? st.actions.map((a) => a.action_type).join(', ')
          : undefined;

        return {
          id: st.step_id || String(idx + 1),
          label: st.description || `Step ${idx + 1}`,
          status,
          detail: actionSummary ? `Actions: ${actionSummary}` : undefined,
        };
      });
    }
    return [];
  }, [steps, plan]);

  const toggleStep = (id: string) => {
    setExpandedStepId((prev) => (prev === id ? null : id));
  };

  if (resolvedSteps.length === 0) {
    return (
      <div style={styles.card}>
        <div style={styles.cardTop}>
          <span style={styles.cardTitle}>EXECUTION PLAN</span>
          <span style={styles.stepCount}>Formulating...</span>
        </div>
        <div style={styles.emptyStateNotice}>
          Awaiting structured plan from runtime...
        </div>
        {error && (
          <div style={styles.errorBox}>
            <strong>Failure [{error.code}]:</strong> {error.message}
          </div>
        )}
      </div>
    );
  }

  const completedCount = resolvedSteps.filter((s) => s.status === 'completed').length;

  return (
    <div style={styles.card}>
      <div style={styles.cardTop}>
        <span style={styles.cardTitle}>EXECUTION PLAN</span>
        <span style={styles.stepCount}>
          {completedCount}/{resolvedSteps.length} Steps
        </span>
      </div>

      <div style={styles.stepList}>
        {resolvedSteps.map((step) => {
          const isExpanded = expandedStepId === step.id;

          return (
            <div
              key={step.id}
              style={{
                ...styles.stepWrapper,
                backgroundColor: isExpanded ? 'var(--bg-surface)' : 'transparent',
                borderColor: isExpanded ? 'var(--border-default)' : 'transparent',
              }}
              onClick={() => toggleStep(step.id)}
            >
              <div style={styles.stepRow}>
                <div style={styles.iconWrap}>
                  {step.status === 'completed' && <GreenCheckCircleIcon size={17} />}
                  {step.status === 'active' && <ActiveRadioCircleIcon size={17} />}
                  {step.status === 'pending' && <PendingCircleIcon size={17} />}
                </div>

                <span
                  style={{
                    ...styles.stepLabel,
                    color:
                      step.status === 'active'
                        ? 'var(--text-primary)'
                        : step.status === 'completed'
                        ? 'var(--text-secondary)'
                        : 'var(--text-muted)',
                    fontWeight: step.status === 'active' ? 700 : 500,
                  }}
                >
                  {step.label}
                </span>

                <div style={styles.chevronWrap}>
                  {isExpanded ? (
                    <ChevronDownIcon size={12} color="var(--text-muted)" />
                  ) : (
                    <ChevronRightIcon size={12} color="var(--text-muted)" />
                  )}
                </div>
              </div>

              {isExpanded && step.detail && (
                <div style={styles.stepDetailBox}>
                  <span>{step.detail}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div style={styles.errorBox}>
          <strong>Failure [{error.code}]:</strong> {error.message}
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: '#f8fafc',
    border: '1px solid #edf2f7',
    borderRadius: '12px',
    padding: '12px 14px',
    marginTop: '8px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    userSelect: 'none',
  },
  cardTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '4px',
    borderBottom: '1px solid #edf2f7',
  },
  cardTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  stepCount: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
  },
  stepList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '3px',
  },
  stepWrapper: {
    borderRadius: 'var(--radius-sm)',
    border: '1px solid',
    padding: '4px 6px',
    transition: 'all var(--transition-fast)',
    cursor: 'pointer',
  },
  stepRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  iconWrap: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  stepLabel: {
    flex: 1,
    fontSize: '12px',
    lineHeight: 1.3,
  },
  chevronWrap: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepDetailBox: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
    lineHeight: 1.35,
    padding: '6px 8px 4px 26px',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-sm)',
    marginTop: '4px',
  },
  emptyStateNotice: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    padding: '4px 2px',
    fontStyle: 'italic',
  },
  errorBox: {
    fontSize: '11px',
    color: 'var(--accent-red, #ef4444)',
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
    borderRadius: 'var(--radius-sm)',
    padding: '6px 8px',
    marginTop: '4px',
  },
};
