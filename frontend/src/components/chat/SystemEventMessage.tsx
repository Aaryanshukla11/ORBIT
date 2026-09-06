import React from 'react';
import { ChatMessage } from '../../types/chat';
import { ShieldIcon, AlertTriangleIcon, CheckCircleIcon } from '../icons/Icons';

interface SystemEventMessageProps {
  message: ChatMessage;
}

export const SystemEventMessage: React.FC<SystemEventMessageProps> = ({ message }) => {
  const isTakeover = message.content.includes('Takeover') || message.content.includes('Preemption');

  return (
    <div style={styles.container}>
      <div style={{
        ...styles.pill,
        borderColor: isTakeover ? 'var(--status-warning-border)' : 'var(--border-subtle)',
        backgroundColor: isTakeover ? 'var(--status-warning-subtle)' : 'var(--bg-surface-elevated)',
      }}>
        {isTakeover ? (
          <AlertTriangleIcon size={13} color="var(--status-warning)" />
        ) : (
          <ShieldIcon size={13} color="var(--text-muted)" />
        )}
        <span style={{
          ...styles.text,
          color: isTakeover ? 'var(--status-warning)' : 'var(--text-secondary)',
        }}>
          {message.content}
        </span>
        <span style={styles.time}>{message.timestamp}</span>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    justifyContent: 'center',
    width: '100%',
    margin: 'var(--space-2) 0',
  },
  pill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
    padding: '3px 12px',
    borderRadius: 'var(--radius-full)',
    border: '1px solid',
    fontSize: '11px',
    maxWidth: '90%',
  },
  text: {
    lineHeight: 1.3,
  },
  time: {
    fontSize: '9.5px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
    marginLeft: '4px',
  },
};
