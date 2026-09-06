import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useOrbit } from './OrbitContext';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';
import { ExecutionRecord, ExecutionStatus } from '../types/activity';
import { EventEnvelope } from '../types';

interface ActivityHistoryContextValue {
  records: ExecutionRecord[];
  activeExecution: ExecutionRecord | null;
  selectedExecution: ExecutionRecord | null;
  filter: 'ALL' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  searchQuery: string;
  isLoading: boolean;
  setFilter: (f: 'ALL' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED') => void;
  setSearchQuery: (q: string) => void;
  selectExecution: (id: string | null) => void;
  refreshHistory: () => Promise<void>;
  clearHistory: () => Promise<void>;
  runningCount: number;
  completedCount: number;
  failedCount: number;
  cancelledCount: number;
  totalCount: number;
}

const ActivityHistoryContext = createContext<ActivityHistoryContextValue | undefined>(undefined);

export const ActivityHistoryProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const [records, setRecords] = useState<ExecutionRecord[]>([]);
  const [activeExecution, setActiveExecution] = useState<ExecutionRecord | null>(null);
  const [selectedExecution, setSelectedExecution] = useState<ExecutionRecord | null>(null);
  const [filter, setFilter] = useState<'ALL' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'>('ALL');
  const [searchQuery, setSearchQuery] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  // Fetch history via REST or WS
  const refreshHistory = useCallback(async () => {
    setIsLoading(true);
    try {
      // 1. Try REST API first for instant synchronous data
      const response = await fetch('http://127.0.0.1:8765/api/history?limit=100');
      if (response.ok) {
        const data = await response.json();
        if (data && Array.isArray(data.records)) {
          setRecords(data.records);
          const running = data.records.find((r: ExecutionRecord) => r.status === 'RUNNING' || r.status === 'REPLANNING');
          setActiveExecution(running || null);
        }
      } else if (connectionState === 'CONNECTED') {
        // 2. Fallback to WS Command
        orbitWS.sendCommand('TASK_HISTORY_LIST', { limit: 100 });
      }
    } catch (err) {
      console.warn('REST history fetch error, trying WS fallback:', err);
      if (connectionState === 'CONNECTED') {
        orbitWS.sendCommand('TASK_HISTORY_LIST', { limit: 100 });
      }
    } finally {
      setIsLoading(false);
    }
  }, [connectionState]);

  // Initial load when connected or mounted
  useEffect(() => {
    refreshHistory();
  }, [refreshHistory]);

  // Subscribe to real-time events
  useEffect(() => {
    const unsubHistoryList = orbitWS.onEvent('TASK_HISTORY_LIST_RESPONSE', (event: EventEnvelope) => {
      const payload = event.payload;
      if (payload && Array.isArray(payload.records)) {
        setRecords(payload.records);
        const running = payload.records.find((r: ExecutionRecord) => r.status === 'RUNNING' || r.status === 'REPLANNING');
        setActiveExecution(running || null);
      }
    });

    const unsubRecordUpdated = orbitWS.onEvent('EXECUTION_RECORD_UPDATED', (event: EventEnvelope) => {
      const updatedRec: ExecutionRecord = event.payload?.record;
      if (!updatedRec) return;

      setRecords((prev) => {
        const exists = prev.some((r) => r.execution_id === updatedRec.execution_id || r.task_id === updatedRec.task_id);
        let next: ExecutionRecord[];
        if (exists) {
          next = prev.map((r) =>
            r.execution_id === updatedRec.execution_id || r.task_id === updatedRec.task_id ? updatedRec : r
          );
        } else {
          next = [updatedRec, ...prev];
        }
        return next.sort((a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime());
      });

      if (updatedRec.status === 'RUNNING' || updatedRec.status === 'REPLANNING') {
        setActiveExecution(updatedRec);
      } else {
        setActiveExecution((current) =>
          current && (current.execution_id === updatedRec.execution_id || current.task_id === updatedRec.task_id)
            ? null
            : current
        );
      }

      // Update selected if open
      setSelectedExecution((cur) =>
        cur && (cur.execution_id === updatedRec.execution_id || cur.task_id === updatedRec.task_id) ? updatedRec : cur
      );
    });

    const unsubTaskState = orbitWS.onEvent('TASK_STATE_CHANGED', (event: EventEnvelope) => {
      const { task_id, status, prompt, error } = event.payload || {};
      if (!task_id) return;

      setRecords((prev) => {
        const target = prev.find((r) => r.task_id === task_id);
        if (!target) return prev;

        const updated: ExecutionRecord = {
          ...target,
          status: (status as ExecutionStatus) || target.status,
          failure_reason: error?.message || target.failure_reason,
          failure_code: error?.code || target.failure_code,
          completed_at: ['COMPLETED', 'FAILED', 'CANCELLED'].includes(status)
            ? new Date().toISOString()
            : target.completed_at,
        };

        if (['COMPLETED', 'FAILED', 'CANCELLED'].includes(status) && target.started_at) {
          updated.duration_ms = Math.max(0, Date.now() - new Date(target.started_at).getTime());
        }

        return prev.map((r) => (r.task_id === task_id ? updated : r));
      });
    });

    return () => {
      unsubHistoryList();
      unsubRecordUpdated();
      unsubTaskState();
    };
  }, []);

  const selectExecution = useCallback(
    (id: string | null) => {
      if (!id) {
        setSelectedExecution(null);
        return;
      }
      const match = records.find((r) => r.execution_id === id || r.task_id === id);
      setSelectedExecution(match || null);
    },
    [records]
  );

  const clearHistory = useCallback(async () => {
    try {
      await fetch('http://127.0.0.1:8765/api/history', { method: 'DELETE' });
    } catch {
      // ignore
    }
    orbitWS.sendCommand('TASK_HISTORY_CLEAR', {});
    setRecords([]);
    setActiveExecution(null);
    setSelectedExecution(null);
  }, []);

  const runningCount = records.filter((r) => r.status === 'RUNNING' || r.status === 'REPLANNING').length;
  const completedCount = records.filter((r) => r.status === 'COMPLETED').length;
  const failedCount = records.filter((r) => r.status === 'FAILED').length;
  const cancelledCount = records.filter((r) => r.status === 'CANCELLED').length;
  const totalCount = records.length;

  return (
    <ActivityHistoryContext.Provider
      value={{
        records,
        activeExecution,
        selectedExecution,
        filter,
        searchQuery,
        isLoading,
        setFilter,
        setSearchQuery,
        selectExecution,
        refreshHistory,
        clearHistory,
        runningCount,
        completedCount,
        failedCount,
        cancelledCount,
        totalCount,
      }}
    >
      {children}
    </ActivityHistoryContext.Provider>
  );
};

export const useActivityHistory = (): ActivityHistoryContextValue => {
  const context = useContext(ActivityHistoryContext);
  if (!context) {
    throw new Error('useActivityHistory must be used within an ActivityHistoryProvider');
  }
  return context;
};
