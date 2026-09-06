import React, { useState } from 'react';
import { ChatMessage } from '../../types/chat';
import { XCircleIcon, AlertTriangleIcon } from '../icons/Icons';

interface ErrorMessageProps {
  message: ChatMessage;
}

export const ErrorMessage: React.FC<ErrorMessageProps> = ({ message }) => {
  const [showDetails, setShowDetails] = useState(false);
  const err = message.errorDetail;

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.titleRow}>
            <XCircleIcon size={16} color="var(--status-error)" />
            <span style={styles.title}>RUNTIME ERROR</span>
            {err?.code && (
              <span style={styles.codeBadge}>{err.code}</span>
            )}
          </div>
          <span style={styles.time}>{message.timestamp}</span>
        </div>

        <div style={styles.content}>
          {message.content}
        </div>

        {err?.details && (
          <div style={styles.detailsContainer}>
            <button
              onClick={() => setShowDetails(!showDetails)}
              style={styles.detailsToggle}
            >
              {showDetails ? 'Hide Diagnostics ▲' : 'View Diagnostics ▼'}
            </button>
            {showDetails && (
              <pre style={styles.detailsPre}>
                {typeof err.details === 'string' ? err.details : JSON.stringify(err.details, null, 2)}
              </pre>
            )}
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
    backgroundColor: 'var(--status-error-subtle)',
    border: '1px solid var(--status-error-border)',
    borderRadius: 'var(--radius-md)',
    padding: 'var(--space-3) var(--space-4)',
    boxShadow: 'var(--shadow-sm)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '6px',
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  title: {
    fontSize: '11px',
    fontWeight: 700,
    color: 'var(--status-error)',
    letterSpacing: '0.06em',
  },
  codeBadge: {
    fontFamily: 'var(--font-mono)',
    fontSize: '10px',
    backgroundColor: 'var(--bg-app)',
    color: 'var(--status-error)',
    padding: '1px 6px',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--status-error-border)',
  },
  time: {
    fontSize: '9.5px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  content: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-primary)',
    lineHeight: 1.45,
  },
  detailsContainer: {
    marginTop: 'var(--space-2)',
  },
  detailsToggle: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: '11px',
    cursor: 'pointer',
    padding: 0,
    fontWeight: 600,
  },
  detailsPre: {
    marginTop: '6px',
    padding: 'var(--space-2) var(--space-3)',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--border-subtle)',
    fontSize: '11px',
    color: 'var(--text-secondary)',
    overflowX: 'auto',
  },
};
