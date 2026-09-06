import React from 'react';
import { useOrbit } from '../context/OrbitContext';
import { useTaskConsole } from '../context/TaskConsoleContext';
import { MessageList } from '../components/chat/MessageList';
import { ChatComposer } from '../components/chat/ChatComposer';
import { TaskExecutionCard } from '../components/task/TaskExecutionCard';
import { PlanInspector } from '../components/task/PlanInspector';
import { ActiveTaskControls } from '../components/task/ActiveTaskControls';
import { ModelsIcon, TerminalIcon, PlugIcon, UnplugIcon } from '../components/icons/Icons';

export const ChatConsolePage: React.FC = () => {
  const { connectionState, activeModel } = useOrbit();
  const { activeTask, activePlan } = useTaskConsole();

  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* Section A: Page Header */}
      <header style={styles.header}>
        <div style={styles.headerTitleGroup}>
          <h1 style={styles.title}>Chat / Task Console</h1>
          <p style={styles.subtitle}>
            Converse with ORBIT or dispatch autonomous desktop task instructions.
          </p>
        </div>

        {/* Status Indicator */}
        <div style={styles.headerMetaRow}>
          <div style={styles.statusPill}>
            <ModelsIcon size={14} color={activeModel ? 'var(--accent-primary)' : 'var(--text-muted)'} />
            <span style={styles.statusLabel}>Model:</span>
            <span style={{
              ...styles.statusValue,
              color: activeModel ? 'var(--text-primary)' : 'var(--text-muted)',
            }}>
              {activeModel ? `${activeModel.provider} / ${activeModel.modelId}` : 'Unavailable (Disconnected)'}
            </span>
          </div>

          <div style={{
            ...styles.statusPill,
            borderColor: isConnected ? 'var(--status-online-border)' : 'var(--status-error-border)',
            backgroundColor: isConnected ? 'var(--status-online-subtle)' : 'var(--status-error-subtle)',
          }}>
            <span style={{
              ...styles.dot,
              backgroundColor: isConnected ? 'var(--status-online)' : 'var(--status-error)',
            }} />
            <span style={{
              ...styles.statusValue,
              color: isConnected ? 'var(--status-online)' : 'var(--status-error)',
            }}>
              {isConnected ? 'Gateway Connected' : 'Gateway Disconnected'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Split Layout: Left (Conversation + Composer), Right (Task Card + Plan Inspector) */}
      <div style={styles.mainGrid}>
        {/* Left Column: Messages & Composer */}
        <div style={styles.leftColumn}>
          {/* Active Task Controls Header (if task is active) */}
          <ActiveTaskControls />

          {/* Conversation Area */}
          <div className="card" style={styles.conversationCard}>
            <MessageList />
          </div>

          {/* Section E: Desktop Command Composer */}
          <ChatComposer />
        </div>

        {/* Right Column: Structured Task Execution Card & Plan Inspector */}
        <div style={styles.rightColumn}>
          {activeTask ? (
            <>
              <TaskExecutionCard task={activeTask} />
              <PlanInspector plan={activePlan || activeTask.plan || null} currentStepIndex={activeTask.current_step_index} />
            </>
          ) : (
            <div className="card" style={styles.idleRightCard}>
              <div style={styles.idleIconWrap}>
                <TerminalIcon size={28} color="var(--text-muted)" />
              </div>
              <div style={styles.idleTitle}>No Active Execution</div>
              <p style={styles.idleText}>
                When an autonomous task is dispatched, the real-time execution card and M1.8 structured plan breakdown will appear here.
              </p>
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
    gap: 'var(--space-4)',
    height: '100%',
    maxWidth: 1600,
    margin: '0 auto',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 'var(--space-2)',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
  },
  headerTitleGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  title: {
    fontSize: 'var(--font-size-xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-muted)',
  },
  headerMetaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  statusPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    fontSize: 'var(--font-size-xs)',
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  statusLabel: {
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  statusValue: {
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
  },
  mainGrid: {
    display: 'grid',
    gridTemplateColumns: 'minmax(500px, 1.8fr) minmax(340px, 1.2fr)',
    gap: 'var(--space-4)',
    flex: 1,
    minHeight: 0,
    overflow: 'hidden',
  },
  leftColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-3)',
    height: '100%',
    minHeight: 0,
    overflow: 'hidden',
  },
  conversationCard: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    padding: 0,
    overflow: 'hidden',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    minHeight: 0,
  },
  rightColumn: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
    height: '100%',
    overflowY: 'auto',
    paddingRight: '2px',
  },
  idleRightCard: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    textAlign: 'center',
    padding: 'var(--space-8) var(--space-4)',
    gap: 'var(--space-3)',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    minHeight: 240,
  },
  idleIconWrap: {
    width: 48,
    height: 48,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-input)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    border: '1px solid var(--border-subtle)',
  },
  idleTitle: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  idleText: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-muted)',
    maxWidth: 280,
    lineHeight: 1.4,
  },
};
