import React, { useEffect, useRef } from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { UserMessage } from './UserMessage';
import { AssistantMessage } from './AssistantMessage';
import { SystemEventMessage } from './SystemEventMessage';
import { TaskExecutionMessage } from './TaskExecutionMessage';
import { ErrorMessage } from './ErrorMessage';
import { ActionAuthPrompt } from './ActionAuthPrompt';
import { TerminalIcon, OrbitLogoIcon } from '../icons/Icons';
import { useOrbit } from '../../context/OrbitContext';

export const MessageList: React.FC = () => {
  const { messages } = useTaskConsole();
  const { connectionState } = useOrbit();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  if (messages.length === 0) {
    return (
      <div style={styles.emptyContainer}>
        <div style={styles.emptyIconCircle}>
          <OrbitLogoIcon size={36} color="var(--accent-primary)" />
        </div>
        <div style={styles.emptyTitle}>ORBIT Task Console Ready</div>
        <p style={styles.emptyDescription}>
          {connectionState === 'CONNECTED'
            ? 'Submit an autonomous task instruction or conversational query using the composer below.'
            : 'Gateway is currently disconnected. Start the ORBIT Python backend to dispatch tasks.'}
        </p>
        <div style={styles.emptyHints}>
          <div style={styles.hintItem}>
            <span style={styles.hintTag}>Task Mode</span>
            <span style={styles.hintText}>Full autonomous planning, verification, and UI execution</span>
          </div>
          <div style={styles.hintItem}>
            <span style={styles.hintTag}>Chat Mode</span>
            <span style={styles.hintText}>Conversational assistance, status inquiries, and diagnostics</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.listContainer}>
      {messages.map((msg) => {
        switch (msg.type) {
          case 'user':
            return <UserMessage key={msg.id} message={msg} />;
          case 'assistant':
            return <AssistantMessage key={msg.id} message={msg} />;
          case 'system':
            return <SystemEventMessage key={msg.id} message={msg} />;
          case 'task_event':
            return <TaskExecutionMessage key={msg.id} message={msg} />;
          case 'error':
            return <ErrorMessage key={msg.id} message={msg} />;
          case 'action_auth':
            return <ActionAuthPrompt key={msg.id} message={msg} />;
          default:
            return <AssistantMessage key={msg.id} message={msg} />;
        }
      })}
      <div ref={bottomRef} style={{ height: 1 }} />
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  listContainer: {
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
    padding: 'var(--space-4)',
  },
  emptyContainer: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 'var(--space-8)',
    textAlign: 'center',
  },
  emptyIconCircle: {
    width: 64,
    height: 64,
    borderRadius: 'var(--radius-lg)',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-default)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 'var(--space-4)',
  },
  emptyTitle: {
    fontSize: 'var(--font-size-lg)',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-2)',
  },
  emptyDescription: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
    maxWidth: 480,
    lineHeight: 1.5,
    marginBottom: 'var(--space-6)',
  },
  emptyHints: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
    width: '100%',
    maxWidth: 440,
  },
  hintItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    padding: '8px 12px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
  },
  hintTag: {
    fontSize: '11px',
    fontWeight: 700,
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-primary-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--accent-primary-border)',
  },
  hintText: {
    fontSize: '11.5px',
    color: 'var(--text-secondary)',
  },
};
