import React from 'react';
import { ChatMessage } from '../../types/chat';
import { ShieldIcon, CheckCircleIcon, XCircleIcon } from '../icons/Icons';
import { useTaskConsole } from '../../context/TaskConsoleContext';

interface ActionAuthPromptProps {
  message: ChatMessage;
}

export const ActionAuthPrompt: React.FC<ActionAuthPromptProps> = ({ message }) => {
  const { authorizeAction } = useTaskConsole();
  const auth = message.actionAuth;

  if (!auth) return null;

  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.header}>
          <div style={styles.titleRow}>
            <ShieldIcon size={16} color="var(--status-warning)" />
            <span style={styles.title}>OPERATOR CONFIRMATION REQUIRED</span>
            <span className="badge badge-warning">{auth.tier}</span>
          </div>
          <span style={styles.time}>{message.timestamp}</span>
        </div>

        <div style={styles.description}>
          {auth.description || `Agent requests approval to execute high-impact action: ${auth.action_type}`}
        </div>

        {auth.parameters && Object.keys(auth.parameters).length > 0 && (
          <pre style={styles.paramPre}>
            {JSON.stringify(auth.parameters, null, 2)}
          </pre>
        )}

        <div style={styles.actionRow}>
          {auth.handled ? (
            <div style={styles.handledStatus}>
              {auth.approved ? (
                <span className="badge badge-online">
                  <CheckCircleIcon size={12} /> Approved by Operator
                </span>
              ) : (
                <span className="badge badge-error">
                  <XCircleIcon size={12} /> Rejected by Operator
                </span>
              )}
            </div>
          ) : (
            <div style={styles.buttonGroup}>
              <button
                className="btn btn-primary btn-sm"
                onClick={() => authorizeAction(auth.task_id, auth.action_id, true)}
              >
                <CheckCircleIcon size={13} />
                <span>Approve Action</span>
              </button>
              <button
                className="btn btn-danger btn-sm"
                onClick={() => authorizeAction(auth.task_id, auth.action_id, false)}
              >
                <XCircleIcon size={13} />
                <span>Reject & Halt</span>
              </button>
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
    justifyContent: 'flex-start',
    width: '100%',
    margin: 'var(--space-2) 0',
  },
  card: {
    width: '100%',
    maxWidth: '85%',
    backgroundColor: 'var(--status-warning-subtle)',
    border: '1px solid var(--status-warning-border)',
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
    color: 'var(--status-warning)',
    letterSpacing: '0.06em',
  },
  time: {
    fontSize: '9.5px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-primary)',
    lineHeight: 1.45,
  },
  paramPre: {
    marginTop: '6px',
    padding: 'var(--space-2)',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-xs)',
    border: '1px solid var(--border-subtle)',
    fontSize: '10.5px',
    color: 'var(--text-secondary)',
    overflowX: 'auto',
  },
  actionRow: {
    marginTop: 'var(--space-3)',
    display: 'flex',
    justifyContent: 'flex-end',
  },
  buttonGroup: {
    display: 'flex',
    gap: 'var(--space-2)',
  },
  handledStatus: {
    display: 'flex',
  },
};
