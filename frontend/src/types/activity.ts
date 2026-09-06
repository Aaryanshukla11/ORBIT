/**
 * Domain contracts for ORBIT Execution History & Activity.
 * Strictly maps to backend ExecutionRecord and runtime events.
 */

export type ExecutionStatus = 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED' | 'BLOCKED' | 'REPLANNING';

export interface ExecutionStepRecord {
  step_id: string;
  name: string;
  status: 'COMPLETED' | 'ACTIVE' | 'FAILED' | 'BLOCKED' | 'PENDING';
  action_type?: string | null;
  detail?: string | null;
  duration_ms?: number | null;
}

export interface ReplanAuditRecord {
  replan_id: string;
  reason: string;
  previous_step?: string | null;
  new_strategy?: string | null;
  timestamp: string;
}

export interface CompletionEvidenceRecord {
  application_name?: string | null;
  application_hwnd?: number | null;
  window_title?: string | null;
  verified_text?: string | null;
  ocr_matched_text?: string | null;
  ocr_confidence?: number | null;
  visual_changes_detected?: string[];
  accessibility_matched_elements?: string[];
  diagnostics?: Record<string, any>;
}

export interface ExecutionRecord {
  execution_id: string;
  task_id: string;
  session_id: string;
  goal: string;
  status: ExecutionStatus;
  started_at: string;
  completed_at?: string | null;
  duration_ms: number;
  active_model?: string | null;
  model_provider?: string | null;
  applications_involved: string[];
  steps: ExecutionStepRecord[];
  steps_completed: number;
  total_steps: number;
  replanning_count: number;
  replan_history: ReplanAuditRecord[];
  failure_reason?: string | null;
  failure_code?: string | null;
  cancellation_reason?: string | null;
  evidence?: CompletionEvidenceRecord | null;
  diagnostics?: Record<string, any>;
}
