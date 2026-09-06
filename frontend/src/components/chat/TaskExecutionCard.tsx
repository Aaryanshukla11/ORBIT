import React, { useState } from 'react';
import { GreenCheckCircleIcon, ActiveRadioCircleIcon, PendingCircleIcon, ChevronDownIcon, ChevronRightIcon } from '../icons/Icons';

export interface StepItem {
  id: string;
  label: string;
  status: 'completed' | 'active' | 'pending';
  detail?: string;
}

const DEFAULT_STEPS: StepItem[] = [
  { id: '1', label: 'Understanding intent', status: 'completed', detail: 'Parsed user goal: locate VS Code and summarize project structure.' },
  { id: '2', label: 'Scanning system context', status: 'completed', detail: 'Identified 3 top-level workspace windows. Located active process Code.exe.' },
  { id: '3', label: 'Locating Visual Studio Code', status: 'active', detail: 'Window HWND 0x00240E9A confirmed. OCR vision bounding box matched.' },
  { id: '4', label: 'Reading project structure', status: 'pending', detail: 'Traversing AST files in workspace directory.' },
  { id: '5', label: 'Generating summary', status: 'pending', detail: 'Synthesizing component architecture summary via local model.' },
  { id: '6', label: 'Preparing response', status: 'pending', detail: 'Formatting final response with actionable references.' },
];

interface TaskExecutionCardProps {
  steps?: StepItem[];
}

export const TaskExecutionCard: React.FC<TaskExecutionCardProps> = ({ steps = DEFAULT_STEPS }) => {
  const [expandedStepId, setExpandedStepId] = useState<string | null>('3');

  const toggleStep = (id: string) => {
    setExpandedStepId((prev) => (prev === id ? null : id));
  };

  return (
    <div style={styles.card}>
      <div style={styles.cardTop}>
        <span style={styles.cardTitle}>EXECUTION PLAN</span>
        <span style={styles.stepCount}>
          {steps.filter((s) => s.status === 'completed').length}/{steps.length} Steps
        </span>
      </div>

      <div style={styles.stepList}>
        {steps.map((step) => {
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
};
