import React from 'react';
import { ChatMessage } from '../../types/chat';
import { OrbitLogoIcon, ModelsIcon } from '../icons/Icons';
import { useOrbit } from '../../context/OrbitContext';

interface AssistantMessageProps {
  message: ChatMessage;
}

export const AssistantMessage: React.FC<AssistantMessageProps> = ({ message }) => {
  const { activeModel } = useOrbit();

  return (
    <div style={styles.container}>
      <div style={styles.bubble}>
        <div style={styles.header}>
          <div style={styles.brandRow}>
            <div style={styles.iconWrapper}>
              <OrbitLogoIcon size={14} color="var(--accent-cyan)" />
            </div>
            <span style={styles.sender}>ORBIT DESKTOP</span>
            {activeModel && (
              <span style={styles.modelTag}>
                <ModelsIcon size={11} />
                {activeModel.modelId}
              </span>
            )}
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
    justifyContent: 'flex-start',
    width: '100%',
    margin: 'var(--space-2) 0',
  },
  bubble: {
    maxWidth: '85%',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
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
  brandRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  iconWrapper: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  sender: {
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--accent-cyan)',
    letterSpacing: '0.06em',
  },
  modelTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
    padding: '1px 6px',
    borderRadius: 'var(--radius-xs)',
  },
  time: {
    fontSize: '10px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  content: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-primary)',
    lineHeight: 1.55,
    whiteSpace: 'pre-wrap',
    wordBreak: 'break-word',
  },
};
