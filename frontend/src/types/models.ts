/**
 * AI Model Manager Domain Types
 * Matching ORBIT backend model inventory and runtime contracts
 */

export type ModelSourceType = 'local' | 'cloud';

export type ModelCapability = 'Code' | 'Text' | 'Vision' | 'Reasoning';

export type ModelStatus = 'ACTIVE' | 'INSTALLED' | 'AVAILABLE' | 'SWITCHING' | 'CONFIGURED' | 'NOT_CONFIGURED';

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

export interface CloudProviderItem {
  id: string;
  name: string;
  providerCode: 'openai' | 'anthropic' | 'google' | 'deepseek' | 'custom';
  status: 'CONFIGURED' | 'READY' | 'DISCONNECTED' | 'NEEDS_KEY';
  models: string[];
  activeModelId?: string;
  hasKey: boolean;
  maskedEndpoint?: string;
}

export interface SystemRuntimeStatus {
  runtimeState: 'READY' | 'INITIALIZING' | 'SWITCHING' | 'BUSY' | 'DEGRADED';
  activeProvider: 'Local Runtime' | 'Cloud API' | 'None';
  modelAvailability: 'Available' | 'Offline' | 'Degraded';
  gatewayConnection: 'Connected' | 'Disconnected' | 'Reconnecting';
}
