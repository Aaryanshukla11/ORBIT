import React from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useOrbit } from '../../context/OrbitContext';
import { StopIcon, PauseIcon, PlayIcon, AlertTriangleIcon, CheckCircleIcon } from '../icons/Icons';

export const ActiveTaskControls: React.FC = () => {
  const { activeTask, cancelActiveTask, pauseActiveTask, resumeActiveTask, isProcessing } = useTaskConsole();
  const { systemHealth, triggerTakeover, releaseTakeover, connectionState } = useOrbit();

  const isConnected = connectionState === 'CONNECTED';
  const isPaused = activeTask?.status === 'PAUSED';
  const hasActiveTask = activeTask && (activeTask.status === 'RUNNING' || activeTask.status === 'VALIDATING' || activeTask.status === 'READY' || isPaused);

  if (!hasActiveTask && !systemHealth.takeoverArmed) {
    return null;
  }

  return (
    <div className="card" style={styles.container}>
      <div style={styles.leftGroup}>
        <span style={styles.badgeLabel}>CONTROL:</span>
        <span style={styles.taskTarget}>
          Task #{activeTask?.task_id.substring(0, 8) || 'Active'}
        </span>
      </div>

      <div style={styles.buttonsGroup}>
        {/* Pause / Resume */}
        {isPaused ? (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => resumeActiveTask()}
            disabled={!isConnected}
            title="Resume Task Execution"
          >
            <PlayIcon size={12} />
            <span>Resume</span>
          </button>
        ) : (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => pauseActiveTask()}
            disabled={!isConnected || !hasActiveTask}
            title="Pause Task Execution"
          >
            <PauseIcon size={12} />
            <span>Pause</span>
          </button>
        )}

        {/* Cancel Task */}
        <button
          className="btn btn-danger btn-sm"
          onClick={() => cancelActiveTask()}
          disabled={!isConnected || !hasActiveTask}
          title="Cancel Active Task"
        >
          <StopIcon size={12} />
          <span>Cancel Task</span>
        </button>

        {/* Takeover Guard Toggle */}
        {systemHealth.takeoverArmed ? (
          <button
            className="btn btn-secondary btn-sm"
            onClick={() => releaseTakeover()}
            disabled={!isConnected}
            title="Release Human Takeover and return to autonomous control"
          >
            <CheckCircleIcon size={12} color="var(--status-online)" />
            <span>Release Takeover</span>
          </button>
        ) : (
          <button
            className="btn btn-warning btn-sm"
            style={styles.takeoverBtn}
            onClick={() => triggerTakeover()}
            disabled={!isConnected}
            title="Trigger Human Takeover and lock autonomous synthetic inputs"
          >
            <AlertTriangleIcon size={12} color="var(--status-warning)" />
            <span>Emergency Takeover</span>
          </button>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 'var(--space-2) var(--space-4)',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-strong)',
    borderRadius: 'var(--radius-md)',
  },
  leftGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  badgeLabel: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  taskTarget: {
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    color: 'var(--accent-primary)',
    fontWeight: 600,
  },
  buttonsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  takeoverBtn: {
    backgroundColor: 'var(--status-warning-subtle)',
    color: 'var(--status-warning)',
    borderColor: 'var(--status-warning-border)',
  },
};
