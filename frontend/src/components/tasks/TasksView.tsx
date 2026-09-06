import React, { useState } from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useActivityHistory } from '../../context/ActivityHistoryContext';
import { PlayIcon, PauseIcon, StopIcon, TasksTabIcon } from '../icons/Icons';

export const TasksView: React.FC = () => {
  const { activeTask, activePlan, isProcessing, pauseActiveTask, resumeActiveTask, cancelActiveTask } = useTaskConsole();
  const { records, filter, setFilter, selectExecution } = useActivityHistory();
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'active' | 'completed'>('all');

  const filteredRecords = records.filter((r) => {
    if (selectedFilter === 'active') return r.status === 'RUNNING' || r.status === 'REPLANNING';
    if (selectedFilter === 'completed') return r.status === 'COMPLETED';
    return true;
  });

  return (
    <div style={styles.container}>
      {/* Header & Filter */}
      <div style={styles.filterRow}>
        <div style={styles.titleWrap}>
          <TasksTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Execution Pipeline</span>
        </div>
        <div style={styles.pillFilterGroup}>
          {(['all', 'active', 'completed'] as const).map((f) => (
            <button
              key={f}
              type="button"
              style={{
                ...styles.filterBtn,
                backgroundColor: selectedFilter === f ? 'var(--bg-surface)' : 'transparent',
                color: selectedFilter === f ? 'var(--accent-primary)' : 'var(--text-muted)',
                fontWeight: selectedFilter === f ? 700 : 500,
                boxShadow: selectedFilter === f ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setSelectedFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Active Running Task Hero Card */}
      <div style={styles.activeTaskCard}>
        <div style={styles.activeHeader}>
          <div style={styles.activeStatusPill}>
            <span style={styles.livePulseDot} />
            <span>{isProcessing ? 'PROCESSING TASK' : 'ORBIT AGENT READY'}</span>
          </div>
          <div style={styles.actionBtnRow}>
            {isProcessing ? (
              <>
                <button
                  type="button"
                  style={styles.controlBtn}
                  onClick={() => pauseActiveTask()}
                  title="Pause Execution"
                >
                  <PauseIcon size={12} color="var(--text-secondary)" />
                </button>
                <button
                  type="button"
                  style={{ ...styles.controlBtn, borderColor: 'var(--accent-red)' }}
                  onClick={() => cancelActiveTask()}
                  title="Cancel Task"
                >
                  <StopIcon size={12} color="var(--accent-red)" />
                </button>
              </>
            ) : (
              <button
                type="button"
                style={{ ...styles.controlBtn, borderColor: 'var(--accent-green)' }}
                onClick={() => resumeActiveTask()}
                title="Resume / Start"
              >
                <PlayIcon size={12} color="var(--accent-green)" />
              </button>
            )}
          </div>
        </div>

        <div style={styles.taskTitle}>
          {activeTask ? activeTask.prompt : isProcessing ? 'Processing Active Task...' : 'No active task running'}
        </div>

        {/* Progress Bar */}
        {activeTask && (
          <div style={styles.progressContainer}>
            <div style={styles.progressBarTrack}>
              <div
                style={{
                  ...styles.progressBarFill,
                  width: activeTask.status === 'COMPLETED' ? '100%' : isProcessing ? '60%' : '0%',
                }}
              />
            </div>
            <div style={styles.progressLabelRow}>
              <span>Status: {activeTask.status}</span>
              <span>{activePlan ? `${activePlan.steps.length} steps planned` : ''}</span>
            </div>
          </div>
        )}
      </div>

      {/* Task Queue List */}
      <div style={styles.queueHeader}>Task History & Queue ({filteredRecords.length})</div>
      <div style={styles.taskList}>
        {filteredRecords.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '24px 12px', color: 'var(--text-muted)', fontSize: '11.5px' }}>
            No task records yet. Submit a task in Chat to begin execution.
          </div>
        ) : (
          filteredRecords.map((record) => (
            <div
              key={record.execution_id}
              style={styles.taskItem}
              onClick={() => selectExecution(record.execution_id)}
            >
              <div style={styles.taskItemTop}>
                <div style={styles.itemTitle}>{record.prompt}</div>
                <span
                  style={{
                    ...styles.statusTag,
                    backgroundColor:
                      record.status === 'RUNNING' || record.status === 'REPLANNING'
                        ? 'var(--accent-primary-subtle)'
                        : record.status === 'COMPLETED'
                        ? 'var(--accent-green-subtle)'
                        : record.status === 'FAILED'
                        ? 'rgba(239, 68, 68, 0.15)'
                        : 'var(--bg-subtle)',
                    color:
                      record.status === 'RUNNING' || record.status === 'REPLANNING'
                        ? 'var(--accent-primary)'
                        : record.status === 'COMPLETED'
                        ? 'var(--accent-green)'
                        : record.status === 'FAILED'
                        ? 'var(--accent-red)'
                        : 'var(--text-muted)',
                  }}
                >
                  {record.status}
                </span>
              </div>

              <div style={styles.taskItemMeta}>
                <span>{record.plan_summary || 'Task'}</span>
                <span>•</span>
                <span>{record.step_count || 0} Steps</span>
                <span>•</span>
                <span>{new Date(record.started_at).toLocaleTimeString()}</span>
              </div>
            </div>
          ))
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
    overflowY: 'auto',
    padding: '10px 18px 24px 18px',
    gap: '14px',
    userSelect: 'none',
  },
  filterRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '8px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  title: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  pillFilterGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
  },
  filterBtn: {
    padding: '3px 8px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '10.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  activeTaskCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '14px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  activeHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  activeStatusPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-primary-subtle)',
    padding: '2px 7px',
    borderRadius: 'var(--radius-full)',
    letterSpacing: '0.04em',
  },
  livePulseDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
    boxShadow: '0 0 6px var(--accent-primary)',
  },
  actionBtnRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  controlBtn: {
    width: 26,
    height: 26,
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  taskTitle: {
    fontSize: '13px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.35,
  },
  progressContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  progressBarTrack: {
    width: '100%',
    height: 6,
    borderRadius: 'var(--radius-full)',
    backgroundColor: 'var(--bg-subtle)',
    overflow: 'hidden',
  },
  progressBarFill: {
    height: '100%',
    backgroundColor: 'var(--accent-primary)',
    borderRadius: 'var(--radius-full)',
    transition: 'width 0.4s ease',
  },
  progressLabelRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  queueHeader: {
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  taskList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  taskItem: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    transition: 'all var(--transition-fast)',
    cursor: 'pointer',
  },
  taskItemTop: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  itemTitle: {
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
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
  taskItemMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
};
