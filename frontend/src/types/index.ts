/**
 * Core Type Definitions for ORBIT Windows Desktop Application
 */

export type NavigationPage = 
  | 'home'
  | 'chat'
  | 'activity'
  | 'models'
  | 'system'
  | 'security'
  | 'history'
  | 'settings';

export type ConnectionState = 
  | 'DISCONNECTED'
  | 'CONNECTING'
  | 'CONNECTED'
  | 'RECONNECTING'
  | 'ERROR';

export type SystemStatusState = 
  | 'STANDBY'
  | 'READY'
  | 'PLANNING'
  | 'EXECUTING'
  | 'AWAITING_TAKEOVER'
  | 'LOCKED'
  | 'ERROR';

export interface ActiveModelInfo {
  provider: string;
  modelId: string;
  family: string;
  contextWindow: number;
  status: 'ONLINE' | 'STANDBY' | 'DEGRADED' | 'OFFLINE';
  temperature?: number;
  latencyMs?: number;
}

export interface SystemHealth {
  cpuUsagePercent: number | null;
  ramUsageMb: number | null;
  activeSessionId: string | null;
  serverVersion: string | null;
  watchdogActive: boolean;
  takeoverArmed: boolean;
}

export interface TelemetryLog {
  id: string;
  timestamp: string;
  level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'ACTION';
  source: string;
  message: string;
  payload?: Record<string, any>;
}

export interface NavigationItem {
  id: NavigationPage;
  label: string;
  shortcut: string;
  iconName: string;
  description: string;
  badge?: string;
}

export interface BaseCommand {
  command_id: string;
  command_type: string;
  session_id: string;
  timestamp: string;
  payload?: Record<string, any>;
}

export interface EventEnvelope {
  event_id: string;
  event_type: string;
  session_id: string;
  timestamp: string;
  correlation_id?: string;
  payload: Record<string, any>;
}

declare global {
  interface Window {
    orbitDesktop?: {
      platform: string;
      minimize: () => void;
      maximize: () => void;
      close: () => void;
      togglePin: () => Promise<boolean>;
      isPinned: () => Promise<boolean>;
      isMaximized: () => Promise<boolean>;
      getAppVersion: () => Promise<string>;
      getSystemDisplays?: () => Promise<any[]>;
      getSystemInfo?: () => Promise<any>;
      getInstalledApps?: () => Promise<any[]>;
      onDisplayChanged?: (callback: () => void) => () => void;
    };
  }
}

