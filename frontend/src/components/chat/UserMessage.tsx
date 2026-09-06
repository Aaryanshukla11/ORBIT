import React from 'react';
import { ChatMessage } from '../../types/chat';

interface UserMessageProps {
  message: ChatMessage;
}

export const UserMessage: React.FC<UserMessageProps> = ({ message }) => {
  const isTask = message.metadata?.mode === 'task';

  return (
    <div style={styles.container}>
      <div style={styles.bubble}>
        <div style={styles.header}>
          <div style={styles.senderGroup}>
            <span style={styles.sender}>OPERATOR</span>
            <span style={{
              ...styles.modeBadge,
              backgroundColor: isTask ? 'var(--accent-primary-subtle)' : 'var(--bg-surface)',
              color: isTask ? 'var(--accent-primary)' : 'var(--text-muted)',
              borderColor: isTask ? 'var(--accent-primary-border)' : 'var(--border-subtle)',
            }}>
              {isTask ? 'AUTONOMOUS TASK' : 'CONVERSATION'}
            </span>
          </div>
          <span style={styles.time}>{message.timestamp}</span>
        </div>
        <div style={styles.content} data-selectable="true">
          {message.content}
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'flex-end',
    width: '100%',
    margin: 'var(--space-2) 0',
  },
  bubble: {
    maxWidth: '75%',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: 'var(--space-3) var(--space-4)',
    boxShadow: 'var(--shadow-sm)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 'var(--space-4)',
    marginBottom: '6px',
  },
  senderGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  sender: {
    fontSize: '10.5px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    letterSpacing: '0.06em',
  },
  modeBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    letterSpacing: '0.04em',
    padding: '1px 6px',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid',
  },
  time: {
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  content: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-primary)',
    lineHeight: 1.5,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
};
