import React, { useState, useEffect, useCallback } from 'react';
import {
  AppsTabIcon,
  CheckIcon,
  PlayIcon,
  SearchIcon,
} from '../icons/Icons';
import { AppLogoIcon } from './AppLogoIcon';

interface RealAppItem {
  id: string;
  name: string;
  publisher?: string;
  processName: string;
  iconType?: string;
  iconDataUrl?: string;
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
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filter, setFilter] = useState<'all' | 'running' | 'installed'>('all');
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
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
        setApps([]);
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
        setStatusMessage(`Dispatched ${app.name}`);
        setTimeout(() => fetchApps(), 1000);
      } else {
        setStatusMessage(`Launch response: ${app.name} (${res?.error || 'dispatched'})`);
      }
    } else {
      setStatusMessage(`Selected ${app.name}`);
    }
    setTimeout(() => {
      setStatusMessage(null);
    }, 2500);
  };

  const categories = [
    'ALL',
    'System & OS',
    'Development',
    'Browsers',
    'Utilities',
    'Communication',
    'Productivity',
    'Media & Design',
    'AI & Inference',
  ];

  const filteredApps = apps.filter((app) => {
    // Status Filter
    if (filter === 'running' && !app.isRunning) return false;
    if (filter === 'installed' && !app.installed) return false;

    // Category Filter
    if (selectedCategory !== 'ALL' && app.category !== selectedCategory) {
      return false;
    }

    // Search Query Filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = (app.name || '').toLowerCase().includes(q);
      const matchProc = (app.processName || '').toLowerCase().includes(q);
      const matchPub = (app.publisher || '').toLowerCase().includes(q);
      const matchCat = (app.category || '').toLowerCase().includes(q);
      if (!matchName && !matchProc && !matchPub && !matchCat) return false;
    }

    return true;
  });

  return (
    <div style={styles.container}>
      {/* 1. Header Row */}
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

      {/* 2. Live Search Bar */}
      <div style={styles.searchContainer}>
        <SearchIcon size={14} color="var(--text-muted)" />
        <input
          type="text"
          placeholder="Search applications, executable (e.g. Chrome, VS Code, explorer.exe)..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          style={styles.searchInput}
        />
        {searchQuery && (
          <button
            type="button"
            style={styles.clearBtn}
            onClick={() => setSearchQuery('')}
            title="Clear search"
          >
            ×
          </button>
        )}
      </div>

      {/* 3. Category Filter Strip */}
      <div style={styles.categoryScroll}>
        {categories.map((cat) => {
          const isCatSelected = selectedCategory === cat;
          const count = cat === 'ALL' ? apps.length : apps.filter((a) => a.category === cat).length;
          if (count === 0 && cat !== 'ALL') return null;

          return (
            <button
              key={cat}
              type="button"
              style={{
                ...styles.categoryBtn,
                backgroundColor: isCatSelected ? 'var(--accent-primary)' : 'var(--bg-surface)',
                color: isCatSelected ? '#ffffff' : 'var(--text-secondary)',
                borderColor: isCatSelected ? 'var(--accent-primary)' : 'var(--border-subtle)',
              }}
              onClick={() => setSelectedCategory(cat)}
            >
              <span>{cat}</span>
              <span
                style={{
                  ...styles.catCount,
                  backgroundColor: isCatSelected ? 'rgba(255,255,255,0.25)' : 'var(--bg-subtle)',
                  color: isCatSelected ? '#ffffff' : 'var(--text-muted)',
                }}
              >
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Toast Notice */}
      {statusMessage && (
        <div style={styles.toast}>
          <CheckIcon size={13} color="var(--accent-green)" />
          <span>{statusMessage}</span>
        </div>
      )}

      {/* 4. Applications List Body */}
      {isLoading && apps.length === 0 ? (
        <div style={styles.emptyState}>Probing running Windows processes and installed software...</div>
      ) : filteredApps.length === 0 ? (
        <div style={styles.emptyState}>
          {searchQuery
            ? `No applications matched "${searchQuery}". Try a different keyword.`
            : typeof window !== 'undefined' && !window.orbitDesktop
            ? 'Native Electron Desktop Companion host required for live Windows application discovery.'
            : 'No target applications discovered for the selected filter.'}
        </div>
      ) : (
        <div style={styles.appList}>
          {filteredApps.map((app) => {
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
                      backgroundColor: app.isRunning ? 'rgba(16, 185, 129, 0.08)' : 'var(--bg-subtle)',
                    }}
                  >
                    <AppLogoIcon app={app} size={22} />
                  </div>
                  <div style={styles.appHead}>
                    <div style={styles.appNameRow}>
                      <span style={styles.appName}>{app.name}</span>
                      <span style={styles.categoryBadge}>{app.category || 'App'}</span>
                      {app.isRunning && <span style={styles.runningBadge}>ACTIVE</span>}
                    </div>
                    <div style={styles.appProcess}>
                      {app.processName} • {app.publisher || 'Software'}
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
    padding: '12px 18px 24px 18px',
    gap: '10px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '8px',
    borderBottom: '1px solid var(--border-subtle)',
    flexShrink: 0,
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
  filterGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
    flexShrink: 0,
  },
  filterBtn: {
    padding: '3px 8px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '10.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  searchContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    padding: '7px 10px',
    boxShadow: 'var(--shadow-card)',
    flexShrink: 0,
  },
  searchInput: {
    flex: 1,
    border: 'none',
    backgroundColor: 'transparent',
    fontSize: '11.5px',
    color: 'var(--text-primary)',
    outline: 'none',
    fontFamily: 'inherit',
  },
  clearBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: '15px',
    cursor: 'pointer',
    padding: '0 2px',
    lineHeight: 1,
  },
  categoryScroll: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    overflowX: 'auto',
    padding: '2px 0 4px 0',
    scrollbarWidth: 'none',
    flexShrink: 0,
    minHeight: '30px',
  },
  categoryBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '4px 10px',
    borderRadius: 'var(--radius-full)',
    border: '1px solid',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    flexShrink: 0,
    transition: 'all var(--transition-fast)',
  },
  catCount: {
    fontSize: '9.5px',
    padding: '1px 5px',
    borderRadius: '10px',
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
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
    flexShrink: 0,
  },
  emptyState: {
    textAlign: 'center',
    padding: '32px 16px',
    color: 'var(--text-muted)',
    fontSize: '11.5px',
    lineHeight: 1.4,
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
    width: 34,
    height: 34,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    border: '1px solid var(--border-subtle)',
  },
  appHead: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  appNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
  },
  appName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  categoryBadge: {
    fontSize: '8.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
  },
  runningBadge: {
    fontSize: '8.5px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
    letterSpacing: '0.04em',
  },
  appProcess: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    marginTop: '1px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
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
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
  },
};
