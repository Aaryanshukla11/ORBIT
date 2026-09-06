import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import {
  PolicyLevel,
  SystemCapabilityPolicy,
  ApplicationPolicyItem,
  AppGranularPermissions,
  SecurityAuditEvent,
  HumanTakeoverSafetyState,
} from '../types/security';
import { EventEnvelope } from '../types';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';

interface SecurityContextType {
  capabilityPolicies: SystemCapabilityPolicy[];
  appPolicies: ApplicationPolicyItem[];
  auditEvents: SecurityAuditEvent[];
  safetyState: HumanTakeoverSafetyState;
  searchQuery: string;
  setSearchQuery: (query: string) => void;
  filterPolicy: 'ALL' | 'ALLOW' | 'ASK' | 'DENY';
  setFilterPolicy: (filter: 'ALL' | 'ALLOW' | 'ASK' | 'DENY') => void;
  updatingPolicyId: string | null;
  policyError: string | null;
  updateCapabilityPolicy: (id: string, level: PolicyLevel) => Promise<boolean>;
  updateAppPolicy: (appId: string, level: PolicyLevel) => Promise<boolean>;
  updateAppGranularPermission: (
    appId: string,
    permKey: keyof AppGranularPermissions,
    level: PolicyLevel
  ) => Promise<boolean>;
  triggerEmergencyStop: () => Promise<boolean>;
  clearPolicyError: () => void;
}

const DEFAULT_CAPABILITY_POLICIES: SystemCapabilityPolicy[] = [
  {
    id: 'cap_mouse',
    name: 'Mouse Control',
    description: 'Hardware cursor movement, clicks & drag actions.',
    level: 'ALLOW',
    category: 'input',
    isRealEnforced: true,
  },
  {
    id: 'cap_keyboard',
    name: 'Keyboard Control',
    description: 'Text typing, modifier keys & application shortcuts.',
    level: 'ALLOW',
    category: 'input',
    isRealEnforced: true,
  },
  {
    id: 'cap_apps',
    name: 'Application Access',
    description: 'Window focus, UI Automation element discovery & control.',
    level: 'ALLOW',
    category: 'system',
    isRealEnforced: true,
  },
  {
    id: 'cap_filesystem',
    name: 'Filesystem Access',
    description: 'Read/write access to project repositories and documents.',
    level: 'ASK',
    category: 'storage',
    isRealEnforced: true,
  },
  {
    id: 'cap_browser',
    name: 'Browser Access',
    description: 'DOM interaction, web navigation and visual grounding.',
    level: 'ALLOW',
    category: 'network',
    isRealEnforced: true,
  },
  {
    id: 'cap_terminal',
    name: 'Terminal Access',
    description: 'Command line execution in Windows Terminal / CMD.',
    level: 'ASK',
    category: 'system',
    isRealEnforced: true,
  },
  {
    id: 'cap_powershell',
    name: 'PowerShell Access',
    description: 'PowerShell script execution & system administration.',
    level: 'ASK',
    category: 'system',
    isRealEnforced: true,
  },
  {
    id: 'cap_window_mgr',
    name: 'Window Management',
    description: 'Window positioning, minimize/maximize & workspace layout.',
    level: 'ALLOW',
    category: 'system',
    isRealEnforced: true,
  },
  {
    id: 'cap_sys_access',
    name: 'Computer / System Access',
    description: 'Core Windows OS API calls and system registry queries.',
    level: 'ASK',
    category: 'system',
    isRealEnforced: true,
  },
];

const DEFAULT_APP_POLICIES: ApplicationPolicyItem[] = [
  {
    id: 'vscode',
    name: 'Visual Studio Code',
    publisher: 'Microsoft Corporation',
    processName: 'Code.exe',
    category: 'Development',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Just now',
    installed: true,
  },
  {
    id: 'edge',
    name: 'Microsoft Edge',
    publisher: 'Microsoft Corporation',
    processName: 'msedge.exe',
    category: 'Browser',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: '2 mins ago',
    installed: true,
  },
  {
    id: 'terminal',
    name: 'Windows Terminal',
    publisher: 'Microsoft Corporation',
    processName: 'wt.exe',
    category: 'System',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: '14 mins ago',
    installed: true,
  },
  {
    id: 'chrome',
    name: 'Google Chrome',
    publisher: 'Google LLC',
    processName: 'chrome.exe',
    category: 'Browser',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: '1 hour ago',
    installed: true,
  },
  {
    id: 'docker',
    name: 'Docker Desktop',
    publisher: 'Docker Inc.',
    processName: 'Docker Desktop.exe',
    category: 'Virtualization',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ASK',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Yesterday',
    installed: true,
  },
  {
    id: 'ollama',
    name: 'Ollama Local Runtime',
    publisher: 'Ollama Team',
    processName: 'ollama.exe',
    category: 'AI & Inference',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Active Runtime',
    installed: true,
  },
  {
    id: 'notepad',
    name: 'Notepad',
    publisher: 'Microsoft Windows',
    processName: 'notepad.exe',
    category: 'Utilities',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: '2 days ago',
    installed: true,
  },
];

const INITIAL_AUDIT_EVENTS: SecurityAuditEvent[] = [
  {
    id: 'aud_1',
    timestamp: '11:22:45 AM',
    action: 'Window Focus Permitted',
    target: 'Visual Studio Code (Code.exe)',
    result: 'ALLOWED',
    tier: 1,
    details: 'Autonomous Tier 1 focus event verified against policy.',
  },
  {
    id: 'aud_2',
    timestamp: '11:22:46 AM',
    action: 'Screen Observation Capture',
    target: 'Display 1 (1920x1080)',
    result: 'ALLOWED',
    tier: 1,
    details: 'DirectX desktop frame capture signed by security coordinator.',
  },
  {
    id: 'aud_3',
    timestamp: '11:22:48 AM',
    action: 'Tier 3 Safety Gate Check',
    target: 'Workspace Directory File Scan',
    result: 'AUTHORIZED',
    tier: 3,
    details: 'Filesystem access policy evaluated: Ask -> Authorized by operator.',
  },
  {
    id: 'aud_4',
    timestamp: '11:22:50 AM',
    action: 'Autonomous Pointer Movement',
    target: 'Cursor Bounds (X: 450, Y: 320)',
    result: 'ALLOWED',
    tier: 1,
    details: 'Pointer coordinate validated within usable canvas boundary.',
  },
];

const SecurityContext = createContext<SecurityContextType | undefined>(undefined);

export const SecurityProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [capabilityPolicies, setCapabilityPolicies] = useState<SystemCapabilityPolicy[]>(DEFAULT_CAPABILITY_POLICIES);
  const [appPolicies, setAppPolicies] = useState<ApplicationPolicyItem[]>(DEFAULT_APP_POLICIES);
  const [auditEvents, setAuditEvents] = useState<SecurityAuditEvent[]>(INITIAL_AUDIT_EVENTS);
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [filterPolicy, setFilterPolicy] = useState<'ALL' | 'ALLOW' | 'ASK' | 'DENY'>('ALL');
  const [updatingPolicyId, setUpdatingPolicyId] = useState<string | null>(null);
  const [policyError, setPolicyError] = useState<string | null>(null);

  const [safetyState, setSafetyState] = useState<HumanTakeoverSafetyState>({
    guardStatus: 'READY',
    emergencyStopAvailable: true,
    autonomousPolicy: 'SUPERVISED',
    watchdogArmed: true,
    activeTakeoverPreempting: false,
  });

  // Load real installed applications from Electron if available
  useEffect(() => {
    if (typeof window !== 'undefined' && window.orbitDesktop?.getInstalledApps) {
      window.orbitDesktop.getInstalledApps().then((apps) => {
        if (apps && Array.isArray(apps) && apps.length > 0) {
          setAppPolicies((prev) => {
            const merged = [...prev];
            apps.forEach((app) => {
              const existing = merged.find((m) => m.id === app.id || m.processName === app.processName);
              if (!existing) {
                merged.push({
                  id: app.id,
                  name: app.name,
                  publisher: app.publisher || 'Installed Software',
                  processName: app.processName,
                  category: app.category || 'Application',
                  accessLevel: 'ASK',
                  permissions: {
                    windowFocus: 'ALLOW',
                    keyboardInput: 'ASK',
                    mouseInteraction: 'ASK',
                    textReading: 'ALLOW',
                    screenObservation: 'ALLOW',
                  },
                  installed: true,
                });
              }
            });
            return merged;
          });
        }
      });
    }
  }, []);

  // Listen to Gateway Events
  useEffect(() => {
    const unsubEvents = orbitWS.onAnyEvent((event: EventEnvelope) => {
      const { event_type, payload } = event;

      if (event_type === 'TAKEOVER_EVENT') {
        const isActive = payload.is_active;
        setSafetyState((prev) => ({
          ...prev,
          activeTakeoverPreempting: isActive,
          guardStatus: isActive ? 'ACTIVE' : 'READY',
        }));

        setAuditEvents((prev) => [
          {
            id: 'aud_' + Date.now(),
            timestamp: new Date().toTimeString().split(' ')[0],
            action: isActive ? 'Human Takeover PREEMPTED' : 'Human Takeover Released',
            target: payload.source || 'Keyboard/Mouse Hook',
            result: isActive ? 'PREEMPTED' : 'ALLOWED',
            tier: 3,
            details: payload.reason || 'Operator input detected.',
          },
          ...prev,
        ]);
      }

      if (event_type === 'ACTION_AUTHORIZATION_REQUIRED') {
        setAuditEvents((prev) => [
          {
            id: 'aud_' + Date.now(),
            timestamp: new Date().toTimeString().split(' ')[0],
            action: `Authorization Required [${payload.action_type}]`,
            target: payload.task_id ? `Task ${payload.task_id.substring(0, 8)}` : 'System',
            result: 'BLOCKED',
            tier: payload.tier || 3,
            details: payload.description || 'Action paused pending operator approval.',
          },
          ...prev,
        ]);
      }
    });

    return () => {
      unsubEvents();
    };
  }, []);

  const updateCapabilityPolicy = useCallback(
    async (id: string, level: PolicyLevel): Promise<boolean> => {
      setUpdatingPolicyId(id);
      setPolicyError(null);

      // Send policy update command to backend
      orbitWS.sendCommand('UPDATE_SECURITY_POLICY', {
        policy_id: id,
        level: level,
      });

      // Update state
      setCapabilityPolicies((prev) =>
        prev.map((p) => (p.id === id ? { ...p, level } : p))
      );

      // Record audit entry
      setAuditEvents((prev) => [
        {
          id: 'aud_' + Date.now(),
          timestamp: new Date().toTimeString().split(' ')[0],
          action: 'Global Capability Policy Modified',
          target: id,
          result: level === 'DENY' ? 'DENIED' : 'ALLOWED',
          tier: 2,
          details: `Policy state changed to ${level}.`,
        },
        ...prev,
      ]);

      setUpdatingPolicyId(null);
      return true;
    },
    []
  );

  const updateAppPolicy = useCallback(
    async (appId: string, level: PolicyLevel): Promise<boolean> => {
      setUpdatingPolicyId(appId);
      setPolicyError(null);

      orbitWS.sendCommand('UPDATE_APP_POLICY', {
        app_id: appId,
        access_level: level,
      });

      setAppPolicies((prev) =>
        prev.map((app) =>
          app.id === appId
            ? {
                ...app,
                accessLevel: level,
                permissions: {
                  windowFocus: level === 'DENY' ? 'DENY' : app.permissions.windowFocus,
                  keyboardInput: level === 'DENY' ? 'DENY' : level === 'ALLOW' ? 'ALLOW' : 'ASK',
                  mouseInteraction: level === 'DENY' ? 'DENY' : level === 'ALLOW' ? 'ALLOW' : 'ASK',
                  textReading: level === 'DENY' ? 'DENY' : app.permissions.textReading,
                  screenObservation: level === 'DENY' ? 'DENY' : app.permissions.screenObservation,
                },
              }
            : app
        )
      );

      setAuditEvents((prev) => [
        {
          id: 'aud_' + Date.now(),
          timestamp: new Date().toTimeString().split(' ')[0],
          action: 'Application Policy Modified',
          target: appId,
          result: level === 'DENY' ? 'DENIED' : 'ALLOWED',
          tier: 2,
          details: `Application access permission updated to ${level}.`,
        },
        ...prev,
      ]);

      setUpdatingPolicyId(null);
      return true;
    },
    []
  );

  const updateAppGranularPermission = useCallback(
    async (
      appId: string,
      permKey: keyof AppGranularPermissions,
      level: PolicyLevel
    ): Promise<boolean> => {
      setUpdatingPolicyId(`${appId}_${permKey}`);

      orbitWS.sendCommand('UPDATE_APP_POLICY', {
        app_id: appId,
        permission_key: permKey,
        level: level,
      });

      setAppPolicies((prev) =>
        prev.map((app) =>
          app.id === appId
            ? {
                ...app,
                permissions: {
                  ...app.permissions,
                  [permKey]: level,
                },
              }
            : app
        )
      );

      setUpdatingPolicyId(null);
      return true;
    },
    []
  );

  const triggerEmergencyStop = useCallback(async (): Promise<boolean> => {
    orbitWS.sendCommand('CANCEL_TASK', {
      reason: 'EMERGENCY_STOP_TRIGGERED',
      hard_stop: true,
    });

    setSafetyState((prev) => ({
      ...prev,
      activeTakeoverPreempting: true,
    }));

    setAuditEvents((prev) => [
      {
        id: 'aud_' + Date.now(),
        timestamp: new Date().toTimeString().split(' ')[0],
        action: 'EMERGENCY STOP EXECUTED',
        target: 'Global Autonomous Dispatch Gate',
        result: 'PREEMPTED',
        tier: 3,
        details: 'All in-flight tasks and synthetic hardware inputs halted immediately.',
      },
      ...prev,
    ]);

    return true;
  }, []);

  const clearPolicyError = () => setPolicyError(null);

  return (
    <SecurityContext.Provider
      value={{
        capabilityPolicies,
        appPolicies,
        auditEvents,
        safetyState,
        searchQuery,
        setSearchQuery,
        filterPolicy,
        setFilterPolicy,
        updatingPolicyId,
        policyError,
        updateCapabilityPolicy,
        updateAppPolicy,
        updateAppGranularPermission,
        triggerEmergencyStop,
        clearPolicyError,
      }}
    >
      {children}
    </SecurityContext.Provider>
  );
};

export const useSecurity = (): SecurityContextType => {
  const context = useContext(SecurityContext);
  if (!context) {
    throw new Error('useSecurity must be used within a SecurityProvider');
  }
  return context;
};
