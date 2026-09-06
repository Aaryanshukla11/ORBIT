import React from 'react';
import { useOrbit } from '../../context/OrbitContext';
import { NAVIGATION_ITEMS } from '../../constants/navigation';
import {
  OrbitLogoIcon,
  HomeIcon,
  ChatIcon,
  ActivityIcon,
  ModelsIcon,
  SystemIcon,
  SecurityIcon,
  HistoryIcon,
  SettingsIcon,
  PlugIcon,
  UnplugIcon,
} from '../icons/Icons';
import { NavigationPage } from '../../types';

const iconMap: Record<string, React.FC<any>> = {
  HomeIcon,
  ChatIcon,
  ActivityIcon,
  ModelsIcon,
  SystemIcon,
  SecurityIcon,
  HistoryIcon,
  SettingsIcon,
};

export const Sidebar: React.FC = () => {
  const { activePage, setActivePage, connectionState } = useOrbit();

  const isConnected = connectionState === 'CONNECTED';

  return (
    <aside style={styles.sidebar}>
      {/* Brand Header */}
      <div style={styles.brandContainer}>
        <div style={styles.logoBadge}>
          <OrbitLogoIcon size={20} color="var(--accent-primary)" />
        </div>
        <div style={styles.brandText}>
          <div style={styles.brandTitle}>ORBIT</div>
          <div style={styles.brandSubtitle}>Desktop Intelligence</div>
        </div>
      </div>

      {/* Navigation Section */}
      <nav style={styles.navSection}>
        <div style={styles.navGroupLabel}>NAVIGATION</div>
        <ul style={styles.navList}>
          {NAVIGATION_ITEMS.map((item) => {
            const IconComponent = iconMap[item.iconName] || HomeIcon;
            const isActive = activePage === item.id;

            return (
              <li key={item.id} style={styles.navItem}>
                <button
                  style={{
                    ...styles.navButton,
                    ...(isActive ? styles.navButtonActive : {}),
                  }}
                  onClick={() => setActivePage(item.id)}
                  title={`${item.label} (${item.shortcut})`}
                >
                  {/* Left Active Pillar Indicator */}
                  {isActive && <div style={styles.activeIndicator} />}

                  <span style={{
                    ...styles.iconWrapper,
                    color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                  }}>
                    <IconComponent size={18} />
                  </span>

                  <span style={{
                    ...styles.navLabel,
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    fontWeight: isActive ? 600 : 500,
                  }}>
                    {item.label}
                  </span>

                  <span style={styles.shortcutBadge}>{item.shortcut.replace('Ctrl+', '')}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Bottom Connection Status Card */}
      <div style={styles.footerCard}>
        <div style={styles.connectionHeader}>
          <div style={styles.connectionStatusRow}>
            <span
              style={{
                ...styles.statusDot,
                backgroundColor:
                  connectionState === 'CONNECTED'
                    ? 'var(--status-online)'
                    : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
                    ? 'var(--status-warning)'
                    : 'var(--status-error)',
              }}
            />
            <span style={styles.connectionStatusText}>
              {connectionState === 'CONNECTED'
                ? 'Gateway Online'
                : connectionState === 'CONNECTING'
                ? 'Connecting...'
                : connectionState === 'RECONNECTING'
                ? 'Reconnecting...'
                : 'Offline'}
            </span>
          </div>
          <span style={styles.versionBadge}>v2.0</span>
        </div>
        <div style={styles.gatewayEndpoint}>ws://127.0.0.1:8765</div>
      </div>
    </aside>
  );
};

const styles: Record<string, React.CSSProperties> = {
  sidebar: {
    width: 'var(--sidebar-width)',
    minWidth: 'var(--sidebar-width)',
    maxWidth: 'var(--sidebar-width)',
    height: '100%',
    backgroundColor: 'var(--bg-surface)',
    borderRight: '1px solid var(--border-subtle)',
    display: 'flex',
    flexDirection: 'column',
    justifyContent: 'space-between',
    userSelect: 'none',
    zIndex: 10,
  },
  brandContainer: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    padding: 'var(--space-4) var(--space-4)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  logoBadge: {
    width: 32,
    height: 32,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-default)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  brandText: {
    display: 'flex',
    flexDirection: 'column',
  },
  brandTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 700,
    letterSpacing: '0.08em',
    color: 'var(--text-primary)',
    lineHeight: 1.1,
  },
  brandSubtitle: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    letterSpacing: '-0.01em',
  },
  navSection: {
    flex: 1,
    padding: 'var(--space-4) var(--space-2)',
    overflowY: 'auto',
  },
  navGroupLabel: {
    fontSize: '10.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.08em',
    padding: '0 var(--space-3) var(--space-2) var(--space-3)',
  },
  navList: {
    listStyle: 'none',
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  navItem: {
    position: 'relative',
  },
  navButton: {
    width: '100%',
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    padding: '8px var(--space-3)',
    background: 'transparent',
    border: 'none',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    transition: 'background var(--transition-fast), color var(--transition-fast)',
    textAlign: 'left',
    position: 'relative',
  },
  navButtonActive: {
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
  },
  activeIndicator: {
    position: 'absolute',
    left: -8,
    top: 6,
    bottom: 6,
    width: 3,
    backgroundColor: 'var(--accent-primary)',
    borderRadius: '0 2px 2px 0',
  },
  iconWrapper: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
    transition: 'color var(--transition-fast)',
  },
  navLabel: {
    fontSize: 'var(--font-size-sm)',
    flex: 1,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    transition: 'color var(--transition-fast)',
  },
  shortcutBadge: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-xs)',
    backgroundColor: 'var(--bg-surface-hover)',
    border: '1px solid var(--border-subtle)',
    fontWeight: 600,
  },
  footerCard: {
    margin: 'var(--space-3)',
    padding: 'var(--space-3)',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
  },
  connectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: '4px',
  },
  connectionStatusRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  connectionStatusText: {
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  versionBadge: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontWeight: 600,
  },
  gatewayEndpoint: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    fontFamily: 'var(--font-mono)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
};
