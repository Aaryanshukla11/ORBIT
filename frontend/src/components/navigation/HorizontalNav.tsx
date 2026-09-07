import React from 'react';
import {
  ChatTabIcon,
  SystemIcon,
  SecurityIcon,
  TasksTabIcon,
  ActivityTabIcon,
  AppsTabIcon,
  SettingsTabIcon,
} from '../icons/Icons';

import { useTaskConsole } from '../../context/TaskConsoleContext';

export type TabId = 'chat' | 'system' | 'security' | 'tasks' | 'apps' | 'settings';

interface HorizontalNavProps {
  activeTab: TabId;
  onSelectTab: (tab: TabId) => void;
}

export const HorizontalNav: React.FC<HorizontalNavProps> = ({ activeTab, onSelectTab }) => {
  const { inputMode } = useTaskConsole();
  const chatLabel = inputMode === 'task' ? 'Assistant' : 'Chatbot';

  const navItems = [
    { id: 'chat' as TabId, label: chatLabel, icon: ChatTabIcon },
    { id: 'system' as TabId, label: 'System', icon: SystemIcon },
    { id: 'security' as TabId, label: 'Security', icon: SecurityIcon },
    { id: 'tasks' as TabId, label: 'Tasks & Activity', icon: TasksTabIcon },
    { id: 'apps' as TabId, label: 'Apps', icon: AppsTabIcon },
    { id: 'settings' as TabId, label: 'Settings', icon: SettingsTabIcon },
  ];

  return (
    <nav style={styles.navContainer}>
      {navItems.map((item) => {
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
