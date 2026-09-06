import React, { useState } from 'react';
import { useSecurity } from '../../context/SecurityContext';
import { PolicyLevel, AppGranularPermissions } from '../../types/security';
import {
  AppsTabIcon,
  SearchIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  TerminalIcon,
  GlobeWebIcon,
  VsCodeIcon,
  CheckIcon,
} from '../icons/Icons';

export const AppAccessControlList: React.FC = () => {
  const {
    appPolicies,
    updateAppPolicy,
    updateAppGranularPermission,
    searchQuery,
    setSearchQuery,
    filterPolicy,
    setFilterPolicy,
    updatingPolicyId,
  } = useSecurity();

  const [expandedAppId, setExpandedAppId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedAppId((prev) => (prev === id ? null : id));
  };

  const filteredApps = appPolicies.filter((app) => {
    // Filter by search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = app.name.toLowerCase().includes(q);
      const matchPub = app.publisher.toLowerCase().includes(q);
      const matchProc = app.processName.toLowerCase().includes(q);
      if (!matchName && !matchPub && !matchProc) return false;
    }

    // Filter by policy
    if (filterPolicy !== 'ALL') {
      if (app.accessLevel !== filterPolicy) return false;
    }

    return true;
  });

  const getAppIcon = (proc: string) => {
    const p = proc.toLowerCase();
    if (p.includes('code')) return <VsCodeIcon size={18} />;
    if (p.includes('edge') || p.includes('chrome')) return <GlobeWebIcon size={16} color="var(--accent-primary)" />;
    if (p.includes('wt') || p.includes('cmd') || p.includes('powershell')) return <TerminalIcon size={16} color="var(--accent-primary)" />;
    return <AppsTabIcon size={16} color="var(--text-muted)" />;
  };

  return (
    <div style={styles.card}>
      {/* Header & Filter Controls */}
      <div style={styles.cardHeader}>
        <div style={styles.titleWrap}>
          <AppsTabIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>APPLICATION ACCESS POLICIES</span>
        </div>
        <span style={styles.countBadge}>{filteredApps.length} Configured</span>
      </div>

      {/* Search and Filters Strip */}
      <div style={styles.controlsRow}>
        <div style={styles.searchBox}>
          <SearchIcon size={13} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Search installed applications..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
        </div>

        <div style={styles.filterPills}>
          {(['ALL', 'ALLOW', 'ASK', 'DENY'] as const).map((lvl) => (
            <button
              key={lvl}
              type="button"
              style={{
                ...styles.filterBtn,
                backgroundColor: filterPolicy === lvl ? 'var(--bg-surface)' : 'transparent',
                color: filterPolicy === lvl ? 'var(--accent-primary)' : 'var(--text-muted)',
                fontWeight: filterPolicy === lvl ? 700 : 500,
                boxShadow: filterPolicy === lvl ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
              }}
              onClick={() => setFilterPolicy(lvl)}
            >
              {lvl}
            </button>
          ))}
        </div>
      </div>

      {/* Applications List */}
      <div style={styles.appList}>
        {filteredApps.map((app) => {
          const isExpanded = expandedAppId === app.id;
          const isUpdating = updatingPolicyId === app.id;

          return (
            <div
              key={app.id}
              style={{
                ...styles.appItem,
                borderColor: isExpanded ? 'var(--accent-primary)' : 'var(--border-subtle)',
              }}
            >
              {/* App Main Row */}
              <div style={styles.appMainRow} onClick={() => toggleExpand(app.id)}>
                <div style={styles.appLeft}>
                  <div style={styles.appIconWrap}>{getAppIcon(app.processName)}</div>
                  <div style={styles.appTextCol}>
                    <div style={styles.appNameRow}>
                      <span style={styles.appName}>{app.name}</span>
                      <span style={styles.categoryBadge}>{app.category}</span>
                    </div>
                    <span style={styles.appPublisher}>
                      {app.publisher} • {app.processName}
                    </span>
                  </div>
                </div>

                <div style={styles.appRight} onClick={(e) => e.stopPropagation()}>
                  {/* Access Level Selector */}
                  <div style={styles.levelGroup}>
                    {(['ALLOW', 'ASK', 'DENY'] as const).map((lvl) => {
                      const isSelected = app.accessLevel === lvl;

                      let activeBg = 'var(--bg-surface)';
                      let activeColor = 'var(--text-primary)';
                      if (isSelected) {
                        if (lvl === 'ALLOW') {
                          activeBg = 'var(--accent-green-subtle)';
                          activeColor = 'var(--accent-green)';
                        } else if (lvl === 'ASK') {
                          activeBg = 'var(--accent-primary-subtle)';
                          activeColor = 'var(--accent-primary)';
                        } else if (lvl === 'DENY') {
                          activeBg = 'var(--accent-red-subtle)';
                          activeColor = 'var(--accent-red)';
                        }
                      }

                      return (
                        <button
                          key={lvl}
                          type="button"
                          disabled={isUpdating}
                          style={{
                            ...styles.lvlBtn,
                            backgroundColor: isSelected ? activeBg : 'transparent',
                            color: isSelected ? activeColor : 'var(--text-muted)',
                            fontWeight: isSelected ? 700 : 500,
                          }}
                          onClick={() => updateAppPolicy(app.id, lvl)}
                        >
                          {lvl.charAt(0) + lvl.slice(1).toLowerCase()}
                        </button>
                      );
                    })}
                  </div>

                  <button
                    type="button"
                    style={styles.expandBtn}
                    onClick={() => toggleExpand(app.id)}
                    title={isExpanded ? 'Collapse permissions' : 'Expand granular permissions'}
                  >
                    {isExpanded ? (
                      <ChevronDownIcon size={12} color="var(--text-muted)" />
                    ) : (
                      <ChevronRightIcon size={12} color="var(--text-muted)" />
                    )}
                  </button>
                </div>
              </div>

              {/* Granular Permissions Expanded Box */}
              {isExpanded && (
                <div style={styles.granularBox}>
                  <div style={styles.granularHeader}>Granular Subsystem Permissions:</div>
                  <div style={styles.granularGrid}>
                    {(
                      [
                        { key: 'windowFocus', label: 'Window Focus' },
                        { key: 'keyboardInput', label: 'Keyboard Input' },
                        { key: 'mouseInteraction', label: 'Mouse Click' },
                        { key: 'textReading', label: 'Text Reading' },
                        { key: 'screenObservation', label: 'Screen Observation' },
                      ] as const
                    ).map(({ key, label }) => {
                      const currentVal = app.permissions[key as keyof AppGranularPermissions];

                      return (
                        <div key={key} style={styles.granularRow}>
                          <span style={styles.granularLabel}>{label}</span>
                          <div style={styles.miniPills}>
                            {(['ALLOW', 'ASK', 'DENY'] as const).map((l) => (
                              <button
                                key={l}
                                type="button"
                                style={{
                                  ...styles.miniPillBtn,
                                  backgroundColor:
                                    currentVal === l
                                      ? l === 'ALLOW'
                                        ? 'var(--accent-green-subtle)'
                                        : l === 'ASK'
                                        ? 'var(--accent-primary-subtle)'
                                        : 'var(--accent-red-subtle)'
                                      : 'transparent',
                                  color:
                                    currentVal === l
                                      ? l === 'ALLOW'
                                        ? 'var(--accent-green)'
                                        : l === 'ASK'
                                        ? 'var(--accent-primary)'
                                        : 'var(--accent-red)'
                                      : 'var(--text-muted)',
                                  fontWeight: currentVal === l ? 700 : 500,
                                }}
                                onClick={() =>
                                  updateAppGranularPermission(
                                    app.id,
                                    key as keyof AppGranularPermissions,
                                    l
                                  )
                                }
                              >
                                {l}
                              </button>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          );
        })}
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
    gap: '10px',
    userSelect: 'none',
  },
  cardHeader: {
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
  controlsRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  searchBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '5px 8px',
  },
  searchInput: {
    flex: 1,
    backgroundColor: 'transparent',
    border: 'none',
    fontSize: '11px',
    color: 'var(--text-primary)',
    outline: 'none',
    fontFamily: 'inherit',
  },
  filterPills: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
  },
  filterBtn: {
    flex: 1,
    padding: '3px 4px',
    borderRadius: 'var(--radius-full)',
    border: 'none',
    fontSize: '9.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  appList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  appItem: {
    backgroundColor: 'var(--bg-app)',
    border: '1px solid',
    borderRadius: 'var(--radius-md)',
    display: 'flex',
    flexDirection: 'column',
    transition: 'all var(--transition-fast)',
    overflow: 'hidden',
  },
  appMainRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    cursor: 'pointer',
    gap: '8px',
  },
  appLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    overflow: 'hidden',
    flex: 1,
  },
  appIconWrap: {
    width: 26,
    height: 26,
    borderRadius: 'var(--radius-sm)',
    backgroundColor: 'var(--bg-surface)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    border: '1px solid var(--border-subtle)',
  },
  appTextCol: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  appNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  appName: {
    fontSize: '12px',
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
    padding: '1px 4px',
    borderRadius: 'var(--radius-sm)',
  },
  appPublisher: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  appRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  levelGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-surface)',
    borderRadius: 'var(--radius-sm)',
    padding: '1px',
    border: '1px solid var(--border-subtle)',
  },
  lvlBtn: {
    padding: '2px 5px',
    borderRadius: 'calc(var(--radius-sm) - 1px)',
    border: 'none',
    fontSize: '9.5px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  expandBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 20,
    height: 20,
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
  },
  granularBox: {
    padding: '8px 10px',
    backgroundColor: 'var(--bg-surface)',
    borderTop: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  granularHeader: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
  },
  granularGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  granularRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '2px 0',
  },
  granularLabel: {
    fontSize: '10.5px',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  miniPills: {
    display: 'flex',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-sm)',
    padding: '1px',
    border: '1px solid var(--border-subtle)',
  },
  miniPillBtn: {
    padding: '1px 4px',
    borderRadius: 'calc(var(--radius-sm) - 1px)',
    border: 'none',
    fontSize: '8.5px',
    cursor: 'pointer',
  },
};
