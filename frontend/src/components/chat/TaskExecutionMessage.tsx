import React from 'react';
import { ChatMessage } from '../../types/chat';
import { TerminalIcon, CheckCircleIcon, XCircleIcon, RefreshIcon } from '../icons/Icons';

interface TaskExecutionMessageProps {
  message: ChatMessage;
}

export const TaskExecutionMessage: React.FC<TaskExecutionMessageProps> = ({ message }) => {
  const status = message.taskStatus || 'CREATED';
  const isCompleted = status === 'COMPLETED';
  const isFailed = status === 'FAILED' || status === 'CANCELLED';
  const isRunning = status === 'RUNNING' || status === 'VALIDATING' || status === 'READY';

  return (
    <div style={styles.container}>
      <div style={{
        ...styles.card,
        borderColor: isCompleted
          ? 'var(--status-online-border)'
          : isFailed
          ? 'var(--status-error-border)'
          : 'var(--border-default)',
      }}>
        <div style={styles.header}>
          <div style={styles.statusRow}>
            {isCompleted ? (
              <CheckCircleIcon size={14} color="var(--status-online)" />
            ) : isFailed ? (
              <XCircleIcon size={14} color="var(--status-error)" />
            ) : (
              <RefreshIcon size={14} color="var(--accent-primary)" />
            )}
            <span style={styles.title}>
              TASK LIFECYCLE: {message.taskId ? message.taskId.substring(0, 8) : 'ACTIVE'}
            </span>
            <span className={`badge ${
              isCompleted ? 'badge-online' :
              isFailed ? 'badge-error' :
              isRunning ? 'badge-busy' : 'badge-offline'
            }`}>
              {status}
            </span>
          </div>
          <span style={styles.time}>{message.timestamp}</span>
        </div>

        <div style={styles.body}>
          {message.content}
        </div>

        {message.errorDetail && (
          <div style={styles.errorBox}>
            <span style={styles.errorCode}>[{message.errorDetail.code}]</span>
            <span style={styles.errorMessage}>{message.errorDetail.message}</span>
          </div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'flex-start',
    width: '100%',
    margin: 'var(--space-2) 0',
  },
  card: {
    width: '100%',
    maxWidth: '85%',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3)',
    boxShadow: 'var(--shadow-sm)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '4px',
  },
  statusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  title: {
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.05em',
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
  },
  time: {
    fontSize: '9.5px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  body: {
    fontSize: '12px',
    color: 'var(--text-primary)',
    lineHeight: 1.4,
  },
  errorBox: {
    marginTop: '6px',
    padding: '4px 8px',
    backgroundColor: 'var(--status-error-subtle)',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--status-error-border)',
    fontSize: '11px',
    display: 'flex',
    gap: '6px',
    alignItems: 'center',
  },
  errorCode: {
    fontFamily: 'var(--font-mono)',
    fontWeight: 700,
    color: 'var(--status-error)',
  },
  errorMessage: {
    color: 'var(--text-primary)',
  },
};
