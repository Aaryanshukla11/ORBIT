import React, { useState, useEffect, useCallback } from 'react';
import {
  AppsTabIcon,
  VsCodeIcon,
  TerminalIcon,
  GlobeWebIcon,
  ExpandScanIcon,
  CheckIcon,
  ServerIcon,
  PlayIcon,
} from '../icons/Icons';

interface RealAppItem {
  id: string;
  name: string;
  publisher?: string;
  processName: string;
  iconType?: string;
  category?: string;
  installed: boolean;
  isRunning: boolean;
  state: string;
  windowTitle: string;
  launchCommand?: string;
}

export const AppsView: React.FC = () => {
  const [apps, setApps] = useState<RealAppItem[]>([]);
  const [activeApp, setActiveApp] = useState<string | null>(null);
  const [filter, setFilter] = useState<'all' | 'running' | 'installed'>('all');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const fetchApps = useCallback(async () => {
    setIsLoading(true);
    try {
      if (typeof window !== 'undefined' && window.orbitDesktop && window.orbitDesktop.getInstalledApps) {
        const discovered = await window.orbitDesktop.getInstalledApps();
        if (discovered && Array.isArray(discovered)) {
          setApps(discovered);
          if (!activeApp && discovered.length > 0) {
            setActiveApp(discovered[0].id);
          }
        }
      } else {
        // Fallback truthful minimal list
        setApps([
          {
            id: 'notepad',
            name: 'Notepad',
            processName: 'notepad.exe',
            category: 'Utilities',
            installed: true,
            isRunning: false,
            state: 'Installed (OS Default)',
            windowTitle: 'Notepad Text Editor',
            launchCommand: 'notepad.exe',
          },
        ]);
      }
    } catch (err: any) {
      console.warn('[AppsView] Failed to query installed apps:', err);
    } finally {
      setIsLoading(false);
    }
  }, [activeApp]);

  useEffect(() => {
    fetchApps();
    const interval = setInterval(fetchApps, 5000);
    return () => clearInterval(interval);
  }, [fetchApps]);

  const handleLaunchOrFocus = async (app: RealAppItem) => {
    if (typeof window !== 'undefined' && window.orbitDesktop && window.orbitDesktop.launchApp && app.launchCommand) {
      const res = await window.orbitDesktop.launchApp(app.launchCommand);
      if (res && res.success) {
        setStatusMessage(`Successfully dispatched: ${app.name}`);
        setTimeout(() => fetchApps(), 1000);
      } else {
        setStatusMessage(`Launch notice: ${app.name} (${res?.error || 'dispatched'})`);
      }
    } else {
      setStatusMessage(`Selected ${app.name}`);
    }
    setTimeout(() => {
      setStatusMessage(null);
    }, 2500);
  };

  const filteredApps = apps.filter((app) => {
    if (filter === 'running') return app.isRunning;
    if (filter === 'installed') return app.installed;
    return true;
  });

  const getAppIcon = (iconType?: string) => {
    switch (iconType) {
      case 'code':
        return VsCodeIcon;
      case 'terminal':
        return TerminalIcon;
      case 'browser':
        return GlobeWebIcon;
      case 'ai':
        return ServerIcon;
      default:
        return AppsTabIcon;
    }
  };

  return (
    <div style={styles.container}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <AppsTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Target Applications</span>
        </div>
        <div style={styles.filterGroup}>
          {(['all', 'running', 'installed'] as const).map((f) => (
            <button
              key={f}
              type="button"
              style={{
                ...styles.filterBtn,
                backgroundColor: filter === f ? 'var(--bg-surface)' : 'transparent',
                color: filter === f ? 'var(--accent-primary)' : 'var(--text-muted)',
                fontWeight: filter === f ? 700 : 500,
                boxShadow: filter === f ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setFilter(f)}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {statusMessage && (
        <div style={styles.toast}>
          <CheckIcon size={13} color="var(--accent-green)" />
          <span>{statusMessage}</span>
        </div>
      )}

      {isLoading && apps.length === 0 ? (
        <div style={styles.emptyState}>Probing running Windows processes and installed software...</div>
      ) : (
        <div style={styles.appList}>
          {filteredApps.map((app) => {
            const Icon = getAppIcon(app.iconType);
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
                  <div
                    style={{
                      ...styles.iconBox,
                      backgroundColor: app.isRunning ? 'rgba(16, 185, 129, 0.1)' : 'var(--bg-subtle)',
                    }}
                  >
                    <Icon size={18} color={app.isRunning ? 'var(--accent-green)' : 'var(--accent-primary)'} />
                  </div>
                  <div style={styles.appHead}>
                    <div style={styles.appNameRow}>
                      <span style={styles.appName}>{app.name}</span>
                      {app.isRunning && <span style={styles.runningBadge}>ACTIVE</span>}
                    </div>
                    <div style={styles.appProcess}>
                      {app.processName} • {app.state}
                    </div>
                  </div>
                </div>

                <div style={styles.windowTitleBox}>
                  <span style={styles.windowTitleText}>{app.windowTitle}</span>
                </div>

                <div style={styles.actionRow}>
                  <button
                    type="button"
                    style={{
                      ...styles.actionBtnPrimary,
                      backgroundColor: app.isRunning ? 'var(--accent-primary)' : 'var(--bg-subtle)',
                      color: app.isRunning ? '#ffffff' : 'var(--text-primary)',
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      handleLaunchOrFocus(app);
                    }}
                  >
                    <PlayIcon size={11} color={app.isRunning ? '#ffffff' : 'var(--text-primary)'} />
                    <span>{app.isRunning ? 'Focus Window' : 'Launch Application'}</span>
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
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
