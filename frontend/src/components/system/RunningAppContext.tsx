import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { TerminalIcon, CheckIcon } from '../icons/Icons';

export const RunningAppContext: React.FC = () => {
  const { observedWindows } = useSystem();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <TerminalIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>OBSERVED APPLICATION WINDOWS</span>
        </div>
        <span style={styles.countBadge}>{observedWindows.length} Active</span>
      </div>

      <div style={styles.windowList}>
        {observedWindows.map((win) => (
          <div
            key={win.hwnd}
            style={{
              ...styles.winRow,
              backgroundColor: win.isForeground ? '#f8faff' : 'var(--bg-app)',
              borderColor: win.isForeground ? 'var(--accent-primary)' : 'var(--border-subtle)',
            }}
          >
            <div style={styles.winLeft}>
              <div style={styles.titleRow}>
                <span style={styles.winTitle}>{win.title}</span>
                {win.isForeground && (
                  <span style={styles.fgBadge}>
                    <CheckIcon size={9} color="var(--accent-green)" /> Foreground
                  </span>
                )}
              </div>
              <div style={styles.metaRow}>
                <span>{win.processName}</span>
                <span>•</span>
                <span style={styles.hwndText}>{win.hwnd}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '4px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  cardTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  countBadge: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  windowList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  winRow: {
    padding: '7px 9px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  winLeft: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    overflow: 'hidden',
    flex: 1,
  },
  titleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  winTitle: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
    flex: 1,
  },
  fgBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  hwndText: {
    fontFamily: 'Consolas, monospace',
    fontSize: '9.5px',
  },
};
