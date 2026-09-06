import React, { useState } from 'react';
import { useOrbit } from '../context/OrbitContext';
import { useTaskConsole } from '../context/TaskConsoleContext';
import {
  PlayIcon,
  ModelsIcon,
  ActivityIcon,
  ShieldIcon,
  TerminalIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  RefreshIcon,
} from '../components/icons/Icons';

export const CommandCenterPage: React.FC = () => {
  const { connectionState, activeModel, setActivePage, systemHealth } = useOrbit();
  const { sendUserMessage } = useTaskConsole();
  const [prompt, setPrompt] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isConnected = connectionState === 'CONNECTED';

  const handleQuickSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim() || !isConnected) return;

    setIsSubmitting(true);
    sendUserMessage(prompt, 'task');
    setPrompt('');
    setTimeout(() => {
      setIsSubmitting(false);
      setActivePage('chat');
    }, 300);
  };

  return (
    <div style={styles.container}>
      {/* Page Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Command Center</h1>
          <p style={styles.description}>
            Executive control interface and autonomous desktop agent orchestration.
          </p>
        </div>
      </div>

      {/* Grid Layout */}
      <div style={styles.grid}>
        {/* Left 2-Column: Quick Task Launcher & System Status */}
        <div style={styles.mainColumn}>
          {/* Quick Task Dispatch Card */}
          <div className="card" style={styles.launchCard}>
            <div style={styles.cardHeader}>
              <div style={styles.cardTitleRow}>
                <TerminalIcon size={18} color="var(--accent-primary)" />
                <h3 style={styles.cardTitle}>Dispatch Autonomous Task</h3>
              </div>
              <span className={`badge ${isConnected ? 'badge-online' : 'badge-error'}`}>
                {isConnected ? 'Agent Ready' : 'Backend Offline'}
              </span>
            </div>

            <form onSubmit={handleQuickSubmit} style={styles.taskForm}>
              <textarea
                style={styles.taskTextarea}
                placeholder={isConnected ? "Enter natural language task instruction (e.g. 'Analyze quarterly PDF report and summarize findings')..." : "Connect to ORBIT WebSocket Gateway to dispatch tasks..."}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                disabled={!isConnected}
                rows={3}
              />
              <div style={styles.formFooter}>
                <div style={styles.promptHint}>
                  Press <kbd style={styles.kbd}>Enter</kbd> to launch, <kbd style={styles.kbd}>Shift+Enter</kbd> for newline
                </div>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={!isConnected || !prompt.trim() || isSubmitting}
                >
                  <PlayIcon size={15} />
                  <span>{isSubmitting ? 'Dispatching...' : 'Launch Task'}</span>
                </button>
              </div>
            </form>
          </div>

          {/* Quick Navigation Cards */}
          <div style={styles.navCardsRow}>
            <div
              className="card"
              style={styles.navCard}
              onClick={() => setActivePage('chat')}
            >
              <div style={styles.navCardIconRow}>
                <TerminalIcon size={20} color="var(--accent-cyan)" />
                <span style={styles.navCardLabel}>Task Console</span>
              </div>
              <p style={styles.navCardDesc}>Interactive execution console & plan monitoring.</p>
            </div>

            <div
              className="card"
              style={styles.navCard}
              onClick={() => setActivePage('activity')}
            >
              <div style={styles.navCardIconRow}>
                <ActivityIcon size={20} color="var(--accent-primary)" />
                <span style={styles.navCardLabel}>Activity Stream</span>
              </div>
              <p style={styles.navCardDesc}>Real-time telemetry and action stage inspector.</p>
            </div>

            <div
              className="card"
              style={styles.navCard}
              onClick={() => setActivePage('models')}
            >
              <div style={styles.navCardIconRow}>
                <ModelsIcon size={20} color="var(--status-online)" />
                <span style={styles.navCardLabel}>Model Runtime</span>
              </div>
              <p style={styles.navCardDesc}>Multi-provider routing, switching, & discovery.</p>
            </div>
          </div>
        </div>

        {/* Right 1-Column: Runtime Telemetry & Safety Matrix */}
        <div style={styles.sideColumn}>
          {/* Agent Readiness Matrix */}
          <div className="card" style={styles.statusCard}>
            <h3 style={styles.cardTitle}>Runtime Readiness</h3>
            <div style={styles.statusList}>
              <div style={styles.statusItem}>
                <span style={styles.statusItemLabel}>WebSocket Gateway</span>
                <span className={`badge ${isConnected ? 'badge-online' : 'badge-error'}`}>
                  {isConnected ? 'Connected' : 'Disconnected'}
                </span>
              </div>
              <div style={styles.statusItem}>
                <span style={styles.statusItemLabel}>Active LLM Core</span>
                <span className={`badge ${activeModel ? 'badge-online' : 'badge-offline'}`}>
                  {activeModel ? activeModel.modelId : 'Unavailable'}
                </span>
              </div>
              <div style={styles.statusItem}>
                <span style={styles.statusItemLabel}>Human Takeover Guard</span>
                <span className={`badge ${systemHealth.takeoverArmed ? 'badge-warning' : 'badge-online'}`}>
                  {systemHealth.takeoverArmed ? 'Armed' : 'Active'}
                </span>
              </div>
              <div style={styles.statusItem}>
                <span style={styles.statusItemLabel}>Watchdog Recovery</span>
                <span className={`badge ${systemHealth.watchdogActive ? 'badge-online' : 'badge-offline'}`}>
                  {systemHealth.watchdogActive ? 'Enabled' : 'Standby'}
                </span>
              </div>
            </div>
          </div>

          {/* Connection Advice Banner */}
          {!isConnected && (
            <div style={styles.disconnectedAlert}>
              <AlertTriangleIcon size={18} color="var(--status-warning)" />
              <div>
                <div style={styles.alertTitle}>Gateway Offline</div>
                <div style={styles.alertText}>
                  Launch the ORBIT Python backend with <code>python -m orbit --port 8765</code> to connect.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
    maxWidth: 1400,
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 'var(--font-size-2xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-1)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: '2fr 1fr',
    gap: 'var(--space-6)',
  },
  mainColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-5)',
  },
  sideColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-5)',
  },
  launchCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  cardTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  taskForm: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  taskTextarea: {
    width: '100%',
    backgroundColor: 'var(--bg-input)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3) var(--space-4)',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-sans)',
    fontSize: 'var(--font-size-sm)',
    lineHeight: 1.6,
    resize: 'none',
    outline: 'none',
    boxShadow: 'var(--shadow-inner)',
  },
  formFooter: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  promptHint: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-muted)',
  },
  kbd: {
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-xs)',
    padding: '1px 5px',
    fontSize: '10px',
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
  },
  navCardsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: 'var(--space-4)',
  },
  navCard: {
    cursor: 'pointer',
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
    transition: 'all var(--transition-fast)',
  },
  navCardIconRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  navCardLabel: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  navCardDesc: {
    fontSize: '12px',
    color: 'var(--text-muted)',
    lineHeight: 1.4,
  },
  statusCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  statusList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
  },
  statusItem: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 'var(--space-2) 0',
    borderBottom: '1px solid var(--border-subtle)',
  },
  statusItemLabel: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-secondary)',
  },
  disconnectedAlert: {
    display: 'flex',
    gap: 'var(--space-3)',
    padding: 'var(--space-4)',
    backgroundColor: 'var(--status-warning-subtle)',
    border: '1px solid var(--status-warning-border)',
    borderRadius: 'var(--radius-md)',
  },
  alertTitle: {
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--status-warning)',
    marginBottom: '2px',
  },
  alertText: {
    fontSize: '11.5px',
    color: 'var(--text-secondary)',
    lineHeight: 1.4,
  },
};
