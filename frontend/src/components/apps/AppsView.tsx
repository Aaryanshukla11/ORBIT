import React, { useState } from 'react';
import { AppsTabIcon, VsCodeIcon, TerminalIcon, GlobeWebIcon, ExpandScanIcon, CheckIcon } from '../icons/Icons';

export const AppsView: React.FC = () => {
  const [activeApp, setActiveApp] = useState<string>('vscode');
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const apps = [
    {
      id: 'vscode',
      name: 'Visual Studio Code',
      icon: VsCodeIcon,
      process: 'Code.exe',
      state: 'Running (Foreground)',
      isForeground: true,
      windowTitle: 'ORBIT - Visual Studio Code',
      capabilities: ['Code Editing', 'Terminal', 'Git Integration'],
    },
    {
      id: 'terminal',
      name: 'Windows Terminal',
      icon: TerminalIcon,
      process: 'wt.exe',
      state: 'Running (Background)',
      isForeground: false,
      windowTitle: 'PowerShell 7 - Administrator',
      capabilities: ['Shell Execution', 'Python Env', 'CLI Tools'],
    },
    {
      id: 'chrome',
      name: 'Google Chrome',
      icon: GlobeWebIcon,
      process: 'chrome.exe',
      state: 'Running (Background)',
      isForeground: false,
      windowTitle: 'Vite + React Localhost',
      capabilities: ['DOM Inspection', 'Web Automation', 'DevTools'],
    },
  ];

  const handleAction = (appName: string, action: string) => {
    setStatusMessage(`${action} triggered on ${appName}`);
    setTimeout(() => {
      setStatusMessage(null);
    }, 2000);
  };

  return (
    <div style={styles.container}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <AppsTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Target Applications</span>
        </div>
        <span style={styles.countBadge}>{apps.length} Active Targets</span>
      </div>

      {statusMessage && (
        <div style={styles.toast}>
          <CheckIcon size={13} color="var(--accent-green)" />
          <span>{statusMessage}</span>
        </div>
      )}

      <div style={styles.appList}>
        {apps.map((app) => {
          const Icon = app.icon;
          const isSelected = activeApp === app.id;

          return (
            <div
              key={app.id}
              style={{
                ...styles.appCard,
                borderColor: isSelected ? 'var(--accent-primary)' : 'var(--border-subtle)',
              }}
              onClick={() => setActiveApp(app.id)}
            >
              <div style={styles.appTop}>
                <div style={styles.iconBox}>
                  <Icon size={20} color="var(--accent-primary)" />
                </div>
                <div style={styles.appHead}>
                  <div style={styles.appName}>{app.name}</div>
                  <div style={styles.appProcess}>{app.process} • {app.state}</div>
                </div>
              </div>

              <div style={styles.windowTitleBox}>
                <span style={styles.windowTitleText}>{app.windowTitle}</span>
              </div>

              <div style={styles.actionRow}>
                <button
                  type="button"
                  style={styles.actionBtnPrimary}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAction(app.name, 'Focus');
                  }}
                >
                  Focus Window
                </button>
                <button
                  type="button"
                  style={styles.actionBtnSecondary}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAction(app.name, 'OCR Ground');
                  }}
                >
                  <ExpandScanIcon size={13} color="var(--text-secondary)" />
                  Ground
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    padding: '10px 18px 24px 18px',
    gap: '12px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '8px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  title: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  countBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-full)',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-green-subtle)',
    color: 'var(--accent-green)',
    fontSize: '11px',
    fontWeight: 600,
  },
  appList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  appCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    boxShadow: 'var(--shadow-card)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  appTop: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  iconBox: {
    width: 32,
    height: 32,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  appHead: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  appName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  appProcess: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    marginTop: '1px',
  },
  windowTitleBox: {
    backgroundColor: 'var(--bg-subtle)',
    padding: '4px 8px',
    borderRadius: 'var(--radius-sm)',
    fontSize: '10.5px',
    fontFamily: 'Consolas, monospace',
    color: 'var(--text-secondary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  windowTitleText: {
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  actionRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    marginTop: '2px',
  },
  actionBtnPrimary: {
    flex: 1,
    padding: '5px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    border: 'none',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  actionBtnSecondary: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '5px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
