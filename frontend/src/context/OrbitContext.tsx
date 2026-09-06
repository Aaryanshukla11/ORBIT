import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { 
  NavigationPage, 
  ConnectionState, 
  ActiveModelInfo, 
  SystemHealth, 
  TelemetryLog,
  EventEnvelope 
} from '../types';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';

interface OrbitContextType {
  activePage: NavigationPage;
  setActivePage: (page: NavigationPage) => void;
  connectionState: ConnectionState;
  gatewayUrl: string;
  setGatewayUrl: (url: string) => void;
  activeModel: ActiveModelInfo | null;
  systemHealth: SystemHealth;
  telemetryLogs: TelemetryLog[];
  connect: (customUrl?: string) => void;
  disconnect: () => void;
  submitTask: (prompt: string) => boolean;
  triggerTakeover: () => boolean;
  releaseTakeover: () => boolean;
  addTelemetryLog: (level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'ACTION', source: string, message: string, payload?: any) => void;
  clearTelemetryLogs: () => void;
}

const defaultSystemHealth: SystemHealth = {
  cpuUsagePercent: null,
  ramUsageMb: null,
  activeSessionId: null,
  serverVersion: null,
  watchdogActive: false,
  takeoverArmed: false,
};

const OrbitContext = createContext<OrbitContextType | undefined>(undefined);

export const OrbitProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [activePage, setActivePage] = useState<NavigationPage>('home');
  const [connectionState, setConnectionState] = useState<ConnectionState>('DISCONNECTED');
  const [gatewayUrl, setGatewayUrl] = useState<string>('ws://127.0.0.1:8765/ws');
  const [activeModel, setActiveModel] = useState<ActiveModelInfo | null>(null);
  const [systemHealth, setSystemHealth] = useState<SystemHealth>(defaultSystemHealth);
  const [telemetryLogs, setTelemetryLogs] = useState<TelemetryLog[]>([]);

  const addTelemetryLog = useCallback((
    level: 'INFO' | 'WARN' | 'ERROR' | 'DEBUG' | 'ACTION', 
    source: string, 
    message: string, 
    payload?: any
  ) => {
    const logItem: TelemetryLog = {
      id: 'log_' + Math.random().toString(36).substring(2, 9),
      timestamp: new Date().toTimeString().split(' ')[0],
      level,
      source,
      message,
      payload,
    };
    setTelemetryLogs(prev => [logItem, ...prev.slice(0, 199)]); // Keep last 200 logs
  }, []);

  const clearTelemetryLogs = useCallback(() => {
    setTelemetryLogs([]);
  }, []);

  // Sync state with Orbit WebSocket Client
  useEffect(() => {
    const unsubState = orbitWS.onStateChange((state, url, errorMsg) => {
      setConnectionState(state);
      if (state === 'CONNECTED') {
        addTelemetryLog('INFO', 'Gateway', `Connected to ORBIT backend at ${url}`);
        // Request active model and initial inventory
        orbitWS.sendCommand('MODEL_ACTIVE');
        orbitWS.sendCommand('HEARTBEAT');
      } else if (state === 'DISCONNECTED') {
        addTelemetryLog('WARN', 'Gateway', 'Disconnected from backend gateway');
        setActiveModel(null);
        setSystemHealth(defaultSystemHealth);
      } else if (state === 'ERROR') {
        addTelemetryLog('ERROR', 'Gateway', errorMsg || 'Connection error encountered');
      } else if (state === 'RECONNECTING') {
        addTelemetryLog('INFO', 'Gateway', 'Attempting backend reconnection...');
      }
    });

    const unsubEvents = orbitWS.onAnyEvent((event: EventEnvelope) => {
      addTelemetryLog('INFO', event.event_type, `Received event: ${event.event_type}`, event.payload);

      if (event.event_type === 'MODEL_ACTIVE_UPDATED' || event.event_type === 'MODEL_ACTIVE_REPORT') {
        if (event.payload?.model) {
          setActiveModel({
            provider: event.payload.model.provider || 'Anthropic',
            modelId: event.payload.model.model_id || 'claude-3-5-sonnet',
            family: event.payload.model.family || 'Claude',
            contextWindow: event.payload.model.context_window || 200000,
            status: 'ONLINE',
            latencyMs: event.payload.model.latency_ms,
          });
        }
      }

      if (event.event_type === 'SYSTEM_HEALTH' || event.event_type === 'HEARTBEAT_ACK') {
        setSystemHealth(prev => ({
          ...prev,
          serverVersion: event.payload?.server_version || prev.serverVersion,
          activeSessionId: event.session_id || prev.activeSessionId,
          watchdogActive: event.payload?.watchdog_active ?? prev.watchdogActive,
          takeoverArmed: event.payload?.takeover_armed ?? prev.takeoverArmed,
        }));
      }
    });

    // Auto-connect attempt on mount
    orbitWS.connect(gatewayUrl);

    return () => {
      unsubState();
      unsubEvents();
    };
  }, [gatewayUrl, addTelemetryLog]);

  // Global Keyboard Navigation (Ctrl+1 through Ctrl+8)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
        const pages: NavigationPage[] = ['home', 'chat', 'activity', 'models', 'system', 'security', 'history', 'settings'];
        const keyNum = parseInt(e.key, 10);
        if (keyNum >= 1 && keyNum <= pages.length) {
          e.preventDefault();
          setActivePage(pages[keyNum - 1]);
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const connect = (customUrl?: string) => {
    const targetUrl = customUrl || gatewayUrl;
    orbitWS.connect(targetUrl);
  };

  const disconnect = () => {
    orbitWS.disconnect();
  };

  const submitTask = (prompt: string): boolean => {
    addTelemetryLog('ACTION', 'UI', `Submitted task: "${prompt}"`);
    return orbitWS.sendCommand('SUBMIT_TASK', { prompt });
  };

  const triggerTakeover = (): boolean => {
    addTelemetryLog('WARN', 'UI', 'User triggered Emergency Human Takeover');
    return orbitWS.sendCommand('TRIGGER_TAKEOVER', { reason: 'User interface trigger' });
  };

  const releaseTakeover = (): boolean => {
    addTelemetryLog('INFO', 'UI', 'User released Human Takeover');
    return orbitWS.sendCommand('RELEASE_TAKEOVER');
  };

  return (
    <OrbitContext.Provider
      value={{
        activePage,
        setActivePage,
        connectionState,
        gatewayUrl,
        setGatewayUrl,
        activeModel,
        systemHealth,
        telemetryLogs,
        connect,
        disconnect,
        submitTask,
        triggerTakeover,
        releaseTakeover,
        addTelemetryLog,
        clearTelemetryLogs,
      }}
    >
      {children}
    </OrbitContext.Provider>
  );
};

export const useOrbit = (): OrbitContextType => {
  const context = useContext(OrbitContext);
  if (!context) {
    throw new Error('useOrbit must be used within an OrbitProvider');
  }
  return context;
};
