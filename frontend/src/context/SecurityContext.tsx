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
  // --- System & OS Core ---
  {
    id: 'explorer',
    name: 'File Explorer',
    publisher: 'Microsoft Windows',
    processName: 'explorer.exe',
    category: 'System & OS',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Active in OS',
    installed: true,
  },
  {
    id: 'taskmgr',
    name: 'Task Manager',
    publisher: 'Microsoft Windows',
    processName: 'Taskmgr.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ASK',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Utility',
    installed: true,
  },
  {
    id: 'terminal',
    name: 'Windows Terminal',
    publisher: 'Microsoft Corporation',
    processName: 'wt.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Active Runtime',
    installed: true,
  },
  {
    id: 'powershell',
    name: 'Windows PowerShell',
    publisher: 'Microsoft Windows',
    processName: 'powershell.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Core',
    installed: true,
  },
  {
    id: 'cmd',
    name: 'Command Prompt',
    publisher: 'Microsoft Windows',
    processName: 'cmd.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Core',
    installed: true,
  },
  {
    id: 'regedit',
    name: 'Registry Editor',
    publisher: 'Microsoft Windows',
    processName: 'regedit.exe',
    category: 'System & OS',
    accessLevel: 'DENY',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'DENY',
      mouseInteraction: 'DENY',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Protected System Tool',
    installed: true,
  },
  {
    id: 'control',
    name: 'Control Panel',
    publisher: 'Microsoft Windows',
    processName: 'control.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ASK',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Utility',
    installed: true,
  },
  {
    id: 'services',
    name: 'Services Manager',
    publisher: 'Microsoft Windows',
    processName: 'mmc.exe',
    category: 'System & OS',
    accessLevel: 'DENY',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'DENY',
      mouseInteraction: 'DENY',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Protected MMC Snap-in',
    installed: true,
  },
  {
    id: 'devmgmt',
    name: 'Device Manager',
    publisher: 'Microsoft Windows',
    processName: 'mmc.exe',
    category: 'System & OS',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ASK',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Utility',
    installed: true,
  },
  // --- Utilities ---
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
    lastAccessed: 'System Utility',
    installed: true,
  },
  {
    id: 'paint',
    name: 'Paint',
    publisher: 'Microsoft Windows',
    processName: 'mspaint.exe',
    category: 'Utilities',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Utility',
    installed: true,
  },
  {
    id: 'calculator',
    name: 'Windows Calculator',
    publisher: 'Microsoft Windows',
    processName: 'CalculatorApp.exe',
    category: 'Utilities',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'System Utility',
    installed: true,
  },
  {
    id: 'snippingtool',
    name: 'Snipping Tool',
    publisher: 'Microsoft Windows',
    processName: 'SnippingTool.exe',
    category: 'Utilities',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Screen Utility',
    installed: true,
  },
  // --- Web Browsers ---
  {
    id: 'edge',
    name: 'Microsoft Edge',
    publisher: 'Microsoft Corporation',
    processName: 'msedge.exe',
    category: 'Browsers',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Active Browser',
    installed: true,
  },
  {
    id: 'chrome',
    name: 'Google Chrome',
    publisher: 'Google LLC',
    processName: 'chrome.exe',
    category: 'Browsers',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Browser',
    installed: true,
  },
  {
    id: 'brave',
    name: 'Brave Browser',
    publisher: 'Brave Software Inc.',
    processName: 'brave.exe',
    category: 'Browsers',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Browser',
    installed: true,
  },
  {
    id: 'firefox',
    name: 'Mozilla Firefox',
    publisher: 'Mozilla Corporation',
    processName: 'firefox.exe',
    category: 'Browsers',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Browser',
    installed: true,
  },
  // --- Development & Engineering ---
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
    lastAccessed: 'Active Workspace',
    installed: true,
  },
  {
    id: 'git',
    name: 'Git for Windows',
    publisher: 'Git Development Community',
    processName: 'git.exe',
    category: 'Development',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed CLI',
    installed: true,
  },
  {
    id: 'docker',
    name: 'Docker Desktop',
    publisher: 'Docker Inc.',
    processName: 'Docker Desktop.exe',
    category: 'Development',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ASK',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Virtualization Engine',
    installed: true,
  },
  {
    id: 'android_studio',
    name: 'Android Studio',
    publisher: 'Google LLC',
    processName: 'studio64.exe',
    category: 'Development',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'IDE Suite',
    installed: true,
  },
  // --- AI & Inference ---
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
    id: 'orbit_gateway',
    name: 'ORBIT Python Gateway',
    publisher: 'ORBIT Core Engine',
    processName: 'python.exe',
    category: 'AI & Inference',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Active Backend',
    installed: true,
  },
  // --- Communication & Collaboration ---
  {
    id: 'slack',
    name: 'Slack',
    publisher: 'Slack Technologies',
    processName: 'slack.exe',
    category: 'Communication',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed App',
    installed: true,
  },
  {
    id: 'discord',
    name: 'Discord',
    publisher: 'Discord Inc.',
    processName: 'Discord.exe',
    category: 'Communication',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed App',
    installed: true,
  },
  {
    id: 'teams',
    name: 'Microsoft Teams',
    publisher: 'Microsoft Corporation',
    processName: 'ms-teams.exe',
    category: 'Communication',
    accessLevel: 'ASK',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ASK',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed App',
    installed: true,
  },
  // --- Productivity ---
  {
    id: 'word',
    name: 'Microsoft Word',
    publisher: 'Microsoft Corporation',
    processName: 'WINWORD.EXE',
    category: 'Productivity',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Software',
    installed: true,
  },
  {
    id: 'excel',
    name: 'Microsoft Excel',
    publisher: 'Microsoft Corporation',
    processName: 'EXCEL.EXE',
    category: 'Productivity',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Software',
    installed: true,
  },
  // --- Media & Design ---
  {
    id: 'blender',
    name: 'Blender 3D Suite',
    publisher: 'Blender Foundation',
    processName: 'blender.exe',
    category: 'Media & Design',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed Suite',
    installed: true,
  },
  {
    id: 'spotify',
    name: 'Spotify Music',
    publisher: 'Spotify AB',
    processName: 'Spotify.exe',
    category: 'Media & Design',
    accessLevel: 'ALLOW',
    permissions: {
      windowFocus: 'ALLOW',
      keyboardInput: 'ALLOW',
      mouseInteraction: 'ALLOW',
      textReading: 'ALLOW',
      screenObservation: 'ALLOW',
    },
    lastAccessed: 'Installed App',
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

  // Load real installed applications and running Windows processes from Electron
  useEffect(() => {
    const fetchRealApps = async () => {
      if (typeof window !== 'undefined' && window.orbitDesktop?.getInstalledApps) {
        try {
          const apps = await window.orbitDesktop.getInstalledApps();
          if (apps && Array.isArray(apps) && apps.length > 0) {
            setAppPolicies((prev) => {
              const merged = [...prev];
              apps.forEach((app) => {
                const existingIndex = merged.findIndex(
                  (m) => m.id === app.id || m.processName.toLowerCase() === (app.processName || '').toLowerCase()
                );
                if (existingIndex >= 0) {
                  // Update existing item status
                  merged[existingIndex] = {
                    ...merged[existingIndex],
                    name: app.name || merged[existingIndex].name,
                    publisher: app.publisher || merged[existingIndex].publisher,
                    category: app.category || merged[existingIndex].category,
                    iconDataUrl: app.iconDataUrl || merged[existingIndex].iconDataUrl,
                    iconType: app.iconType || merged[existingIndex].iconType,
                    lastAccessed: app.isRunning ? 'Active Process' : merged[existingIndex].lastAccessed,
                    installed: true,
                  };
                } else {
                  // Add discovered software
                  merged.push({
                    id: app.id,
                    name: app.name,
                    publisher: app.publisher || 'Installed Software',
                    processName: app.processName,
                    category: app.category || 'Utilities',
                    iconDataUrl: app.iconDataUrl,
                    iconType: app.iconType,
                    accessLevel: app.category === 'System & OS' || app.category === 'Browsers' || app.category === 'Development' ? 'ALLOW' : 'ASK',
                    permissions: {
                      windowFocus: 'ALLOW',
                      keyboardInput: 'ASK',
                      mouseInteraction: 'ALLOW',
                      textReading: 'ALLOW',
                      screenObservation: 'ALLOW',
                    },
                    lastAccessed: app.isRunning ? 'Active Process' : 'Discovered Software',
                    installed: true,
                  });
                }
              });
              return merged;
            });
          }
        } catch (err) {
          console.warn('[SecurityContext] App discovery notice:', err);
        }
      }
    };

    fetchRealApps();
    const interval = setInterval(fetchRealApps, 6000);
    return () => clearInterval(interval);
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
