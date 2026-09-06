import React, { useState, useRef, useEffect } from 'react';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useOrbit } from '../../context/OrbitContext';
import { PlayIcon, TerminalIcon, ChatIcon, ModelsIcon } from '../icons/Icons';
import { InputMode } from '../../types/chat';

export const ChatComposer: React.FC = () => {
  const { inputMode, setInputMode, sendUserMessage, isProcessing } = useTaskConsole();
  const { connectionState, activeModel } = useOrbit();
  const [text, setText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const isConnected = connectionState === 'CONNECTED';

  // Auto-resize textarea based on content
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleSubmit = () => {
    if (!text.trim() || !isConnected || isProcessing) return;

    const sent = sendUserMessage(text, inputMode);
    if (sent) {
      setText('');
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  return (
    <div className="card card-elevated" style={styles.container}>
      {/* Top Controls Bar inside Composer */}
      <div style={styles.topRow}>
        {/* Mode Selector */}
        <div style={styles.modeToggleGroup}>
          <button
            type="button"
            style={{
              ...styles.modeBtn,
              ...(inputMode === 'task' ? styles.modeBtnActive : {}),
            }}
            onClick={() => setInputMode('task')}
            title="Dispatch Autonomous Task (Full Planning & Execution)"
          >
            <TerminalIcon size={13} />
            <span>Autonomous Task</span>
          </button>

          <button
            type="button"
            style={{
              ...styles.modeBtn,
              ...(inputMode === 'chat' ? styles.modeBtnActive : {}),
            }}
            onClick={() => setInputMode('chat')}
            title="Conversational Assistance & Status Inquiries"
          >
            <ChatIcon size={13} />
            <span>Conversational</span>
          </button>
        </div>

        {/* Active Model Indicator */}
        <div style={styles.modelIndicator}>
          <ModelsIcon size={13} color={activeModel ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <span style={styles.modelLabel}>
            {activeModel ? `${activeModel.provider} / ${activeModel.modelId}` : 'Model Unavailable'}
          </span>
        </div>
      </div>

      {/* Text Area */}
      <div style={styles.inputWrapper}>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            !isConnected
              ? 'WebSocket gateway disconnected. Start backend to dispatch commands...'
              : inputMode === 'task'
              ? "Describe autonomous task to execute on Windows desktop (e.g. 'Open Notepad and write summary report')..."
              : 'Ask a question or request status from ORBIT...'
          }
          disabled={!isConnected}
          rows={2}
          style={{
            ...styles.textarea,
            opacity: !isConnected ? 0.6 : 1,
          }}
        />
      </div>

      {/* Bottom Action Row */}
      <div style={styles.bottomRow}>
        <div style={styles.shortcutsHint}>
          Press <kbd style={styles.kbd}>Enter</kbd> to {inputMode === 'task' ? 'dispatch task' : 'send'}, <kbd style={styles.kbd}>Shift+Enter</kbd> for newline
        </div>

        <button
          type="button"
          className="btn btn-primary"
          onClick={handleSubmit}
          disabled={!isConnected || !text.trim() || isProcessing}
          style={styles.sendBtn}
        >
          <PlayIcon size={14} />
          <span>{isProcessing ? 'Processing...' : inputMode === 'task' ? 'Dispatch Task' : 'Send'}</span>
        </button>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
    padding: 'var(--space-3) var(--space-4)',
    borderTop: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    borderRadius: 'var(--radius-lg)',
  },
  topRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: '4px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  modeToggleGroup: {
    display: 'flex',
    gap: '4px',
    backgroundColor: 'var(--bg-input)',
    padding: '2px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
  },
  modeBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    padding: '3px 10px',
    fontSize: '11px',
    fontWeight: 600,
    background: 'transparent',
    border: 'none',
    color: 'var(--text-muted)',
    borderRadius: 'var(--radius-xs)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  modeBtnActive: {
    backgroundColor: 'var(--bg-surface-elevated)',
    color: 'var(--accent-primary)',
    border: '1px solid var(--border-subtle)',
  },
  modelIndicator: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--text-muted)',
  },
  modelLabel: {
    maxWidth: 260,
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  inputWrapper: {
    width: '100%',
  },
  textarea: {
    width: '100%',
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-sans)',
    fontSize: 'var(--font-size-sm)',
    lineHeight: 1.5,
    resize: 'none',
    outline: 'none',
    padding: '4px 0',
  },
  bottomRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: '4px',
  },
  shortcutsHint: {
    fontSize: '11px',
    color: 'var(--text-muted)',
  },
  kbd: {
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-xs)',
    padding: '1px 5px',
    fontSize: '10px',
    color: 'var(--text-secondary)',
    fontFamily: 'var(--font-mono)',
  },
  sendBtn: {
    padding: '5px 14px',
  },
};
