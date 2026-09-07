/**
 * AI Model Manager Domain Types
 * Matching ORBIT backend model inventory and runtime contracts
 */

export type ModelSourceType = 'local' | 'cloud';

export type ModelCapability = 'Code' | 'Text' | 'Vision' | 'Reasoning' | 'Chat';

export type ModelStatus = 'ACTIVE' | 'INSTALLED' | 'AVAILABLE' | 'UNAVAILABLE' | 'SWITCHING' | 'CONFIGURED' | 'NOT_CONFIGURED';

export interface ModelItem {
  id: string;
  name: string;
  provider: string;
  type: ModelSourceType;
  family: string;
  size?: string;
  contextWindow: number;
  capabilities: ModelCapability[];
  installed: boolean;
  status: ModelStatus;
  hardwareReq?: string;
  description?: string;
}

export type CloudProviderStatus =
  | 'AUTHENTICATED'
  | 'AUTH_FAILED'
  | 'AUTHENTICATING'
  | 'CONFIGURED_UNVERIFIED'
  | 'UNAVAILABLE'
  | 'UNREACHABLE'
  | 'NOT_CONFIGURED'
  | 'CONFIGURED'
  | 'READY'
  | 'DISCONNECTED'
  | 'NEEDS_KEY'
  | 'ERROR';

export interface CloudProviderItem {
  id: string;
  name: string;
  providerCode: 'openai' | 'anthropic' | 'google' | 'deepseek' | 'custom' | string;
  status: CloudProviderStatus;
  models: string[];
  activeModelId?: string;
  hasKey: boolean;
  authStatus?: CloudProviderStatus;
  diagnosticMessage?: string;
  modelsCount?: number;
  maskedEndpoint?: string;
}

export interface SystemRuntimeStatus {
  runtimeState: 'READY' | 'INITIALIZING' | 'SWITCHING' | 'BUSY' | 'DEGRADED';
  activeProvider: 'Local Runtime' | 'Cloud API' | 'None';
  modelAvailability: 'Available' | 'Offline' | 'Degraded';
  gatewayConnection: 'Connected' | 'Disconnected' | 'Reconnecting';
}
