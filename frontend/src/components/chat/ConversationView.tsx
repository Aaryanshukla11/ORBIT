import React, { useRef, useEffect } from 'react';
import {
  OrbitGradientLogo,
  ShieldIcon,
  CheckCircleIcon,
  XCircleIcon,
} from '../icons/Icons';
import { TaskExecutionCard } from './TaskExecutionCard';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useOrbit } from '../../context/OrbitContext';

export const ConversationView: React.FC = () => {
  const { messages, isProcessing, authorizeAction, inputMode } = useTaskConsole();
  const { connectionState, systemHealth } = useOrbit();
  const scrollEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isProcessing]);

  const isAssistant = inputMode === 'task';
  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* 1. Clean Landing Hero Page (When no active conversation) */}
      {messages.length === 0 ? (
        <div style={styles.landingContainer}>
          {/* Main Brand & Identity Section */}
          <div style={styles.heroSection}>
            <div style={styles.logoWrap}>
              <OrbitGradientLogo size={56} />
            </div>
            <div style={styles.heroTitleRow}>
              <h1 style={styles.heroTitle}>
                {isAssistant ? 'ORBIT ASSISTANT' : 'ORBIT CHATBOT'}
              </h1>
              <span
                style={{
                  ...styles.modeBadge,
                  backgroundColor: isAssistant ? 'rgba(37, 99, 235, 0.1)' : 'rgba(16, 185, 129, 0.1)',
                  color: isAssistant ? 'var(--accent-primary)' : 'var(--accent-green)',
                }}
              >
                {isAssistant ? 'Autonomous Desktop Partner' : 'Conversational AI Intelligence'}
              </span>
            </div>
            <p style={styles.heroSubtitle}>
              {isAssistant
                ? 'Your executive Windows desktop automation partner. Enter a command below to plan, click, type, and automate local applications.'
                : 'Your conversational AI co-pilot. Ask programming questions, explore system architecture, or reason through complex workflows.'}
            </p>
          </div>

          {/* Real-time Subsystem Status Pills */}
          <div style={styles.statusPillsRow}>
            <div style={styles.statusPill}>
              <span
                style={{
                  ...styles.statusDot,
                  backgroundColor: isConnected ? 'var(--accent-green)' : '#f59e0b',
                }}
              />
              <span>{isConnected ? 'Gateway Online' : 'Connecting...'}</span>
            </div>

            <div style={styles.statusPill}>
              <span
                style={{
                  ...styles.statusDot,
                  backgroundColor: isAssistant ? 'var(--accent-primary)' : 'var(--accent-green)',
                }}
              />
              <span>{isAssistant ? 'Win32 Actions Ready' : 'LLM Chat Ready'}</span>
            </div>

            <div style={styles.statusPill}>
              <span
                style={{
                  ...styles.statusDot,
                  backgroundColor: systemHealth.takeoverArmed ? '#f59e0b' : 'var(--accent-green)',
                }}
              />
              <span>{systemHealth.takeoverArmed ? 'Takeover Intercept' : 'Safety Guard Armed'}</span>
            </div>
          </div>
        </div>
      ) : (
        /* 2. Dynamic Message Stream */
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
                  {msg.plan && <TaskExecutionCard plan={msg.plan} error={msg.errorDetail} />}
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
    padding: '8px 18px 16px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '16px',
    userSelect: 'none',
  },
  landingContainer: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '24px',
    padding: '40px 10px 20px 10px',
    flex: 1,
  },
  heroSection: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    textAlign: 'center',
    gap: '10px',
    maxWidth: '420px',
  },
  logoWrap: {
    marginBottom: '6px',
  },
  heroTitleRow: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    gap: '6px',
  },
  heroTitle: {
    fontSize: '22px',
    fontWeight: 800,
    letterSpacing: '0.08em',
    color: 'var(--text-primary)',
    margin: 0,
  },
  modeBadge: {
    fontSize: '11px',
    fontWeight: 700,
    padding: '4px 12px',
    borderRadius: '12px',
    letterSpacing: '0.02em',
  },
  heroSubtitle: {
    fontSize: '12.5px',
    lineHeight: 1.5,
    color: 'var(--text-secondary)',
    margin: 0,
  },
  statusPillsRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    flexWrap: 'wrap',
  },
  statusPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 12px',
    borderRadius: '16px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-subtle)',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    boxShadow: '0 1px 2px rgba(0,0,0,0.03)',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
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
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: 700,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  userName: {
    fontSize: '12.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  timestamp: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
  userBubble: {
    backgroundColor: 'var(--bg-user-bubble)',
    color: 'var(--text-primary)',
    padding: '10px 14px',
    borderRadius: '14px',
    borderTopLeftRadius: '3px',
    fontSize: '13px',
    lineHeight: 1.45,
    marginLeft: '34px',
    border: '1px solid var(--border-default)',
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
  },
  orbitName: {
    fontSize: '12.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '0.04em',
  },
  orbitContentWrapper: {
    display: 'flex',
    gap: '12px',
    marginLeft: '12px',
  },
  verticalGuideLine: {
    width: '2px',
    backgroundColor: 'var(--border-subtle)',
    borderRadius: '1px',
    marginTop: '2px',
    marginBottom: '2px',
  },
  orbitMainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    paddingTop: '2px',
  },
  assistantBubble: {
    backgroundColor: 'var(--bg-surface)',
    color: 'var(--text-primary)',
    padding: '10px 14px',
    borderRadius: '14px',
    borderTopLeftRadius: '3px',
    fontSize: '13px',
    lineHeight: 1.45,
    border: '1px solid var(--border-default)',
    boxShadow: 'var(--shadow-card)',
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
