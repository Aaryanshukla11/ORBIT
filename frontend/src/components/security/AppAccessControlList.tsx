import React, { useState } from 'react';
import { useSecurity } from '../../context/SecurityContext';
import { PolicyLevel, AppGranularPermissions } from '../../types/security';
import {
  AppsTabIcon,
  SearchIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckIcon,
  ShieldIcon,
} from '../icons/Icons';
import { AppLogoIcon } from '../apps/AppLogoIcon';

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

  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [expandedAppId, setExpandedAppId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedAppId((prev) => (prev === id ? null : id));
  };

  const categories = [
    'ALL',
    'System & OS',
    'Utilities',
    'Browsers',
    'Development',
    'AI & Inference',
    'Communication',
    'Productivity',
    'Media & Design',
  ];

  const filteredApps = appPolicies.filter((app) => {
    // Filter by Category
    if (selectedCategory !== 'ALL' && app.category !== selectedCategory) {
      return false;
    }

    // Filter by search
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchName = (app.name || '').toLowerCase().includes(q);
      const matchPub = (app.publisher || '').toLowerCase().includes(q);
      const matchProc = (app.processName || '').toLowerCase().includes(q);
      const matchCat = (app.category || '').toLowerCase().includes(q);
      if (!matchName && !matchPub && !matchProc && !matchCat) return false;
    }

    // Filter by policy
    if (filterPolicy !== 'ALL') {
      if (app.accessLevel !== filterPolicy) return false;
    }

    return true;
  });

  const handleBulkAllowCategory = (cat: string) => {
    appPolicies.forEach((app) => {
      if (cat === 'ALL' || app.category === cat) {
        updateAppPolicy(app.id, 'ALLOW');
      }
    });
  };

  return (
    <div style={styles.card}>
      {/* Header & Stats Strip */}
      <div style={styles.cardHeader}>
        <div style={styles.titleWrap}>
          <AppsTabIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>APPLICATION ACCESS POLICIES</span>
        </div>
        <div style={styles.headerMeta}>
          <span style={styles.countBadge}>{filteredApps.length} of {appPolicies.length} Software</span>
        </div>
      </div>

      {/* Category Pills Strip */}
      <div style={styles.categoryScroll}>
        {categories.map((cat) => {
          const isCatSelected = selectedCategory === cat;
          const count = cat === 'ALL' ? appPolicies.length : appPolicies.filter((a) => a.category === cat).length;
          if (count === 0 && cat !== 'ALL') return null;

          return (
            <button
              key={cat}
              type="button"
              style={{
                ...styles.categoryBtn,
                backgroundColor: isCatSelected ? 'var(--accent-primary)' : 'var(--bg-app)',
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

      {/* Search and Policy Filter Strip */}
      <div style={styles.controlsRow}>
        <div style={styles.searchBox}>
          <SearchIcon size={13} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Search system software, executable (e.g. explorer.exe, code, chrome)..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
          {searchQuery && (
            <button
              type="button"
              style={styles.clearSearchBtn}
              onClick={() => setSearchQuery('')}
            >
              ×
            </button>
          )}
        </div>

        <div style={styles.policyFilterRow}>
          <span style={styles.filterLabel}>Policy Filter:</span>
          <div style={styles.filterPills}>
            {(['ALL', 'ALLOW', 'ASK', 'DENY'] as const).map((lvl) => (
              <button
                key={lvl}
                type="button"
                style={{
                  ...styles.filterBtn,
                  backgroundColor: filterPolicy === lvl ? 'var(--bg-surface)' : 'transparent',
                  color:
                    filterPolicy === lvl
                      ? lvl === 'ALLOW'
                        ? 'var(--accent-green)'
                        : lvl === 'DENY'
                        ? 'var(--accent-red)'
                        : 'var(--accent-primary)'
                      : 'var(--text-muted)',
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
      </div>

      {/* Applications List */}
      <div style={styles.appList}>
        {filteredApps.length === 0 ? (
          <div style={styles.emptySearch}>
            <span>No applications matched query. Clear search or select another category.</span>
          </div>
        ) : (
          filteredApps.map((app) => {
            const isExpanded = expandedAppId === app.id;
            const isUpdating = updatingPolicyId === app.id;
            const isRunning = app.lastAccessed === 'Active Process' || app.lastAccessed === 'Active Runtime' || app.lastAccessed === 'Active in OS';

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
                    <div style={styles.appIconWrap}>
                      <AppLogoIcon app={app} size={16} />
                    </div>
                    <div style={styles.appTextCol}>
                      <div style={styles.appNameRow}>
                        <span style={styles.appName}>{app.name}</span>
                        <span style={styles.categoryBadge}>{app.category || 'Application'}</span>
                        {isRunning && <span style={styles.runningBadge}>ACTIVE</span>}
                      </div>
                      <span style={styles.appPublisher}>
                        {app.publisher || 'Microsoft Windows'} • {app.processName}
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
                      title={isExpanded ? 'Collapse granular permissions' : 'Configure granular sub-permissions'}
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
                          { key: 'windowFocus', label: 'Window Focus & Positioning' },
                          { key: 'keyboardInput', label: 'Synthetic Keyboard Keystrokes' },
                          { key: 'mouseInteraction', label: 'Mouse Movement & Click Actions' },
                          { key: 'textReading', label: 'Accessibility UI Text Reading' },
                          { key: 'screenObservation', label: 'Visual Screen Frame Capture' },
                        ] as const
                      ).map(({ key, label }) => {
                        const currentVal = app.permissions[key as keyof AppGranularPermissions] || 'ALLOW';

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
          })
        )}
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
    fontSize: '10.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  headerMeta: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  countBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
  },
  categoryScroll: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    overflowX: 'auto',
    padding: '2px 0 4px 0',
    scrollbarWidth: 'none',
    flexShrink: 0,
    minHeight: '28px',
  },
  categoryBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-full)',
    border: '1px solid',
    fontSize: '10px',
    fontWeight: 600,
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    flexShrink: 0,
    transition: 'all var(--transition-fast)',
  },
  catCount: {
    fontSize: '9px',
    padding: '0 4px',
    borderRadius: '8px',
    fontWeight: 700,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  controlsRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    flexShrink: 0,
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
  clearSearchBtn: {
    background: 'none',
    border: 'none',
    color: 'var(--text-muted)',
    fontSize: '14px',
    cursor: 'pointer',
    padding: '0 2px',
  },
  policyFilterRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: '2px',
  },
  filterLabel: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  filterPills: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-full)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
  },
  filterBtn: {
    padding: '2px 7px',
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
    paddingRight: '2px',
  },
  emptySearch: {
    textAlign: 'center',
    padding: '20px 12px',
    color: 'var(--text-muted)',
    fontSize: '11px',
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
    width: 28,
    height: 28,
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
    gap: '5px',
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
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
  },
  runningBadge: {
    fontSize: '8px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '1px 4px',
    borderRadius: '3px',
    letterSpacing: '0.04em',
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
    padding: '2px 6px',
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
    padding: '1px 5px',
    borderRadius: 'calc(var(--radius-sm) - 1px)',
    border: 'none',
    fontSize: '8.5px',
    cursor: 'pointer',
  },
};
