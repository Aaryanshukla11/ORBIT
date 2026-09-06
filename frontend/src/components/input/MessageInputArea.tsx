import React, { useState, useRef, useEffect } from 'react';
import {
  ExpandScanIcon,
  SendArrowIcon,
  BotAutoIcon,
  GlobeWebIcon,
  PaperclipIcon,
  MicIcon,
  ChevronDownIcon,
} from '../icons/Icons';
import { useOrbit } from '../../context/OrbitContext';

interface MessageInputAreaProps {
  onSendMessage?: (text: string) => void;
}

export const MessageInputArea: React.FC<MessageInputAreaProps> = ({ onSendMessage }) => {
  const [text, setText] = useState('');
  const [autoMode, setAutoMode] = useState(true);
  const [webEnabled, setWebEnabled] = useState(true);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const { submitTask, connectionState } = useOrbit();

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 120)}px`;
    }
  }, [text]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!text.trim()) return;

    if (onSendMessage) {
      onSendMessage(text);
    } else {
      submitTask(text);
    }

    setText('');
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  return (
    <div style={styles.outerWrapper}>
      <div style={styles.inputContainer}>
        {/* Top Textarea Row */}
        <div style={styles.textRow}>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask ORBIT anything..."
            rows={1}
            style={styles.textarea}
          />

          <div style={styles.topRightActions}>
            <button
              type="button"
              style={styles.iconBtn}
              title="Expand View"
            >
              <ExpandScanIcon size={17} color="#94a3b8" />
            </button>

            <button
              type="button"
              style={{
                ...styles.sendBtn,
                opacity: text.trim() ? 1 : 0.9,
              }}
              onClick={handleSend}
              title="Send Message (Enter)"
            >
              <SendArrowIcon size={15} color="#ffffff" />
            </button>
          </div>
        </div>

        {/* Bottom Pill Buttons Row */}
        <div style={styles.bottomPillRow}>
          <div style={styles.leftPillsGroup}>
            {/* Auto Mode Pill */}
            <button
              type="button"
              style={styles.pillBtn}
              onClick={() => setAutoMode(!autoMode)}
              title="Toggle Automation Mode"
            >
              <BotAutoIcon size={15} color="#475569" />
              <span style={styles.pillText}>Auto</span>
              <ChevronDownIcon size={12} color="#94a3b8" />
            </button>

            {/* Web Access Pill */}
            <button
              type="button"
              style={styles.pillBtn}
              onClick={() => setWebEnabled(!webEnabled)}
              title="Toggle Web Access"
            >
              <GlobeWebIcon size={15} color="#475569" />
              <span style={styles.pillText}>Web</span>
              <ChevronDownIcon size={12} color="#94a3b8" />
            </button>
          </div>

          <div style={styles.rightPillsGroup}>
            {/* Attachment Button */}
            <button
              type="button"
              style={styles.roundPillBtn}
              title="Attach File"
            >
              <PaperclipIcon size={16} color="#475569" />
            </button>

            {/* Microphone Button */}
            <button
              type="button"
              style={styles.roundPillBtn}
              title="Voice Input"
            >
              <MicIcon size={16} color="#475569" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  outerWrapper: {
    padding: '0 18px 16px 18px',
    backgroundColor: 'var(--bg-app)',
    flexShrink: 0,
  },
  inputContainer: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: '16px',
    padding: '12px 14px 10px 14px',
    boxShadow: 'var(--shadow-input)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  textRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  textarea: {
    flex: 1,
    backgroundColor: 'transparent',
    border: 'none',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-sans)',
    fontSize: '13.5px',
    lineHeight: 1.4,
    resize: 'none',
    outline: 'none',
    padding: '2px 0',
  },
  topRightActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  iconBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 32,
    height: 32,
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  sendBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 34,
    height: 34,
    borderRadius: '10px',
    border: 'none',
    backgroundColor: 'var(--accent-primary)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    boxShadow: '0 2px 6px rgba(37, 99, 235, 0.3)',
  },
  bottomPillRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: '2px',
  },
  leftPillsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  rightPillsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  pillBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 10px',
    borderRadius: 'var(--radius-full)',
    backgroundColor: 'var(--bg-pill)',
    border: '1px solid var(--border-subtle)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  pillText: {
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  roundPillBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 30,
    height: 30,
    borderRadius: '50%',
    backgroundColor: 'var(--bg-pill)',
    border: '1px solid var(--border-subtle)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
