import React, { useState, useEffect } from 'react';
import { OrbitGradientLogo, PinIcon, MinimizeIcon, CloseIcon } from '../icons/Icons';
import { useTaskConsole } from '../../context/TaskConsoleContext';

export interface HeaderProps {
  onNavigateToChat?: () => void;
}

export const Header: React.FC<HeaderProps> = ({ onNavigateToChat }) => {
  const [isPinned, setIsPinned] = useState(false);
  const { inputMode, startNewConversation } = useTaskConsole();

  useEffect(() => {
    if ((window as any).orbitDesktop?.isPinned) {
      (window as any).orbitDesktop.isPinned().then((pinned: boolean) => {
        setIsPinned(pinned);
      });
    }
  }, []);

  const handleTogglePin = async () => {
    if ((window as any).orbitDesktop?.togglePin) {
      const pinned = await (window as any).orbitDesktop.togglePin();
      setIsPinned(pinned);
    }
  };

  const handleMinimize = () => {
    (window as any).orbitDesktop?.minimize?.();
  };

  const handleClose = () => {
    (window as any).orbitDesktop?.close?.();
  };

  const handleNewConversation = () => {
    startNewConversation();
    onNavigateToChat?.();
  };

  return (
    <header style={styles.header} className="drag-region">
      {/* Brand Group - Click to Start New Conversation */}
      <div 
        style={styles.brandGroup}
        className="no-drag"
        onClick={handleNewConversation}
        title={inputMode === 'task' ? 'Start new Assistant conversation' : 'Start new Chatbot conversation'}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            handleNewConversation();
          }
        }}
      >
        <div style={styles.logoWrap}>
          <OrbitGradientLogo size={36} />
        </div>
        <div style={styles.titleWrap}>
          <div style={styles.title}>O R B I T</div>
          <div style={styles.subtitle}>
            {inputMode === 'task' ? 'Autonomous Desktop Assistant' : 'Conversational AI Chatbot'}
          </div>
        </div>
      </div>

      {/* Window Controls */}
      <div style={styles.controlsGroup} className="no-drag">
        <button
          style={{
            ...styles.controlBtn,
            color: isPinned ? 'var(--accent-primary)' : 'var(--text-secondary)',
          }}
          onClick={handleTogglePin}
          title={isPinned ? 'Unpin from Top' : 'Pin Always on Top'}
        >
          <PinIcon size={16} isPinned={isPinned} />
        </button>

        <button
          style={styles.controlBtn}
          onClick={handleMinimize}
          title="Minimize"
        >
          <MinimizeIcon size={14} />
        </button>

        <button
          style={{ ...styles.controlBtn, ...styles.closeBtn }}
          onClick={handleClose}
          title="Close"
        >
          <CloseIcon size={14} />
        </button>
      </div>
    </header>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '14px 18px 10px 18px',
    backgroundColor: 'var(--bg-app)',
    userSelect: 'none',
  },
  brandGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
    cursor: 'pointer',
    padding: '3px 8px',
    marginLeft: '-8px',
    borderRadius: 'var(--radius-md)',
    transition: 'background-color var(--transition-fast), transform var(--transition-fast)',
    outline: 'none',
  },
  logoWrap: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    transition: 'transform var(--transition-fast)',
  },
  titleWrap: {
    display: 'flex',
    flexDirection: 'column',
  },
  title: {
    fontSize: '15px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '0.14em',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginTop: '1px',
  },
  controlsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  controlBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 28,
    height: 28,
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    background: 'transparent',
    color: 'var(--text-secondary)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  closeBtn: {
    color: 'var(--text-secondary)',
  },
};
