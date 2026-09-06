/**
 * Domain contracts for ORBIT System Overview.
 * Every metric is strictly classified as LIVE, PERSISTED, UNAVAILABLE, or ESTIMATED.
 */

export type DataOrigin = 'LIVE' | 'PERSISTED' | 'UNAVAILABLE' | 'ESTIMATED';

export type SystemOperationalState =
  | 'IDLE'
  | 'PLANNING'
  | 'EXECUTING'
  | 'REPLANNING'
  | 'AWAITING_APPROVAL'
  | 'HUMAN_TAKEOVER'
  | 'PAUSED'
  | 'DISCONNECTED'
  | 'ERROR';

export interface ConnectionStatusItem {
  id: string;
  name: string;
  status: 'CONNECTED' | 'DISCONNECTED' | 'RECONNECTING' | 'READY' | 'BUSY' | 'UNAVAILABLE';
  label: string;
  origin: DataOrigin;
  latencyMs?: number | null;
}

export interface SafetyStatusItem {
  id: string;
  name: string;
  status: 'READY' | 'ACTIVE' | 'AVAILABLE' | 'LOCKED' | 'UNAVAILABLE';
  label: string;
  detail?: string;
  origin: DataOrigin;
}

export interface AttentionItem {
  id: string;
  severity: 'WARNING' | 'ERROR' | 'INFO';
  title: string;
  description: string;
  actionLabel?: string;
  actionTab?: string;
  origin: DataOrigin;
}

export interface SystemOverviewState {
  operationalState: SystemOperationalState;
  stateLabel: string;
  isBackendConnected: boolean;
  activeTaskPrompt?: string | null;
  activeTaskStatus?: string | null;
  activeTaskProgress?: { current: number; total: number; stepName?: string } | null;
  activeModelName?: string | null;
  activeModelProvider?: string | null;
  activeModelIsLocal: boolean;
  activeModelHealth?: string | null;
  activeModelLatencyMs?: number | null;
  isHumanTakeoverActive: boolean;
  connections: ConnectionStatusItem[];
  safetyStatuses: SafetyStatusItem[];
  attentionItems: AttentionItem[];
}
