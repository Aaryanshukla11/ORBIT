import React, { createContext, useContext, useMemo, ReactNode } from 'react';
import { useOrbit } from './OrbitContext';
import { useModelManager } from './ModelManagerContext';
import { useSecurity } from './SecurityContext';
import { useTaskConsole } from './TaskConsoleContext';
import { useActivityHistory } from './ActivityHistoryContext';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';
import {
  ConnectionStatusItem,
  SafetyStatusItem,
  AttentionItem,
  SystemOperationalState,
  SystemOverviewState,
} from '../types/systemOverview';
import { ExecutionRecord } from '../types/activity';

interface SystemOverviewContextValue {
  overview: SystemOverviewState;
  recentActivities: ExecutionRecord[];
  stopCurrentTask: () => Promise<void>;
}

const SystemOverviewContext = createContext<SystemOverviewContextValue | undefined>(undefined);

export const SystemOverviewProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const { activeModel } = useModelManager();
  const { safetyState } = useSecurity();
  const { activeTask } = useTaskConsole();
  const { records, activeExecution } = useActivityHistory();

  const isConnected = connectionState === 'CONNECTED';
  const takeoverActive = safetyState.activeTakeoverPreempting || safetyState.guardStatus === 'ACTIVE';

  // Compute truthful operational state
  const operationalState = useMemo<SystemOperationalState>(() => {
    if (!isConnected) return 'DISCONNECTED';
    if (takeoverActive) return 'HUMAN_TAKEOVER';

    const running = activeExecution || (activeTask && activeTask.status === 'RUNNING' ? activeTask : null);
    if (running) {
      if (activeExecution?.status === 'REPLANNING') return 'REPLANNING';
      if (activeTask?.status === 'VALIDATING') return 'PLANNING';
      return 'EXECUTING';
    }

    return 'IDLE';
  }, [isConnected, takeoverActive, activeExecution, activeTask]);

  const stateLabel = useMemo(() => {
    switch (operationalState) {
      case 'DISCONNECTED':
        return 'Backend Disconnected';
      case 'HUMAN_TAKEOVER':
        return 'Human Takeover Active';
      case 'ERROR':
        return 'System Error';
      case 'REPLANNING':
        return 'Dynamic Replanning';
      case 'PLANNING':
        return 'Planning Task';
      case 'EXECUTING':
        return 'Executing Task';
      case 'PAUSED':
        return 'Execution Paused';
      case 'AWAITING_APPROVAL':
        return 'Awaiting Approval';
      case 'IDLE':
      default:
        return 'ORBIT Online';
    }
  }, [operationalState]);

  // Compute active task details
  const activeTaskPrompt = activeExecution?.goal || (activeTask?.status === 'RUNNING' ? activeTask.prompt : null);
  const activeTaskStatus = activeExecution?.status || (activeTask?.status === 'RUNNING' ? 'RUNNING' : null);

  const activeTaskProgress = useMemo(() => {
    if (activeExecution && activeExecution.total_steps > 0) {
      const activeStepObj = activeExecution.steps.find((s) => s.status === 'ACTIVE');
      return {
        current: Math.max(1, activeExecution.steps_completed + 1),
        total: activeExecution.total_steps,
        stepName: activeStepObj ? activeStepObj.name : `Step ${activeExecution.steps_completed + 1}`,
      };
    }
    return null;
  }, [activeExecution]);

  // Compute connections status
  const connections: ConnectionStatusItem[] = useMemo(() => {
    const wsStatus =
      connectionState === 'CONNECTED'
        ? 'CONNECTED'
        : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
        ? 'RECONNECTING'
        : 'DISCONNECTED';

    const aiStatus = !isConnected ? 'UNAVAILABLE' : activeModel ? 'READY' : 'UNAVAILABLE';

    const execStatus = !isConnected
      ? 'UNAVAILABLE'
      : operationalState === 'EXECUTING' || operationalState === 'REPLANNING'
      ? 'BUSY'
      : 'READY';

    return [
      {
        id: 'conn_gw',
        name: 'Backend Gateway',
        status: isConnected ? 'CONNECTED' : 'DISCONNECTED',
        label: isConnected ? 'Port 8765' : 'Offline',
        origin: 'LIVE',
      },
      {
        id: 'conn_ws',
        name: 'WebSocket Stream',
        status: wsStatus,
        label: wsStatus === 'CONNECTED' ? 'Synchronized' : wsStatus === 'RECONNECTING' ? 'Reconnecting' : 'Disconnected',
        origin: 'LIVE',
      },
      {
        id: 'conn_ai',
        name: 'AI Runtime Engine',
        status: aiStatus,
        label: activeModel ? `${activeModel.name}` : 'No Model',
        origin: 'LIVE',
      },
      {
        id: 'conn_exec',
        name: 'Execution Engine',
        status: execStatus,
        label: execStatus === 'BUSY' ? 'Executing Step' : execStatus === 'READY' ? 'Idle & Ready' : 'Unavailable',
        origin: 'LIVE',
      },
    ];
  }, [connectionState, isConnected, activeModel, operationalState]);

  // Compute safety statuses
  const safetyStatuses: SafetyStatusItem[] = useMemo(() => {
    return [
      {
        id: 'safe_takeover',
        name: 'Human Takeover Guard',
        status: takeoverActive ? 'ACTIVE' : 'READY',
        label: takeoverActive ? 'Operator Intervening' : 'Passive Monitoring',
        detail: 'Instant keyboard/mouse takeover intercept',
        origin: 'LIVE',
      },
      {
        id: 'safe_exec',
        name: 'Autonomous Execution',
        status: isConnected ? 'AVAILABLE' : 'UNAVAILABLE',
        label: isConnected ? 'Active Policy' : 'Unavailable',
        detail: 'Bounded workspace coordinate geometry',
        origin: 'LIVE',
      },
      {
        id: 'safe_policy',
        name: 'Safety Policy Gate',
        status: 'READY',
        label: 'Tier 1/2/3 Enforced',
        detail: 'Granular application & action authorization',
        origin: 'LIVE',
      },
      {
        id: 'safe_estop',
        name: 'Emergency Stop',
        status: safetyState.emergencyStopAvailable ? 'AVAILABLE' : 'UNAVAILABLE',
        label: 'Hardware & OS Release',
        detail: 'Safe key-up and cursor release protocol',
        origin: 'LIVE',
      },
    ];
  }, [takeoverActive, isConnected, safetyState]);

  // Compute attention required items (ONLY if genuine problems exist)
  const attentionItems: AttentionItem[] = useMemo(() => {
    const items: AttentionItem[] = [];

    if (!isConnected) {
      items.push({
        id: 'att_disconnected',
        severity: 'ERROR',
        title: 'Backend Gateway Disconnected',
        description: 'ORBIT cannot reach the Python runtime on port 8765. Ensure backend is running.',
        actionLabel: 'Check Connection',
        actionTab: 'system',
        origin: 'LIVE',
      });
    }

    if (takeoverActive) {
      items.push({
        id: 'att_takeover',
        severity: 'INFO',
        title: 'Human Takeover Active',
        description: 'Operator has taken manual control. Agent actions are preempted.',
        actionLabel: 'View Safety Controls',
        actionTab: 'security',
        origin: 'LIVE',
      });
    }

    // Check for recent failed execution in last 10 minutes
    const recentFailure = records.find(
      (r) =>
        r.status === 'FAILED' &&
        r.completed_at &&
        Date.now() - new Date(r.completed_at).getTime() < 10 * 60 * 1000
    );

    if (recentFailure) {
      items.push({
        id: `att_fail_${recentFailure.execution_id}`,
        severity: 'WARNING',
        title: 'Recent Task Failed',
        description: recentFailure.failure_reason || `Task '${recentFailure.goal.slice(0, 40)}...' failed to complete.`,
        actionLabel: 'View Diagnostics',
        actionTab: 'activity',
        origin: 'PERSISTED',
      });
    }

    return items;
  }, [isConnected, takeoverActive, records]);

  // Stop active task action
  const stopCurrentTask = async () => {
    const tid = activeExecution?.task_id || activeTask?.task_id;
    if (tid) {
      orbitWS.sendCommand('CANCEL_TASK', { task_id: tid, reason: 'Operator clicked Stop Task from System Overview' });
    }
  };

  const overview: SystemOverviewState = {
    operationalState,
    stateLabel,
    isBackendConnected: isConnected,
    activeTaskPrompt,
    activeTaskStatus,
    activeTaskProgress,
    activeModelName: activeModel ? activeModel.name : null,
    activeModelProvider: activeModel ? activeModel.provider : 'Local Ollama',
    activeModelIsLocal: activeModel ? activeModel.type === 'local' : true,
    activeModelHealth: activeModel?.status === 'ACTIVE' ? 'HEALTHY' : activeModel?.status || 'READY',
    activeModelLatencyMs: null,
    isHumanTakeoverActive: takeoverActive,
    connections,
    safetyStatuses,
    attentionItems,
  };

  // Recent 4 genuine historical records
  const recentActivities = records.slice(0, 4);

  return (
    <SystemOverviewContext.Provider value={{ overview, recentActivities, stopCurrentTask }}>
      {children}
    </SystemOverviewContext.Provider>
  );
};

export const useSystemOverview = (): SystemOverviewContextValue => {
  const context = useContext(SystemOverviewContext);
  if (!context) {
    throw new Error('useSystemOverview must be used within a SystemOverviewProvider');
  }
  return context;
};
