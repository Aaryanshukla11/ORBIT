import React, { useState } from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useActivityHistory } from '../../context/ActivityHistoryContext';
import { useOrbit } from '../../context/OrbitContext';
import {
  TasksTabIcon,
  PlayIcon,
  PauseIcon,
  StopIcon,
  AlertTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  HistoryIcon,
  SearchIcon,
  ChevronRightIcon,
  ChevronDownIcon,
  CpuChipIcon,
  BotAutoIcon,
  ActiveRadioCircleIcon,
  PendingCircleIcon,
} from '../icons/Icons';
import { ExecutionDetailView } from '../activity/ExecutionDetailView';
import { ExecutionRecord } from '../../types/activity';

export const TasksView: React.FC = () => {
  const {
    activeTask,
    activePlan,
    isProcessing,
    pauseActiveTask,
    resumeActiveTask,
    cancelActiveTask,
  } = useTaskConsole();

  const {
    records,
    filter,
    setFilter,
    searchQuery,
    setSearchQuery,
    selectedExecution,
    selectExecution,
    activeExecution,
  } = useActivityHistory();

  const { systemHealth, triggerTakeover, releaseTakeover, connectionState } = useOrbit();

  // Section Expansion Mode: 'split' (both visible), 'tasks' (tasks expanded, history compressed), 'history' (history expanded, tasks compressed)
  const [viewMode, setViewMode] = useState<'split' | 'tasks' | 'history'>('split');
  const [showPlanSteps, setShowPlanSteps] = useState<boolean>(true);

  // If a specific execution detail is open, show the full detail view
  if (selectedExecution) {
    return <ExecutionDetailView />;
  }

  const isConnected = connectionState === 'CONNECTED';
  const isPaused = activeTask?.status === 'PAUSED';
  const hasActiveTask =
    (activeTask && (activeTask.status === 'RUNNING' || activeTask.status === 'VALIDATING' || activeTask.status === 'READY' || isPaused)) ||
    isProcessing ||
    Boolean(activeExecution);

  // Calculation for active execution progress
  const completedSteps = activeExecution?.steps_completed ?? (activeTask?.status === 'COMPLETED' ? 1 : 0);
  const totalSteps = activeExecution?.total_steps ?? (activePlan?.steps?.length || 1);
  const progressPct = Math.min(100, Math.round((completedSteps / Math.max(1, totalSteps)) * 100));

  // Filtered historical execution records
  const filteredRecords = records.filter((r) => {
    if (filter === 'RUNNING' && r.status !== 'RUNNING' && r.status !== 'REPLANNING') return false;
    if (filter === 'COMPLETED' && r.status !== 'COMPLETED') return false;
    if (filter === 'FAILED' && r.status !== 'FAILED') return false;
    if (filter === 'CANCELLED' && r.status !== 'CANCELLED') return false;

    if (searchQuery && searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      const inGoal = (r.goal || '').toLowerCase().includes(q);
      const inModel = r.active_model ? r.active_model.toLowerCase().includes(q) : false;
      const inApp = (r.applications_involved || []).some((a) => a.toLowerCase().includes(q));
      const inStatus = (r.status || '').toLowerCase().includes(q);
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
    return `${(ms / 1000).toFixed(1)}s`;
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

  return (
    <div style={styles.container}>
      {/* 1. Master Header with Mode Selector */}
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <TasksTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Tasks & Execution Pipeline</span>
          <span style={styles.headerBadge}>
            {hasActiveTask ? '1 Active' : 'Idle'} • {records.length} Recorded
          </span>
        </div>

        {/* Segmented Mode Selector */}
        <div style={styles.modePillGroup}>
          <button
            type="button"
            style={{
              ...styles.modeBtn,
              backgroundColor: viewMode === 'tasks' ? 'var(--bg-surface)' : 'transparent',
              color: viewMode === 'tasks' ? 'var(--accent-primary)' : 'var(--text-muted)',
              fontWeight: viewMode === 'tasks' ? 700 : 500,
              boxShadow: viewMode === 'tasks' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setViewMode('tasks')}
            title="Focus and expand Active Pipeline"
          >
            <BotAutoIcon size={12} color={viewMode === 'tasks' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
            <span>Pipeline Focus</span>
          </button>

          <button
            type="button"
            style={{
              ...styles.modeBtn,
              backgroundColor: viewMode === 'split' ? 'var(--bg-surface)' : 'transparent',
              color: viewMode === 'split' ? 'var(--accent-primary)' : 'var(--text-muted)',
              fontWeight: viewMode === 'split' ? 700 : 500,
              boxShadow: viewMode === 'split' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setViewMode('split')}
            title="Balanced view with both Pipeline and History"
          >
            <span>Split View</span>
          </button>

          <button
            type="button"
            style={{
              ...styles.modeBtn,
              backgroundColor: viewMode === 'history' ? 'var(--bg-surface)' : 'transparent',
              color: viewMode === 'history' ? 'var(--accent-primary)' : 'var(--text-muted)',
              fontWeight: viewMode === 'history' ? 700 : 500,
              boxShadow: viewMode === 'history' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setViewMode('history')}
            title="Focus and expand Execution History"
          >
            <HistoryIcon size={12} color={viewMode === 'history' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
            <span>History Focus</span>
          </button>
        </div>
      </div>

      <div style={styles.scrollArea}>
        {/* ========================================================= */}
        {/* SECTION 1: ACTIVE TASK & EXECUTION PIPELINE               */}
        {/* ========================================================= */}
        {viewMode === 'history' ? (
          /* COMPRESSED Tasks Ribbon */
          <div
            style={styles.compressedRibbon}
            onClick={() => setViewMode('tasks')}
            title="Click to expand Active Task Pipeline"
          >
            <div style={styles.compressedLeft}>
              <span
                style={{
                  ...styles.pulseDot,
                  backgroundColor: hasActiveTask ? 'var(--accent-primary)' : 'var(--accent-green)',
                }}
              />
              <span style={styles.compressedLabel}>ACTIVE PIPELINE:</span>
              <span style={styles.compressedText}>
                {hasActiveTask
                  ? activeExecution?.goal || activeTask?.prompt || 'Executing active pipeline...'
                  : 'ORBIT Agent Idle & Ready'}
              </span>
              {hasActiveTask && (
                <span style={styles.compressedStepBadge}>
                  Step {completedSteps}/{totalSteps} • {progressPct}%
                </span>
              )}
            </div>

            <div style={styles.compressedRight}>
              <span style={styles.expandHintBadge}>Click to Expand ↕</span>
            </div>
          </div>
        ) : (
          /* EXPANDED Active Task Card */
          <div
            style={{
              ...styles.activeCard,
              borderColor: hasActiveTask ? 'var(--accent-primary)' : 'var(--border-default)',
            }}
          >
            <div style={styles.activeHeaderRow}>
              <div style={styles.activeStatusWrap}>
                <span
                  style={{
                    ...styles.pulseDot,
                    backgroundColor: isProcessing || activeExecution ? 'var(--accent-primary)' : 'var(--accent-green)',
                  }}
                />
                <span style={styles.activeStatusText}>
                  {isProcessing || activeExecution?.status === 'RUNNING'
                    ? 'PROCESSING TASK'
                    : isPaused
                    ? 'TASK PAUSED'
                    : systemHealth.takeoverArmed
                    ? 'HUMAN TAKEOVER ACTIVE'
                    : 'ORBIT AGENT READY'}
                </span>
              </div>

              {/* Action Controls */}
              <div style={styles.controlButtons}>
                {hasActiveTask && (
                  <>
                    {isPaused ? (
                      <button
                        type="button"
                        style={{ ...styles.actionBtn, borderColor: 'var(--accent-green)', color: 'var(--accent-green)' }}
                        onClick={() => resumeActiveTask()}
                        title="Resume Execution"
                      >
                        <PlayIcon size={12} color="var(--accent-green)" />
                        <span>Resume</span>
                      </button>
                    ) : (
                      <button
                        type="button"
                        style={styles.actionBtn}
                        onClick={() => pauseActiveTask()}
                        title="Pause Execution"
                      >
                        <PauseIcon size={12} color="var(--text-secondary)" />
                        <span>Pause</span>
                      </button>
                    )}

                    <button
                      type="button"
                      style={{ ...styles.actionBtn, borderColor: 'var(--accent-red)', color: 'var(--accent-red)' }}
                      onClick={() => cancelActiveTask()}
                      title="Cancel Task"
                    >
                      <StopIcon size={12} color="var(--accent-red)" />
                      <span>Cancel</span>
                    </button>
                  </>
                )}

                {/* Human Takeover Guard Toggle */}
                {systemHealth.takeoverArmed ? (
                  <button
                    type="button"
                    style={{ ...styles.actionBtn, borderColor: 'var(--accent-green)', color: 'var(--accent-green)' }}
                    onClick={() => releaseTakeover()}
                    title="Release human takeover and restore autonomous control"
                  >
                    <CheckCircleIcon size={12} color="var(--accent-green)" />
                    <span>Release Takeover</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    style={{ ...styles.actionBtn, borderColor: 'var(--accent-warning)', color: 'var(--accent-warning)' }}
                    onClick={() => triggerTakeover()}
                    title="Lock autonomous synthetic inputs & take manual control"
                  >
                    <AlertTriangleIcon size={12} color="var(--accent-warning)" />
                    <span>Emergency Takeover</span>
                  </button>
                )}

                {viewMode === 'split' && (
                  <button
                    type="button"
                    style={styles.compressToggleBtn}
                    onClick={() => setViewMode('history')}
                    title="Compress Pipeline to focus on History"
                  >
                    ▾ Compress
                  </button>
                )}
              </div>
            </div>

            {/* Task Goal Display */}
            <div style={styles.goalBox}>
              <div style={styles.goalLabel}>CURRENT GOAL:</div>
              <div style={styles.goalText}>
                {hasActiveTask
                  ? activeExecution?.goal || activeTask?.prompt || 'Processing active agent task...'
                  : 'No task currently active. Type an instruction in the Assistant tab to begin.'}
              </div>
            </div>

            {/* Live Step Progress Bar */}
            {hasActiveTask && (
              <div style={styles.progressSection}>
                <div style={styles.progressInfoRow}>
                  <span style={styles.progressStepCount}>
                    Step {Math.min(totalSteps, completedSteps + 1)} of {totalSteps}
                  </span>
                  <span style={styles.progressPctText}>{progressPct}%</span>
                </div>
                <div style={styles.progressTrack}>
                  <div style={{ ...styles.progressFill, width: `${progressPct}%` }} />
                </div>
              </div>
            )}

            {/* Live Planned Steps Inspector */}
            {activePlan && activePlan.steps && activePlan.steps.length > 0 && (
              <div style={styles.planContainer}>
                <div
                  style={styles.planHeader}
                  onClick={() => setShowPlanSteps(!showPlanSteps)}
                >
                  <div style={styles.planHeaderLeft}>
                    {showPlanSteps ? <ChevronDownIcon size={12} /> : <ChevronRightIcon size={12} />}
                    <span>Execution Plan ({activePlan.steps.length} Steps Planned)</span>
                  </div>
                  <span style={styles.planHint}>{showPlanSteps ? 'Collapse' : 'Expand'}</span>
                </div>

                {showPlanSteps && (
                  <div style={styles.stepsList}>
                    {activePlan.steps.map((step, idx) => {
                      const isCurrent = idx === completedSteps;
                      const isDone = idx < completedSteps;
                      return (
                        <div
                          key={step.step_id || idx}
                          style={{
                            ...styles.stepItem,
                            backgroundColor: isCurrent ? 'var(--accent-primary-subtle)' : 'var(--bg-app)',
                            borderColor: isCurrent ? 'var(--accent-primary)' : 'var(--border-subtle)',
                          }}
                        >
                          <div style={styles.stepIconWrap}>
                            {isDone ? (
                              <CheckCircleIcon size={14} color="var(--accent-green)" />
                            ) : isCurrent ? (
                              <ActiveRadioCircleIcon size={14} />
                            ) : (
                              <PendingCircleIcon size={14} />
                            )}
                          </div>
                          <div style={styles.stepTextWrap}>
                            <div style={styles.stepTitle}>
                              <span style={styles.stepIndex}>#{idx + 1}</span> {step.description || `Execute ${(step as any).action || (step.actions && step.actions.length > 0 ? step.actions[0].action_type : 'Step')}`}
                            </div>
                            <div style={styles.stepMeta}>
                              Action: {(step as any).action || (step.actions && step.actions.length > 0 ? step.actions.map(a => a.action_type).join(', ') : 'Custom')} {(step as any).target_app ? `• App: ${(step as any).target_app}` : ''}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ========================================================= */}
        {/* SECTION 2: EXECUTION HISTORY & ACTIVITY TIMELINE          */}
        {/* ========================================================= */}
        {viewMode === 'tasks' ? (
          /* COMPRESSED History Ribbon */
          <div
            style={styles.compressedRibbon}
            onClick={() => setViewMode('history')}
            title="Click to expand Execution History"
          >
            <div style={styles.compressedLeft}>
              <HistoryIcon size={14} color="var(--accent-primary)" />
              <span style={styles.compressedLabel}>EXECUTION HISTORY:</span>
              <span style={styles.compressedText}>
                {records.length} tasks recorded ({records.filter((r) => r.status === 'COMPLETED').length} completed,{' '}
                {records.filter((r) => r.status === 'FAILED').length} failed)
              </span>
            </div>

            <div style={styles.compressedRight}>
              <span style={styles.expandHintBadge}>Click to Expand ↕</span>
            </div>
          </div>
        ) : (
          /* EXPANDED History Section */
          <div style={styles.historyContainer}>
            {/* History Section Header & Filter Strip */}
            <div style={styles.historyHeaderRow}>
              <div style={styles.historyTitleWrap}>
                <HistoryIcon size={14} color="var(--accent-primary)" />
                <span style={styles.historyTitle}>Execution History ({filteredRecords.length})</span>
              </div>

              <div style={styles.historyControls}>
                {/* Status Filter Pills */}
                <div style={styles.filterPills}>
                  {(['ALL', 'RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED'] as const).map((f) => (
                    <button
                      key={f}
                      type="button"
                      style={{
                        ...styles.filterBtn,
                        backgroundColor: filter === f ? 'var(--accent-primary)' : 'transparent',
                        color: filter === f ? '#ffffff' : 'var(--text-muted)',
                        fontWeight: filter === f ? 700 : 500,
                      }}
                      onClick={() => setFilter(f)}
                    >
                      {f.charAt(0) + f.slice(1).toLowerCase()}
                    </button>
                  ))}
                </div>

                {viewMode === 'split' && (
                  <button
                    type="button"
                    style={styles.compressToggleBtn}
                    onClick={() => setViewMode('tasks')}
                    title="Compress History to focus on Pipeline"
                  >
                    ▴ Compress
                  </button>
                )}
              </div>
            </div>

            {/* Live Search Bar */}
            <div style={styles.searchBox}>
              <SearchIcon size={13} color="var(--text-muted)" />
              <input
                type="text"
                placeholder="Search execution history by goal, active model, or target application..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={styles.searchInput}
              />
              {searchQuery && (
                <button
                  type="button"
                  style={styles.clearBtn}
                  onClick={() => setSearchQuery('')}
                  title="Clear search"
                >
                  ×
                </button>
              )}
            </div>

            {/* Timeline List of Execution Records */}
            {filteredRecords.length === 0 ? (
              <div style={styles.emptyHistory}>
                {searchQuery
                  ? `No execution records matched "${searchQuery}".`
                  : filter !== 'ALL'
                  ? `No execution records with status "${filter}".`
                  : 'No tasks executed yet. Send a prompt in the Assistant tab to record activity.'}
              </div>
            ) : (
              <div style={styles.timelineList}>
                {filteredRecords.map((rec) => (
                  <div
                    key={rec.execution_id}
                    style={styles.recordCard}
                    onClick={() => selectExecution(rec.execution_id)}
                    title="Click to view full plan steps, logs, and execution details"
                  >
                    <div style={styles.recordTopRow}>
                      <div style={styles.recordGoalWrap}>
                        <span style={styles.recordStatusIcon}>{renderStatusIcon(rec.status)}</span>
                        <span style={styles.recordGoal}>{rec.goal}</span>
                      </div>
                      <span
                        style={{
                          ...styles.statusTag,
                          backgroundColor:
                            rec.status === 'RUNNING' || rec.status === 'REPLANNING'
                              ? 'var(--accent-primary-subtle)'
                              : rec.status === 'COMPLETED'
                              ? 'var(--accent-green-subtle)'
                              : rec.status === 'FAILED'
                              ? 'rgba(239, 68, 68, 0.15)'
                              : 'var(--bg-subtle)',
                          color:
                            rec.status === 'RUNNING' || rec.status === 'REPLANNING'
                              ? 'var(--accent-primary)'
                              : rec.status === 'COMPLETED'
                              ? 'var(--accent-green)'
                              : rec.status === 'FAILED'
                              ? 'var(--accent-red)'
                              : 'var(--text-muted)',
                        }}
                      >
                        {rec.status}
                      </span>
                    </div>

                    <div style={styles.recordMetaRow}>
                      <div style={styles.recordMetaLeft}>
                        {rec.active_model && (
                          <span style={styles.metaBadge}>
                            <CpuChipIcon size={10} color="var(--text-secondary)" />
                            <span>{rec.active_model}</span>
                          </span>
                        )}
                        {rec.applications_involved && rec.applications_involved.length > 0 && (
                          <span style={styles.metaBadge}>
                            <span>{rec.applications_involved.join(', ')}</span>
                          </span>
                        )}
                        {rec.steps_completed !== undefined && (
                          <span style={styles.metaBadge}>
                            {rec.steps_completed} / {rec.total_steps || rec.steps?.length || 1} Steps
                          </span>
                        )}
                      </div>

                      <div style={styles.recordMetaRight}>
                        {rec.duration_ms && <span style={styles.durationText}>{formatDuration(rec.duration_ms)}</span>}
                        <span style={styles.timestampText}>{formatRelativeTime((rec as any).timestamp || (rec as any).created_at || (rec as any).completed_at)}</span>
                        <ChevronRightIcon size={12} color="var(--text-muted)" />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
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
    width: '100%',
    height: '100%',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 18px 8px 18px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
    userSelect: 'none',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  title: {
    fontSize: '13.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  headerBadge: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    fontWeight: 600,
  },
  modePillGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
    gap: '2px',
  },
  modeBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 10px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '10.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 18px 24px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  // Compressed Ribbon Styling
  compressedRibbon: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
    boxShadow: 'var(--shadow-card)',
    transition: 'all var(--transition-fast)',
    userSelect: 'none',
    flexShrink: 0,
  },
  compressedLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    overflow: 'hidden',
    flex: 1,
  },
  compressedLabel: {
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--text-secondary)',
    letterSpacing: '0.04em',
    whiteSpace: 'nowrap',
  },
  compressedText: {
    fontSize: '11.5px',
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  compressedStepBadge: {
    fontSize: '10px',
    backgroundColor: 'var(--accent-primary-subtle)',
    color: 'var(--accent-primary)',
    fontWeight: 700,
    padding: '1px 6px',
    borderRadius: 'var(--radius-sm)',
    whiteSpace: 'nowrap',
  },
  compressedRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  expandHintBadge: {
    fontSize: '10px',
    color: 'var(--accent-primary)',
    fontWeight: 600,
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
  },
  // Expanded Active Task Card
  activeCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    boxShadow: 'var(--shadow-card)',
    transition: 'all var(--transition-fast)',
    flexShrink: 0,
  },
  activeHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: '8px',
  },
  activeStatusWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  pulseDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    display: 'inline-block',
  },
  activeStatusText: {
    fontSize: '11.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '0.04em',
  },
  controlButtons: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  actionBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '4px 8px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-subtle)',
    border: '1px solid var(--border-subtle)',
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  compressToggleBtn: {
    padding: '3px 7px',
    borderRadius: 'var(--radius-sm)',
    backgroundColor: 'transparent',
    border: '1px dashed var(--border-subtle)',
    color: 'var(--text-muted)',
    fontSize: '10px',
    cursor: 'pointer',
  },
  goalBox: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    backgroundColor: 'var(--bg-app)',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
  },
  goalLabel: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  goalText: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.4,
  },
  progressSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  progressInfoRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10.5px',
  },
  progressStepCount: {
    color: 'var(--text-muted)',
    fontWeight: 600,
  },
  progressPctText: {
    color: 'var(--accent-primary)',
    fontWeight: 700,
  },
  progressTrack: {
    height: 5,
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: '3px',
    overflow: 'hidden',
  },
  progressFill: {
    height: '100%',
    backgroundColor: 'var(--accent-primary)',
    borderRadius: '3px',
    transition: 'width 0.3s ease',
  },
  planContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    marginTop: '2px',
  },
  planHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: 'pointer',
    userSelect: 'none',
  },
  planHeaderLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--text-secondary)',
  },
  planHint: {
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  stepsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    maxHeight: '180px',
    overflowY: 'auto',
    paddingRight: '2px',
  },
  stepItem: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    padding: '6px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid',
  },
  stepIconWrap: {
    marginTop: '1px',
    flexShrink: 0,
  },
  stepTextWrap: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    flex: 1,
  },
  stepTitle: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  stepIndex: {
    color: 'var(--text-muted)',
    fontWeight: 700,
    marginRight: '2px',
  },
  stepMeta: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    marginTop: '1px',
  },
  // History Container
  historyContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    flex: 1,
  },
  historyHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: '8px',
  },
  historyTitleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  historyTitle: {
    fontSize: '12.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  historyControls: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  filterPills: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
  },
  filterBtn: {
    padding: '2px 7px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '9.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  searchBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '5px 8px',
    boxShadow: 'var(--shadow-card)',
  },
  searchInput: {
    flex: 1,
    border: 'none',
    backgroundColor: 'transparent',
    fontSize: '11px',
    color: 'var(--text-primary)',
    outline: 'none',
    fontFamily: 'inherit',
  },
  clearBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: '14px',
    cursor: 'pointer',
    padding: '0 2px',
  },
  emptyHistory: {
    textAlign: 'center',
    padding: '24px 12px',
    color: 'var(--text-muted)',
    fontSize: '11.5px',
    backgroundColor: 'var(--bg-surface)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
  },
  timelineList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  recordCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '9px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    cursor: 'pointer',
    boxShadow: 'var(--shadow-card)',
    transition: 'all var(--transition-fast)',
  },
  recordTopRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  recordGoalWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    overflow: 'hidden',
    flex: 1,
  },
  recordStatusIcon: {
    flexShrink: 0,
    display: 'flex',
    alignItems: 'center',
  },
  recordGoal: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  statusTag: {
    fontSize: '9.5px',
    fontWeight: 700,
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    letterSpacing: '0.03em',
    whiteSpace: 'nowrap',
  },
  recordMetaRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  recordMetaLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    overflow: 'hidden',
  },
  metaBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  recordMetaRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  durationText: {
    fontFamily: 'Consolas, monospace',
  },
  timestampText: {
    color: 'var(--text-muted)',
  },
  runningDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
    display: 'inline-block',
  },
  idleDot: {
    width: 8,
    height: 8,
    borderRadius: '50%',
    backgroundColor: 'var(--text-muted)',
    display: 'inline-block',
  },
};
