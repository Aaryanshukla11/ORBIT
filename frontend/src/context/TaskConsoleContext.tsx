import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { ChatMessage, InputMode, ActionAuthPayload } from '../types/chat';
import { Task, ExecutionPlan, Action, TaskStatus, ErrorDetail } from '../types/task';
import { EventEnvelope } from '../types';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';
import { useOrbit } from './OrbitContext';

interface TaskConsoleContextType {
  messages: ChatMessage[];
  activeTask: Task | null;
  activePlan: ExecutionPlan | null;
  inputMode: InputMode;
  setInputMode: (mode: InputMode) => void;
  sendUserMessage: (content: string, mode?: InputMode) => boolean;
  cancelActiveTask: (taskId?: string, reason?: string) => boolean;
  pauseActiveTask: (taskId?: string) => boolean;
  resumeActiveTask: (taskId?: string) => boolean;
  authorizeAction: (taskId: string, actionId: string, approved: boolean, reason?: string) => boolean;
  clearMessages: () => void;
  isProcessing: boolean;
}

const TaskConsoleContext = createContext<TaskConsoleContextType | undefined>(undefined);

export const TaskConsoleProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState, addTelemetryLog } = useOrbit();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [activeTask, setActiveTask] = useState<Task | null>(null);
  const [activePlan, setActivePlan] = useState<ExecutionPlan | null>(null);
  const [inputMode, setInputMode] = useState<InputMode>('task');
  const [isProcessing, setIsProcessing] = useState<boolean>(false);

  const getTimestamp = () => new Date().toTimeString().split(' ')[0];

  const addMessage = useCallback((msg: Omit<ChatMessage, 'id' | 'timestamp'>) => {
    const newMessage: ChatMessage = {
      ...msg,
      id: 'msg_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now().toString(36),
      timestamp: getTimestamp(),
    };
    setMessages((prev) => [...prev, newMessage]);
    return newMessage;
  }, []);

  // Sync with WebSocket Gateway Events
  useEffect(() => {
    const unsubEvents = orbitWS.onAnyEvent((event: EventEnvelope) => {
      const { event_type, payload, session_id } = event;

      // 1. TASK_STATE_CHANGED
      if (event_type === 'TASK_STATE_CHANGED') {
        const taskId = payload.task_id;
        const status = payload.status as TaskStatus;
        const prompt = payload.prompt || '';
        const error = payload.error as ErrorDetail | undefined;

        setActiveTask((prev) => {
          if (!prev || prev.task_id === taskId) {
            return {
              task_id: taskId,
              session_id: session_id || 'default',
              prompt: prompt || (prev?.prompt ?? ''),
              status: status,
              plan: prev?.plan,
              current_step_index: prev?.current_step_index ?? 0,
              created_at: prev?.created_at ?? new Date().toISOString(),
              error: error,
            };
          }
          return prev;
        });

        if (status === 'RUNNING' || status === 'VALIDATING' || status === 'READY') {
          setIsProcessing(true);
        } else if (status === 'COMPLETED' || status === 'FAILED' || status === 'CANCELLED') {
          setIsProcessing(false);
        }

        // Add task event message to stream
        addMessage({
          type: 'task_event',
          content: `Task ${taskId.substring(0, 8)} transitioned to state: ${status}`,
          taskId: taskId,
          taskStatus: status,
          errorDetail: error,
        });
      }

      // 2. PLAN_UPDATED
      if (event_type === 'PLAN_UPDATED') {
        const plan = payload.plan as ExecutionPlan;
        if (plan) {
          setActivePlan(plan);
          setActiveTask((prev) => prev ? { ...prev, plan: plan } : null);

          addMessage({
            type: 'assistant',
            content: `Plan formulated: ${plan.description} (${plan.steps.length} steps)`,
            taskId: payload.task_id,
            plan: plan,
          });
        }
      }

      // 3. ACTION_AUTHORIZATION_REQUIRED
      if (event_type === 'ACTION_AUTHORIZATION_REQUIRED') {
        const authData: ActionAuthPayload = {
          action_id: payload.action_id,
          task_id: payload.task_id,
          action_type: payload.action_type,
          tier: payload.tier,
          description: payload.description,
          parameters: payload.parameters || {},
        };

        addMessage({
          type: 'action_auth',
          content: `Safety Authorization Required: Tier 3 action [${payload.action_type}]`,
          actionAuth: authData,
          taskId: payload.task_id,
        });
      }

      // 4. TAKEOVER_EVENT
      if (event_type === 'TAKEOVER_EVENT') {
        const isActive = payload.is_active;
        const source = payload.source || 'human_input';
        const reason = payload.reason || 'Operator preemption';

        addMessage({
          type: 'system',
          content: isActive 
            ? `Emergency Takeover ACTIVATED (${source}): ${reason}. AI synthetic inputs locked.`
            : `Human Takeover RELEASED. Normal agent controls restored.`,
        });
      }

      // 5. ERROR
      if (event_type === 'ERROR') {
        addMessage({
          type: 'error',
          content: payload.message || 'An unexpected backend error occurred.',
          errorDetail: {
            code: payload.code || 'GATEWAY_ERROR',
            message: payload.message || 'Unknown error',
            recoverable: payload.recoverable ?? true,
            details: payload.details,
          },
        });
      }

      // 6. RUNTIME_STATUS
      if (event_type === 'RUNTIME_STATUS') {
        if (!payload.active_task_id && isProcessing) {
          setIsProcessing(false);
        }
      }
    });

    return () => {
      unsubEvents();
    };
  }, [addMessage, isProcessing]);

  // Command Senders
  const sendUserMessage = useCallback((content: string, mode?: InputMode): boolean => {
    if (!content.trim()) return false;
    const currentMode = mode || inputMode;

    // Record user message
    addMessage({
      type: 'user',
      content: content,
      metadata: { mode: currentMode },
    });

    if (currentMode === 'task') {
      setIsProcessing(true);
      const sent = orbitWS.sendCommand('SUBMIT_TASK', {
        prompt: content,
        context: {},
      });

      if (!sent) {
        setIsProcessing(false);
        addMessage({
          type: 'error',
          content: 'Failed to dispatch task: WebSocket is currently disconnected.',
        });
        return false;
      }
      return true;
    } else {
      // Conversational mode: dispatch task with conversational intent context
      const sent = orbitWS.sendCommand('SUBMIT_TASK', {
        prompt: content,
        context: { conversational: true },
      });
      return sent;
    }
  }, [inputMode, addMessage]);

  const cancelActiveTask = useCallback((taskId?: string, reason = 'User canceled from Console'): boolean => {
    const targetId = taskId || activeTask?.task_id;
    if (!targetId) return false;

    addMessage({
      type: 'system',
      content: `Requesting cancellation for Task ${targetId.substring(0, 8)}...`,
    });

    const sent = orbitWS.sendCommand('CANCEL_TASK', {
      task_id: targetId,
      reason: reason,
    });

    if (sent) {
      setIsProcessing(false);
    }
    return sent;
  }, [activeTask, addMessage]);

  const pauseActiveTask = useCallback((taskId?: string): boolean => {
    const targetId = taskId || activeTask?.task_id;
    if (!targetId) return false;

    return orbitWS.sendCommand('PAUSE_TASK', {
      task_id: targetId,
    });
  }, [activeTask]);

  const resumeActiveTask = useCallback((taskId?: string): boolean => {
    const targetId = taskId || activeTask?.task_id;
    if (!targetId) return false;

    return orbitWS.sendCommand('RESUME_TASK', {
      task_id: targetId,
    });
  }, [activeTask]);

  const authorizeAction = useCallback((
    taskId: string, 
    actionId: string, 
    approved: boolean, 
    reason?: string
  ): boolean => {
    // Update local message state
    setMessages((prev) => 
      prev.map((m) => {
        if (m.actionAuth && m.actionAuth.action_id === actionId) {
          return {
            ...m,
            actionAuth: {
              ...m.actionAuth,
              handled: true,
              approved: approved,
            },
          };
        }
        return m;
      })
    );

    addMessage({
      type: 'system',
      content: approved 
        ? `Authorized Tier 3 Action ${actionId.substring(0, 8)}.`
        : `Rejected Tier 3 Action ${actionId.substring(0, 8)}.`,
    });

    return orbitWS.sendCommand('AUTHORIZE_ACTION', {
      task_id: taskId,
      action_id: actionId,
      approved: approved,
      reason: reason || (approved ? 'Operator approved' : 'Operator rejected'),
    });
  }, [addMessage]);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setActiveTask(null);
    setActivePlan(null);
    setIsProcessing(false);
  }, []);

  return (
    <TaskConsoleContext.Provider
      value={{
        messages,
        activeTask,
        activePlan,
        inputMode,
        setInputMode,
        sendUserMessage,
        cancelActiveTask,
        pauseActiveTask,
        resumeActiveTask,
        authorizeAction,
        clearMessages,
        isProcessing,
      }}
    >
      {children}
    </TaskConsoleContext.Provider>
  );
};

export const useTaskConsole = (): TaskConsoleContextType => {
  const context = useContext(TaskConsoleContext);
  if (!context) {
    throw new Error('useTaskConsole must be used within a TaskConsoleProvider');
  }
  return context;
};
