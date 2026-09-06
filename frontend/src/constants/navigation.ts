import { NavigationItem } from '../types';

export const NAVIGATION_ITEMS: NavigationItem[] = [
  {
    id: 'home',
    label: 'Command Center',
    shortcut: 'Ctrl+1',
    iconName: 'HomeIcon',
    description: 'Executive overview, agent readiness, and central control',
  },
  {
    id: 'chat',
    label: 'Chat / Task Console',
    shortcut: 'Ctrl+2',
    iconName: 'ChatIcon',
    description: 'Natural language task instructions, live plan timeline, and execution',
  },
  {
    id: 'activity',
    label: 'Activity Monitor',
    shortcut: 'Ctrl+3',
    iconName: 'ActivityIcon',
    description: 'Real-time telemetry event stream, action stage metrics, and telemetry',
  },
  {
    id: 'models',
    label: 'Model Manager',
    shortcut: 'Ctrl+4',
    iconName: 'ModelsIcon',
    description: 'Multi-provider LLM inventory, switching runtime, and benchmark telemetry',
  },
  {
    id: 'system',
    label: 'System & Displays',
    shortcut: 'Ctrl+5',
    iconName: 'SystemIcon',
    description: 'Win32 topology, mouse/keyboard hook watchdog, and memory diagnostics',
  },
  {
    id: 'security',
    label: 'Security & Safety',
    shortcut: 'Ctrl+6',
    iconName: 'SecurityIcon',
    description: 'Zero-trust authorization guardrails, takeover policies, and whitelist access',
  },
  {
    id: 'history',
    label: 'Execution History',
    shortcut: 'Ctrl+7',
    iconName: 'HistoryIcon',
    description: 'Historical plan runs, verification logs, and session audit trails',
  },
  {
    id: 'settings',
    label: 'Settings',
    shortcut: 'Ctrl+8',
    iconName: 'SettingsIcon',
    description: 'Gateway WebSocket endpoints, timeouts, and application preferences',
  },
];
