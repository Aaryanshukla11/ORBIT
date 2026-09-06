import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { DisplayItem, SystemInfo, WorkspaceContext, CapabilityItem, ObservedWindowItem, SystemHealthSummary } from '../types/system';
import { useOrbit } from './OrbitContext';
import { EventEnvelope } from '../types';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';

interface SystemContextType {
  displays: DisplayItem[];
  systemInfo: SystemInfo | null;
  workspaceContext: WorkspaceContext;
  capabilities: CapabilityItem[];
  observedWindows: ObservedWindowItem[];
  healthSummary: SystemHealthSummary;
  selectedDisplayId: number | null;
  setSelectedDisplayId: (id: number | null) => void;
  refreshSystemState: () => Promise<void>;
  isLoading: boolean;
}

const DEFAULT_DISPLAYS: DisplayItem[] = [
  {
    id: 1,
    index: 1,
    name: 'Display 1 (Primary)',
    isPrimary: true,
    bounds: { x: 0, y: 0, width: 1920, height: 1080 },
    workArea: { x: 0, y: 0, width: 1920, height: 1040 },
    scaleFactor: 1.0,
    scalePercent: 100,
    resolution: '1920 × 1080',
    touchSupport: false,
  },
];

const DEFAULT_WORKSPACE: WorkspaceContext = {
  activeDisplay: 'Display 1',
  focusedWindow: 'Visual Studio Code',
  focusedProcess: 'Code.exe',
  focusedHwnd: '0x00240E9A',
  dockEdge: 'RIGHT',
  dockWidthPx: 420,
  usableCanvas: '1500 × 1040 px (75% Screen)',
  observationPipeline: 'Available',
  visionResolution: '1920 × 1080',
};

const DEFAULT_CAPABILITIES: CapabilityItem[] = [
  {
    id: 'cap_obs',
    name: 'Display Observation',
    status: 'AVAILABLE',
    badge: 'Hardware DirectX/GDI',
    description: 'Real-time multi-monitor desktop capture & OCR vision grounding.',
  },
  {
    id: 'cap_win',
    name: 'Window Detection & Tracking',
    status: 'AVAILABLE',
    badge: 'Win32 HWND Events',
    description: 'Foreground focus tracking, window geometry & hierarchy enumeration.',
  },
  {
    id: 'cap_auto',
    name: 'UI Automation Engine',
    status: 'AVAILABLE',
    badge: 'Native UIAutomation',
    description: 'Accessible element inspection, control pattern invocation.',
  },
  {
    id: 'cap_mouse',
    name: 'Mouse Pointer Dispatch',
    status: 'ALLOWED',
    badge: 'Coordinate Safety Clamped',
    description: 'High-precision cursor movement, clicks & drag transactions.',
  },
  {
    id: 'cap_key',
    name: 'Keyboard Input Synthesis',
    status: 'ALLOWED',
    badge: 'Unicode & Shortcuts',
    description: 'Direct keystroke synthesis & system shortcut execution.',
  },
  {
    id: 'cap_sec',
    name: 'Filesystem Access Safety',
    status: 'GUARDED',
    badge: 'Tier 3 Safety Gate',
    description: 'Protected workspace paths guarded by runtime security policies.',
  },
];

const SystemContext = createContext<SystemContextType | undefined>(undefined);

export const SystemProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const [displays, setDisplays] = useState<DisplayItem[]>(DEFAULT_DISPLAYS);
  const [systemInfo, setSystemInfo] = useState<SystemInfo | null>(null);
  const [workspaceContext, setWorkspaceContext] = useState<WorkspaceContext>(DEFAULT_WORKSPACE);
  const [capabilities, setCapabilities] = useState<CapabilityItem[]>(DEFAULT_CAPABILITIES);
  const [observedWindows, setObservedWindows] = useState<ObservedWindowItem[]>([]);
  const [selectedDisplayId, setSelectedDisplayId] = useState<number | null>(1);
  const [isLoading, setIsLoading] = useState<boolean>(false);

  const fetchSystemData = useCallback(async () => {
    setIsLoading(true);
    try {
      // 1. Query Electron Desktop IPC
      if (typeof window !== 'undefined' && window.orbitDesktop) {
        if (window.orbitDesktop.getSystemDisplays) {
          const realDisplays = await window.orbitDesktop.getSystemDisplays();
          if (realDisplays && realDisplays.length > 0) {
            setDisplays(realDisplays);
            setSelectedDisplayId(realDisplays[0].id);
          }
        }

        if (window.orbitDesktop.getSystemInfo) {
          const realSysInfo = await window.orbitDesktop.getSystemInfo();
          if (realSysInfo) {
            setSystemInfo(realSysInfo);
          }
        }

        if (window.orbitDesktop.getInstalledApps) {
          const realApps = await window.orbitDesktop.getInstalledApps();
          if (realApps && Array.isArray(realApps)) {
            const running = realApps
              .filter((a: any) => a.isRunning)
              .map((a: any, idx: number) => ({
                hwnd: `0x${(idx + 1).toString(16).padStart(6, '0')}`,
                title: a.name,
                processName: a.processName || a.name,
                isForeground: idx === 0,
              }));
            if (running.length > 0) {
              setObservedWindows(running);
            }
          }
        }
      }
    } catch (err) {
      console.warn('[SystemContext] Failed to fetch hardware info via IPC:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSystemData();

    // Listen for display changes (monitors plugged/unplugged or scaled)
    if (typeof window !== 'undefined' && window.orbitDesktop?.onDisplayChanged) {
      const unsub = window.orbitDesktop.onDisplayChanged(() => {
        fetchSystemData();
      });
      return () => {
        if (typeof unsub === 'function') unsub();
      };
    }
  }, [fetchSystemData]);

  // Sync with Gateway Events
  useEffect(() => {
    const unsubEvents = orbitWS.onAnyEvent((event: EventEnvelope) => {
      const { event_type, payload } = event;

      if (event_type === 'WORKSPACE_GEOMETRY') {
        if (payload?.physical_display) {
          const w = payload.physical_display.width;
          const h = payload.physical_display.height;
          const dockW = payload.reservation_width_px || 420;
          const usableW = w - dockW;

          setWorkspaceContext((prev) => ({
            ...prev,
            usableCanvas: `${usableW} × ${h} px (~75% Screen)`,
            dockWidthPx: dockW,
            visionResolution: `${w} × ${h}`,
          }));
        }
      }

      if (event_type === 'WINDOW_FOCUS_CHANGED') {
        if (payload?.title) {
          setWorkspaceContext((prev) => ({
            ...prev,
            focusedWindow: payload.title,
            focusedProcess: payload.process_name || prev.focusedProcess,
            focusedHwnd: payload.hwnd || prev.focusedHwnd,
          }));

          setObservedWindows((prev) => {
            const exists = prev.some((w) => w.title === payload.title);
            if (exists) {
              return prev.map((w) => ({
                ...w,
                isForeground: w.title === payload.title,
              }));
            }
            return [
              {
                hwnd: payload.hwnd || '0x000000',
                title: payload.title,
                processName: payload.process_name || 'App.exe',
                isForeground: true,
              },
              ...prev.map((w) => ({ ...w, isForeground: false })),
            ];
          });
        }
      }
    });

    return () => {
      unsubEvents();
    };
  }, []);

  const healthSummary: SystemHealthSummary = {
    systemConnection: connectionState === 'CONNECTED' ? 'Connected' : 'Disconnected',
    desktopObservation: 'Ready',
    automationLayer: 'Ready',
    displayAccess: displays.length > 0 ? 'Available' : 'Restricted',
  };

  return (
    <SystemContext.Provider
      value={{
        displays,
        systemInfo,
        workspaceContext,
        capabilities,
        observedWindows,
        healthSummary,
        selectedDisplayId,
        setSelectedDisplayId,
        refreshSystemState: fetchSystemData,
        isLoading,
      }}
    >
      {children}
    </SystemContext.Provider>
  );
};

export const useSystem = (): SystemContextType => {
  const context = useContext(SystemContext);
  if (!context) {
    throw new Error('useSystem must be used within a SystemProvider');
  }
  return context;
};
