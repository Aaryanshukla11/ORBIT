/**
 * System & Displays Domain Types
 * Matching Electron Desktop API and ORBIT Workspace/Capability contracts
 */

export interface DisplayItem {
  id: number;
  index: number;
  name: string;
  isPrimary: boolean;
  bounds: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  workArea: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  scaleFactor: number;
  scalePercent: number;
  resolution: string;
  rotation?: number;
  touchSupport?: boolean;
}

export interface SystemInfo {
  platform: string;
  release: string;
  arch: string;
  cpuModel: string;
  cpuCores: number;
  totalMemory: string;
  freeMemory: string;
  electronVersion: string;
  chromeVersion: string;
  nodeVersion: string;
}

export interface WorkspaceContext {
  activeDisplay: string;
  focusedWindow: string;
  focusedProcess: string;
  focusedHwnd: string;
  dockEdge: 'RIGHT' | 'LEFT' | 'NONE';
  dockWidthPx: number;
  usableCanvas: string;
  observationPipeline: 'Available' | 'Active' | 'Degraded';
  visionResolution: string;
}

export interface CapabilityItem {
  id: string;
  name: string;
  status: 'AVAILABLE' | 'ALLOWED' | 'RESTRICTED' | 'GUARDED';
  badge: string;
  description: string;
}

export interface ObservedWindowItem {
  hwnd: string;
  title: string;
  processName: string;
  isForeground: boolean;
  bounds?: string;
}

export interface SystemHealthSummary {
  systemConnection: 'Connected' | 'Disconnected' | 'Connecting';
  desktopObservation: 'Ready' | 'Active' | 'Degraded';
  automationLayer: 'Ready' | 'Standby' | 'Locked';
  displayAccess: 'Available' | 'Restricted';
}
