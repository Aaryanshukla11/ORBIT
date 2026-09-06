import React from 'react';
import {
  HomeIcon,
  ChatTabIcon,
  ModelsIcon,
  PulseHeartIcon,
  SystemIcon,
  SecurityIcon,
  TasksTabIcon,
  ActivityTabIcon,
  AppsTabIcon,
  SettingsTabIcon,
} from '../icons/Icons';

export type TabId = 'overview' | 'chat' | 'models' | 'health' | 'system' | 'security' | 'tasks' | 'activity' | 'apps' | 'settings';

interface HorizontalNavProps {
  activeTab: TabId;
  onSelectTab: (tab: TabId) => void;
}

interface NavItem {
  id: TabId;
  label: string;
  icon: React.FC<any>;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'overview', label: 'Overview', icon: HomeIcon },
  { id: 'chat', label: 'Chat', icon: ChatTabIcon },
  { id: 'models', label: 'Models', icon: ModelsIcon },
  { id: 'health', label: 'Health', icon: PulseHeartIcon },
  { id: 'system', label: 'System', icon: SystemIcon },
  { id: 'security', label: 'Security', icon: SecurityIcon },
  { id: 'activity', label: 'Activity', icon: ActivityTabIcon },
  { id: 'apps', label: 'Apps', icon: AppsTabIcon },
  { id: 'settings', label: 'Settings', icon: SettingsTabIcon },
];

export const HorizontalNav: React.FC<HorizontalNavProps> = ({ activeTab, onSelectTab }) => {
  return (
    <nav style={styles.navContainer}>
      {NAV_ITEMS.map((item) => {
        const Icon = item.icon;
        const isActive = activeTab === item.id;

        return (
          <button
            key={item.id}
            style={{
              ...styles.tabBtn,
              backgroundColor: isActive ? 'var(--bg-tab-active)' : 'transparent',
              color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
            }}
            onClick={() => onSelectTab(item.id)}
            title={`View ${item.label}`}
          >
            <Icon size={16} color={isActive ? 'var(--accent-primary)' : 'var(--text-secondary)'} />
            <span
              style={{
                ...styles.tabLabel,
                fontWeight: isActive ? 700 : 500,
                color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
              }}
            >
              {item.label}
            </span>

            {/* Subtle active indicator */}
            {isActive && <div style={styles.activeBar} />}
          </button>
        );
      })}
    </nav>
  );
};

const styles: Record<string, React.CSSProperties> = {
  navContainer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 8px 8px 8px',
    gap: '1px',
    userSelect: 'none',
  },
  tabBtn: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '2px',
    padding: '5px 1px 4px 1px',
    borderRadius: 'var(--radius-md)',
    border: 'none',
    cursor: 'pointer',
    position: 'relative',
    transition: 'all var(--transition-fast)',
  },
  tabLabel: {
    fontSize: '9.5px',
    letterSpacing: '-0.01em',
    lineHeight: 1.1,
  },
  activeBar: {
    position: 'absolute',
    bottom: 0,
    left: '10%',
    right: '10%',
    height: 2.5,
    backgroundColor: 'var(--accent-primary)',
    borderRadius: '2px 2px 0 0',
  },
};
