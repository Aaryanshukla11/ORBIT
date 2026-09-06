import { Task, ExecutionPlan, TaskStatus, ErrorDetail, Action } from './task';

export type MessageType = 
  | 'user'
  | 'assistant'
  | 'system'
  | 'task_event'
  | 'error'
  | 'action_auth';

export type InputMode = 'task' | 'chat';

export interface ActionAuthPayload {
  action_id: string;
  task_id: string;
  action_type: string;
  tier: string;
  description: string;
  parameters: Record<string, any>;
  approved?: boolean;
  handled?: boolean;
}

export interface ChatMessage {
  id: string;
  type: MessageType;
  timestamp: string;
  content: string;
  sender?: string;
  taskId?: string;
  taskStatus?: TaskStatus;
  plan?: ExecutionPlan;
  activeAction?: Action;
  actionAuth?: ActionAuthPayload;
  errorDetail?: ErrorDetail;
  metadata?: Record<string, any>;
}
