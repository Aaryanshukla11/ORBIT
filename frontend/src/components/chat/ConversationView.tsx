import React, { useRef, useEffect } from 'react';
import { OrbitGradientLogo, SparklesIcon, ShieldIcon, CheckCircleIcon, XCircleIcon } from '../icons/Icons';
import { TaskExecutionCard } from './TaskExecutionCard';
import { AppContextCard } from './AppContextCard';
import { useTaskConsole } from '../../context/TaskConsoleContext';

export const ConversationView: React.FC = () => {
  const { messages, isProcessing, sendUserMessage, authorizeAction } = useTaskConsole();
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  const quickPrompts = [
    'Open my code editor and summarize the main components of the ORBIT project.',
    'Inspect active terminal logs and check for build warnings.',
    'Focus Google Chrome and ground DOM selectors.',
  ];

  return (
    <div style={styles.container}>
      {/* If no user messages yet, show interactive welcome & initial scenario */}
      {messages.length === 0 ? (
        <>
          {/* Default Hero Scenario */}
          <div style={styles.userSection}>
            <div style={styles.userAvatarRow}>
              <div style={styles.userAvatarCircle}>
                <span>A</span>
              </div>
              <div style={styles.userName}>You</div>
              <div style={styles.timestamp}>11:22 AM</div>
            </div>

            <div style={styles.userBubble} data-selectable="true">
              Open my code editor and summarize the main components of the ORBIT project.
            </div>
          </div>

          <div style={styles.orbitSection}>
            <div style={styles.orbitHeaderRow}>
              <div style={styles.orbitAvatar}>
                <OrbitGradientLogo size={26} />
              </div>
              <div style={styles.orbitName}>ORBIT</div>
              <div style={styles.timestamp}>11:22 AM</div>
            </div>

            <div style={styles.orbitContentWrapper}>
              <div style={styles.verticalGuideLine} />

              <div style={styles.orbitMainContent}>
                <div style={styles.statusHeading}>Analyzing your request...</div>

                {/* Interactive Task Execution Checklist Card */}
                <TaskExecutionCard />

                {/* Interactive App Context Card */}
                <AppContextCard />
              </div>
            </div>
          </div>

          {/* Suggested Quick Prompts */}
          <div style={styles.suggestionsContainer}>
            <div style={styles.suggestionsHeader}>
              <SparklesIcon size={12} color="var(--accent-primary)" />
              <span>Suggested Automations (Click to run):</span>
            </div>
            <div style={styles.promptsList}>
              {quickPrompts.map((prompt, idx) => (
                <button
                  key={idx}
                  type="button"
                  style={styles.promptChip}
                  onClick={() => sendUserMessage(prompt)}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        </>
      ) : (
        /* Dynamic message stream */
        messages.map((msg) => {
          if (msg.type === 'user') {
            return (
              <div key={msg.id} style={styles.userSection}>
                <div style={styles.userAvatarRow}>
                  <div style={styles.userAvatarCircle}>
                    <span>A</span>
                  </div>
                  <div style={styles.userName}>You</div>
                  <div style={styles.timestamp}>{msg.timestamp}</div>
                </div>
                <div style={styles.userBubble}>{msg.content}</div>
              </div>
            );
          }

          if (msg.type === 'action_auth' && msg.actionAuth) {
            const auth = msg.actionAuth;
            return (
              <div key={msg.id} style={styles.authCard}>
                <div style={styles.authHeader}>
                  <ShieldIcon size={16} color="var(--accent-primary)" />
                  <span style={styles.authTitle}>Safety Authorization Gate (Tier {auth.tier})</span>
                </div>
                <div style={styles.authDesc}>{auth.description}</div>
                {!auth.handled ? (
                  <div style={styles.authBtnRow}>
                    <button
                      type="button"
                      style={styles.approveBtn}
                      onClick={() => authorizeAction(auth.task_id, auth.action_id, true)}
                    >
                      <CheckCircleIcon size={13} color="#ffffff" />
                      Authorize Execution
                    </button>
                    <button
                      type="button"
                      style={styles.rejectBtn}
                      onClick={() => authorizeAction(auth.task_id, auth.action_id, false)}
                    >
                      <XCircleIcon size={13} color="var(--accent-red)" />
                      Reject
                    </button>
                  </div>
                ) : (
                  <div style={styles.authHandledNotice}>
                    {auth.approved ? 'Approved by Operator' : 'Rejected by Operator'}
                  </div>
                )}
              </div>
            );
          }

          return (
            <div key={msg.id} style={styles.orbitSection}>
              <div style={styles.orbitHeaderRow}>
                <div style={styles.orbitAvatar}>
                  <OrbitGradientLogo size={26} />
                </div>
                <div style={styles.orbitName}>ORBIT</div>
                <div style={styles.timestamp}>{msg.timestamp}</div>
              </div>

              <div style={styles.orbitContentWrapper}>
                <div style={styles.verticalGuideLine} />
                <div style={styles.orbitMainContent}>
                  <div style={styles.assistantBubble}>{msg.content}</div>
                  {msg.plan && <TaskExecutionCard />}
                </div>
              </div>
            </div>
          );
        })
      )}

      {/* Typing / Thinking Live Indicator */}
      {isProcessing && (
        <div style={styles.processingIndicator}>
          <div style={styles.spinnerCircle} />
          <span>ORBIT agent executing workspace step...</span>
        </div>
      )}

      <div ref={scrollEndRef} />
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    overflowY: 'auto',
    padding: '10px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
  },
  userSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  userAvatarRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  userAvatarCircle: {
    width: 26,
    height: 26,
    borderRadius: '50%',
    backgroundColor: '#5b82a6',
    color: '#ffffff',
    fontSize: '12px',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  userName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  timestamp: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginLeft: '2px',
  },
  userBubble: {
    marginLeft: '34px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: '14px',
    padding: '12px 16px',
    fontSize: '13px',
    color: 'var(--text-primary)',
    lineHeight: 1.45,
    boxShadow: 'var(--shadow-card)',
  },
  orbitSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  orbitHeaderRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  orbitAvatar: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  orbitName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  orbitContentWrapper: {
    display: 'flex',
    position: 'relative',
    marginLeft: '12px',
    paddingLeft: '22px',
  },
  verticalGuideLine: {
    position: 'absolute',
    left: 0,
    top: 4,
    bottom: 8,
    width: 2,
    backgroundColor: '#3b82f6',
    borderRadius: '1px',
    opacity: 0.8,
  },
  orbitMainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  statusHeading: {
    fontSize: '12.5px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
    marginBottom: '2px',
  },
  assistantBubble: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: '12px',
    padding: '10px 14px',
    fontSize: '13px',
    color: 'var(--text-primary)',
    lineHeight: 1.4,
    boxShadow: 'var(--shadow-card)',
  },
  suggestionsContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    marginTop: '6px',
    paddingLeft: '34px',
  },
  suggestionsHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  promptsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  promptChip: {
    textAlign: 'left',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 12px',
    fontSize: '12px',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
  },
  authCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--accent-primary)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    marginLeft: '34px',
    boxShadow: 'var(--shadow-card)',
  },
  authHeader: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  authTitle: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
  },
  authDesc: {
    fontSize: '12px',
    color: 'var(--text-primary)',
    lineHeight: 1.35,
  },
  authBtnRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginTop: '4px',
  },
  approveBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '6px 12px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-green)',
    border: 'none',
    color: '#ffffff',
    fontSize: '11.5px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  rejectBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '6px 12px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--accent-red)',
    color: 'var(--accent-red)',
    fontSize: '11.5px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  authHandledNotice: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  processingIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 14px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary-subtle)',
    color: 'var(--accent-primary)',
    fontSize: '11.5px',
    fontWeight: 600,
    marginLeft: '34px',
  },
  spinnerCircle: {
    width: 12,
    height: 12,
    border: '2px solid var(--accent-primary)',
    borderTopColor: 'transparent',
    borderRadius: '50%',
  },
};
