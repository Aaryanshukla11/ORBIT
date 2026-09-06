import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { ModelItem, CloudProviderItem, ModelSourceType, SystemRuntimeStatus } from '../types/models';
import { EventEnvelope } from '../types';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';
import { useOrbit } from './OrbitContext';

interface ModelManagerContextType {
  models: ModelItem[];
  cloudProviders: CloudProviderItem[];
  activeModelId: string;
  activeModel: ModelItem | null;
  switchingModelId: string | null;
  switchingError: string | null;
  sourceTab: ModelSourceType;
  setSourceTab: (tab: ModelSourceType) => void;
  systemStatus: SystemRuntimeStatus;
  switchModel: (modelId: string) => boolean;
  discoverModels: () => void;
  saveProviderKey: (providerId: string, apiKey: string) => boolean;
}

const DEFAULT_LOCAL_MODELS: ModelItem[] = [
  {
    id: 'ollama:qwen2.5-coder:7b',
    name: 'Qwen2.5-Coder 7B',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'Qwen2.5',
    size: '4.7 GB',
    contextWindow: 32768,
    capabilities: ['Code', 'Text', 'Reasoning'],
    installed: true,
    status: 'ACTIVE',
    hardwareReq: '8GB VRAM / 16GB RAM',
    description: 'High-performance coding agent with native instruction following.',
  },
  {
    id: 'ollama:qwen2.5-coder:1.5b',
    name: 'Qwen2.5-Coder 1.5B',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'Qwen2.5',
    size: '1.2 GB',
    contextWindow: 32768,
    capabilities: ['Code', 'Text'],
    installed: true,
    status: 'INSTALLED',
    hardwareReq: '4GB RAM (CPU/iGPU)',
    description: 'Ultra-lightweight fast local code model.',
  },
  {
    id: 'ollama:qwen2.5-coder:14b',
    name: 'Qwen2.5-Coder 14B',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'Qwen2.5',
    size: '9.0 GB',
    contextWindow: 32768,
    capabilities: ['Code', 'Text', 'Reasoning'],
    installed: true,
    status: 'INSTALLED',
    hardwareReq: '16GB VRAM (NVIDIA RTX)',
    description: 'State-of-the-art local coding and architecture synthesis.',
  },
  {
    id: 'ollama:llama3.2-vision:latest',
    name: 'Llama 3.2 Vision 11B',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'Llama',
    size: '7.9 GB',
    contextWindow: 128000,
    capabilities: ['Vision', 'Text', 'Code'],
    installed: true,
    status: 'INSTALLED',
    hardwareReq: '12GB VRAM',
    description: 'Multimodal vision perception for desktop OCR and screen grounding.',
  },
  {
    id: 'ollama:deepseek-coder-v2:lite',
    name: 'DeepSeek-Coder-V2-Lite',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'DeepSeek',
    size: '8.9 GB',
    contextWindow: 64000,
    capabilities: ['Code', 'Text', 'Reasoning'],
    installed: true,
    status: 'INSTALLED',
    hardwareReq: '12GB VRAM / 24GB RAM',
    description: 'Mixture-of-Experts coder with extensive multilingual syntax mastery.',
  },
];

const DEFAULT_CLOUD_PROVIDERS: CloudProviderItem[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    providerCode: 'openai',
    status: 'CONFIGURED',
    models: ['gpt-4o', 'gpt-4o-mini', 'o1-preview', 'o1-mini'],
    activeModelId: 'gpt-4o',
    hasKey: true,
    maskedEndpoint: 'api.openai.com/v1',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    providerCode: 'anthropic',
    status: 'CONFIGURED',
    models: ['claude-3-5-sonnet', 'claude-3-5-haiku', 'claude-3-opus'],
    activeModelId: 'claude-3-5-sonnet',
    hasKey: true,
    maskedEndpoint: 'api.anthropic.com/v1',
  },
  {
    id: 'google',
    name: 'Google Gemini',
    providerCode: 'google',
    status: 'READY',
    models: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
    hasKey: false,
    maskedEndpoint: 'generativelanguage.googleapis.com',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek Cloud',
    providerCode: 'deepseek',
    status: 'READY',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    hasKey: false,
    maskedEndpoint: 'api.deepseek.com/v1',
  },
];

const ModelManagerContext = createContext<ModelManagerContextType | undefined>(undefined);

export const ModelManagerProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const [models, setModels] = useState<ModelItem[]>(DEFAULT_LOCAL_MODELS);
  const [cloudProviders, setCloudProviders] = useState<CloudProviderItem[]>(DEFAULT_CLOUD_PROVIDERS);
  const [activeModelId, setActiveModelId] = useState<string>('ollama:qwen2.5-coder:7b');
  const [switchingModelId, setSwitchingModelId] = useState<string | null>(null);
  const [switchingError, setSwitchingError] = useState<string | null>(null);
  const [sourceTab, setSourceTab] = useState<ModelSourceType>('local');

  const [systemStatus, setSystemStatus] = useState<SystemRuntimeStatus>({
    runtimeState: 'READY',
    activeProvider: 'Local Runtime',
    modelAvailability: 'Available',
    gatewayConnection: connectionState === 'CONNECTED' ? 'Connected' : 'Disconnected',
  });

  useEffect(() => {
    setSystemStatus((prev) => ({
      ...prev,
      gatewayConnection: connectionState === 'CONNECTED' ? 'Connected' : 'Disconnected',
    }));
  }, [connectionState]);

  // Sync with Gateway Events
  useEffect(() => {
    const unsubEvents = orbitWS.onAnyEvent((event: EventEnvelope) => {
      const { event_type, payload } = event;

      // Active Model Response
      if (event_type === 'MODEL_ACTIVE_RESPONSE' || event_type === 'MODEL_ACTIVE_UPDATED') {
        if (payload?.model?.model_id) {
          const mId = payload.model.model_id;
          setActiveModelId(mId);
          setSwitchingModelId(null);
          setSwitchingError(null);

          setModels((prev) =>
            prev.map((m) => ({
              ...m,
              status: m.id === mId ? 'ACTIVE' : m.status === 'ACTIVE' ? 'INSTALLED' : m.status,
            }))
          );
        }
      }

      // Switch Started
      if (event_type === 'MODEL_SWITCH_STARTED' || event_type === 'MODEL_ACTIVATION_STARTED') {
        const targetId = payload.target_model_id || payload.model_id;
        if (targetId) {
          setSwitchingModelId(targetId);
          setSwitchingError(null);
          setSystemStatus((prev) => ({ ...prev, runtimeState: 'SWITCHING' }));
        }
      }

      // Switch Succeeded
      if (event_type === 'MODEL_SWITCH_SUCCEEDED' || event_type === 'MODEL_SWITCHED' || event_type === 'MODEL_ACTIVATED') {
        const targetId = payload.target_model_id || payload.model_id;
        if (targetId) {
          setActiveModelId(targetId);
          setSwitchingModelId(null);
          setSwitchingError(null);
          setSystemStatus((prev) => ({ ...prev, runtimeState: 'READY' }));

          setModels((prev) =>
            prev.map((m) => ({
              ...m,
              status: m.id === targetId ? 'ACTIVE' : m.status === 'ACTIVE' ? 'INSTALLED' : m.status,
            }))
          );
        }
      }

      // Switch Failed
      if (event_type === 'MODEL_SWITCH_FAILED' || event_type === 'MODEL_RUNTIME_FAILED') {
        setSwitchingModelId(null);
        setSwitchingError(payload.failure_reason || payload.message || 'Model activation failed');
        setSystemStatus((prev) => ({ ...prev, runtimeState: 'DEGRADED' }));
      }

      // Discovery Completed
      if (event_type === 'MODEL_DISCOVERY_COMPLETED' || event_type === 'MODEL_LIST_RESPONSE') {
        if (payload?.models && Array.isArray(payload.models)) {
          // Merge discovered models
          setModels((prev) => {
            const incoming: ModelItem[] = payload.models.map((m: any) => ({
              id: m.model_id || m.id,
              name: m.name || m.model_id,
              provider: m.provider || 'Local',
              type: m.type || (m.provider?.toLowerCase().includes('ollama') ? 'local' : 'cloud'),
              family: m.family || 'LLM',
              size: m.size || 'N/A',
              contextWindow: m.context_window || 32768,
              capabilities: m.capabilities || ['Text', 'Code'],
              installed: m.installed ?? true,
              status: (m.model_id === activeModelId ? 'ACTIVE' : 'INSTALLED') as any,
              hardwareReq: m.hardware_req,
            }));
            return incoming.length > 0 ? incoming : prev;
          });
        }
      }
    });

    return () => {
      unsubEvents();
    };
  }, [activeModelId]);

  const switchModel = useCallback((modelId: string): boolean => {
    if (switchingModelId) return false; // Prevent duplicate requests
    if (modelId === activeModelId) return true;

    setSwitchingModelId(modelId);
    setSwitchingError(null);
    setSystemStatus((prev) => ({ ...prev, runtimeState: 'SWITCHING' }));

    const sent = orbitWS.sendCommand('MODEL_SWITCH', {
      model_id: modelId,
      policy: 'REJECT_DURING_ACTIVE_TASK',
      timeout_seconds: 30.0,
      preload_weights: true,
    });

    if (!sent) {
      // If gateway offline, update local mock state cleanly with temporary timeout
      setTimeout(() => {
        setActiveModelId(modelId);
        setSwitchingModelId(null);
        setSystemStatus((prev) => ({ ...prev, runtimeState: 'READY' }));
        setModels((prev) =>
          prev.map((m) => ({
            ...m,
            status: m.id === modelId ? 'ACTIVE' : m.status === 'ACTIVE' ? 'INSTALLED' : m.status,
          }))
        );
      }, 500);
    }
    return true;
  }, [switchingModelId, activeModelId]);

  const discoverModels = useCallback(() => {
    orbitWS.sendCommand('MODEL_DISCOVER', {
      include_runtimes: true,
      include_cloud: true,
      include_files: true,
    });
  }, []);

  const saveProviderKey = useCallback((providerId: string, apiKey: string): boolean => {
    if (!apiKey.trim()) return false;

    setCloudProviders((prev) =>
      prev.map((p) => {
        if (p.id === providerId) {
          return {
            ...p,
            status: 'CONFIGURED',
            hasKey: true,
          };
        }
        return p;
      })
    );

    // Notify backend
    orbitWS.sendCommand('MODEL_DISCOVER', { provider: providerId });
    return true;
  }, []);

  const activeModel = models.find((m) => m.id === activeModelId) || models[0] || null;

  return (
    <ModelManagerContext.Provider
      value={{
        models,
        cloudProviders,
        activeModelId,
        activeModel,
        switchingModelId,
        switchingError,
        sourceTab,
        setSourceTab,
        systemStatus,
        switchModel,
        discoverModels,
        saveProviderKey,
      }}
    >
      {children}
    </ModelManagerContext.Provider>
  );
};

export const useModelManager = (): ModelManagerContextType => {
  const context = useContext(ModelManagerContext);
  if (!context) {
    throw new Error('useModelManager must be used within a ModelManagerProvider');
  }
  return context;
};
