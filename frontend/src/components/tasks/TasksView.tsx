import React, { useState } from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { PlayIcon, PauseIcon, StopIcon, CheckCircleIcon, ActiveRadioCircleIcon, PendingCircleIcon, TasksTabIcon } from '../icons/Icons';

export const TasksView: React.FC = () => {
  const { activeTask, activePlan, isProcessing, pauseActiveTask, resumeActiveTask, cancelActiveTask } = useTaskConsole();
  const [selectedFilter, setSelectedFilter] = useState<'all' | 'active' | 'completed'>('all');

  const mockTasks = [
    {
      id: 'task_001',
      title: 'Analyze and summarize repository architecture',
      target: 'Visual Studio Code',
      status: isProcessing ? 'RUNNING' : 'COMPLETED',
      progress: isProcessing ? 65 : 100,
      steps: 6,
      completedSteps: isProcessing ? 4 : 6,
      time: '2 mins ago',
    },
    {
      id: 'task_002',
      title: 'Inspect active terminal logs for build warnings',
      target: 'Windows Terminal',
      status: 'COMPLETED',
      progress: 100,
      steps: 3,
      completedSteps: 3,
      time: '14 mins ago',
    },
    {
      id: 'task_003',
      title: 'Verify UI responsiveness in Chrome DevTools',
      target: 'Google Chrome',
      status: 'IDLE',
      progress: 0,
      steps: 4,
      completedSteps: 0,
      time: '1 hour ago',
    },
  ];

  return (
    <div style={styles.container}>
      {/* Header & Filter */}
      <div style={styles.filterRow}>
        <div style={styles.titleWrap}>
          <TasksTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Execution Pipeline</span>
        </div>
        <div style={styles.pillFilterGroup}>
          {(['all', 'active', 'completed'] as const).map((filter) => (
            <button
              key={filter}
              type="button"
              style={{
                ...styles.filterBtn,
                backgroundColor: selectedFilter === filter ? 'var(--bg-surface)' : 'transparent',
                color: selectedFilter === filter ? 'var(--accent-primary)' : 'var(--text-muted)',
                fontWeight: selectedFilter === filter ? 700 : 500,
                boxShadow: selectedFilter === filter ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setSelectedFilter(filter)}
            >
              {filter.charAt(0).toUpperCase() + filter.slice(1)}
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
          {activeTask ? activeTask.prompt : 'Locate Visual Studio Code & Summarize ORBIT Codebase'}
        </div>

        {/* Progress Bar */}
        <div style={styles.progressContainer}>
          <div style={styles.progressBarTrack}>
            <div
              style={{
                ...styles.progressBarFill,
                width: isProcessing ? '65%' : '100%',
              }}
            />
          </div>
          <div style={styles.progressLabelRow}>
            <span>Target: VS Code</span>
            <span>{isProcessing ? 'Step 3 of 6 (65%)' : 'Completed (100%)'}</span>
          </div>
        </div>
      </div>

      {/* Task Queue List */}
      <div style={styles.queueHeader}>Task History & Queue</div>
      <div style={styles.taskList}>
        {mockTasks
          .filter((t) => {
            if (selectedFilter === 'active') return t.status === 'RUNNING';
            if (selectedFilter === 'completed') return t.status === 'COMPLETED';
            return true;
          })
          .map((task) => (
            <div key={task.id} style={styles.taskItem}>
              <div style={styles.taskItemTop}>
                <div style={styles.itemTitle}>{task.title}</div>
                <span
                  style={{
                    ...styles.statusTag,
                    backgroundColor:
                      task.status === 'RUNNING'
                        ? 'var(--accent-primary-subtle)'
                        : task.status === 'COMPLETED'
                        ? 'var(--accent-green-subtle)'
                        : 'var(--bg-subtle)',
                    color:
                      task.status === 'RUNNING'
                        ? 'var(--accent-primary)'
                        : task.status === 'COMPLETED'
                        ? 'var(--accent-green)'
                        : 'var(--text-muted)',
                  }}
                >
                  {task.status}
                </span>
              </div>

              <div style={styles.taskItemMeta}>
                <span>{task.target}</span>
                <span>•</span>
                <span>{task.completedSteps}/{task.steps} Steps</span>
                <span>•</span>
                <span>{task.time}</span>
              </div>
            </div>
          ))}
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
