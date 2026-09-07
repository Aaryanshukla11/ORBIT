import React from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { ChatTabIcon, BotAutoIcon } from '../icons/Icons';

interface ModeSwitchProps {
  fullWidth?: boolean;
}

export const ModeSwitch: React.FC<ModeSwitchProps> = ({ fullWidth = true }) => {
  const { inputMode, setInputMode } = useTaskConsole();
  const isAssistant = inputMode === 'task';
  const isChatbot = inputMode === 'chat';

  return (
    <div
      style={{
        ...styles.switchContainer,
        width: fullWidth ? '100%' : 'auto',
      }}
      role="tablist"
      aria-label="ORBIT Operating Mode"
    >
      {/* Assistant Mode Button */}
      <button
        type="button"
        role="tab"
        aria-selected={isAssistant}
        style={{
          ...styles.modeBtn,
          ...(isAssistant ? styles.activeBtn : styles.inactiveBtn),
        }}
        onClick={() => setInputMode('task')}
        title="Assistant Mode: Autonomous desktop automation, planning & OS actions"
      >
        <BotAutoIcon
          size={15}
          color={isAssistant ? '#ffffff' : 'var(--text-secondary)'}
        />
        <div style={styles.labelCol}>
          <span style={{ ...styles.primaryLabel, color: isAssistant ? '#ffffff' : 'var(--text-primary)' }}>
            Assistant
          </span>
          <span style={{ ...styles.secondaryLabel, color: isAssistant ? 'rgba(255,255,255,0.85)' : 'var(--text-muted)' }}>
            Autonomous Agent
          </span>
        </div>
        {isAssistant && <div style={styles.activePillGlow} />}
      </button>

      {/* Chatbot Mode Button */}
      <button
        type="button"
        role="tab"
        aria-selected={isChatbot}
        style={{
          ...styles.modeBtn,
          ...(isChatbot ? styles.activeBtn : styles.inactiveBtn),
        }}
        onClick={() => setInputMode('chat')}
        title="Chatbot Mode: Conversational AI for coding, advice & reasoning"
      >
        <ChatTabIcon
          size={15}
          color={isChatbot ? '#ffffff' : 'var(--text-secondary)'}
        />
        <div style={styles.labelCol}>
          <span style={{ ...styles.primaryLabel, color: isChatbot ? '#ffffff' : 'var(--text-primary)' }}>
            Chatbot
          </span>
          <span style={{ ...styles.secondaryLabel, color: isChatbot ? 'rgba(255,255,255,0.85)' : 'var(--text-muted)' }}>
            Conversational AI
          </span>
        </div>
        {isChatbot && <div style={styles.activePillGlow} />}
      </button>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  switchContainer: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: '14px',
    padding: '4px',
    gap: '4px',
    boxShadow: '0 1px 4px rgba(0, 0, 0, 0.04)',
    userSelect: 'none',
  },
  modeBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '8px',
    border: 'none',
    borderRadius: '10px',
    padding: '7px 10px',
    cursor: 'pointer',
    position: 'relative',
    transition: 'all 0.2s cubic-bezier(0.4, 0, 0.2, 1)',
  },
  activeBtn: {
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    boxShadow: '0 2px 8px rgba(37, 99, 235, 0.35)',
  },
  inactiveBtn: {
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
  },
  labelCol: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'flex-start',
    textAlign: 'left',
  },
  primaryLabel: {
    fontSize: '12px',
    fontWeight: 700,
    lineHeight: 1.2,
    letterSpacing: '0.01em',
  },
  secondaryLabel: {
    fontSize: '9.5px',
    fontWeight: 500,
    lineHeight: 1.1,
    marginTop: '1px',
  },
  activePillGlow: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: '10px',
    pointerEvents: 'none',
  },
};
