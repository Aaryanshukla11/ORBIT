/**
 * Task, Plan, and Runtime Domain Models
 * Strictly aligned with ORBIT backend contracts (src/orbit/contracts/runtime.py)
 */

export type TaskStatus = 
  | 'CREATED'
  | 'QUEUED'
  | 'VALIDATING'
  | 'READY'
  | 'RUNNING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'PAUSED';

export type ActionStage = 
  | 'PENDING'
  | 'AUTHORIZED'
  | 'DISPATCHED'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'REJECTED';

export type ActionTier = 
  | 'TIER_1_SAFE'
  | 'TIER_2_CONSTRAINED'
  | 'TIER_3_HIGH_IMPACT';

export type VerificationStatus = 
  | 'PASSED'
  | 'FAILED'
  | 'INCONCLUSIVE'
  | 'SKIPPED';

export interface VerificationResult {
  status: VerificationStatus;
  confidence: number;
  details?: Record<string, any>;
  evaluated_at?: string;
}

export interface ErrorDetail {
  code: string;
  message: string;
  recoverable?: boolean;
  details?: Record<string, any>;
}

export interface Action {
  action_id: string;
  task_id: string;
  action_type: string;
  tier: ActionTier;
  stage: ActionStage;
  parameters: Record<string, any>;
  created_at?: string;
  dispatched_at?: string;
  completed_at?: string;
  verification?: VerificationResult;
  error?: ErrorDetail;
}

export interface Step {
  step_id: string;
  step_index: number;
  description: string;
  actions: Action[];
  status: TaskStatus;
}

export interface ExecutionPlan {
  plan_id: string;
  task_id: string;
  description: string;
  steps: Step[];
  created_at: string;
  updated_at: string;
}

export interface Task {
  task_id: string;
  session_id: string;
  prompt: string;
  status: TaskStatus;
  plan?: ExecutionPlan;
  current_step_index: number;
  created_at: string;
  started_at?: string;
  completed_at?: string;
  error?: ErrorDetail;
  metadata?: Record<string, any>;
}

export type TaskExecutionStage = 
  | 'UNDERSTANDING'
  | 'PLANNING'
  | 'READY'
  | 'EXECUTING'
  | 'VERIFYING'
  | 'COMPLETED'
  | 'FAILED'
  | 'CANCELLED'
  | 'PAUSED';
