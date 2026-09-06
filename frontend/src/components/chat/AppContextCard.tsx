import React, { useState } from 'react';
import { VsCodeIcon, ChevronRightIcon, CheckCircleIcon } from '../icons/Icons';

interface AppContextCardProps {
  appName?: string;
  statusText?: string;
  icon?: React.ReactNode;
}

export const AppContextCard: React.FC<AppContextCardProps> = ({
  appName = 'Visual Studio Code',
  statusText = 'Opening application...',
  icon = <VsCodeIcon size={26} />,
}) => {
  const [isFocused, setIsFocused] = useState(false);

  const handleCardClick = () => {
    setIsFocused(true);
    setTimeout(() => {
      setIsFocused(false);
    }, 2500);
  };

  return (
    <div
      style={{
        ...styles.card,
        borderColor: isFocused ? 'var(--accent-primary)' : 'var(--border-default)',
      }}
      onClick={handleCardClick}
      title="Click to Focus Application"
    >
      <div style={styles.leftCol}>
        <div style={styles.appIconWrap}>{icon}</div>
        <div style={styles.textWrap}>
          <div style={styles.appName}>{appName}</div>
          <div style={styles.statusText}>
            {isFocused ? 'Window Focused & OCR Grounded' : statusText}
          </div>
        </div>
      </div>

      <div style={styles.rightCol}>
        {isFocused ? (
          <CheckCircleIcon size={16} color="var(--accent-green)" />
        ) : (
          <ChevronRightIcon size={16} color="#94a3b8" />
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: '12px',
    padding: '12px 14px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    boxShadow: 'var(--shadow-card)',
    marginTop: '10px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    userSelect: 'none',
  },
  leftCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  appIconWrap: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  textWrap: {
    display: 'flex',
    flexDirection: 'column',
  },
  appName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  statusText: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginTop: '2px',
  },
  rightCol: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
};
