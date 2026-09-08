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
    id: 'ollama:qwen2.5:latest',
    name: 'Qwen2.5 7.6B',
    provider: 'Ollama / Local',
    type: 'local',
    family: 'Qwen2.5',
    size: '4.7 GB',
    contextWindow: 32768,
    capabilities: ['Chat', 'Text', 'Code'],
    installed: true,
    status: 'ACTIVE',
    hardwareReq: '8GB VRAM / 16GB RAM',
    description: 'High-performance general reasoning, chat, and executive copilot.',
  },
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
    status: 'INSTALLED',
    hardwareReq: '8GB VRAM / 16GB RAM',
    description: 'High-performance coding agent with native instruction following.',
  },
  {
    id: 'ollama:qwen2.5-coder:14B',
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
];

export const normalizeModelId = (id?: string | null): string => {
  if (!id) return '';
  let cleaned = id.trim().toLowerCase();
  // Strip known provider prefixes like "ollama:", "openai:", "anthropic:", "google:", "gemini:", "deepseek:", "cloud:", "local:"
  cleaned = cleaned.replace(/^(?:ollama|openai|anthropic|google|gemini|deepseek|cloud|local):(?:\w+:)?/, '');
  return cleaned;
};

export const isSameModel = (a?: string | null, b?: string | null): boolean => {
  if (!a || !b) return false;
  const aRaw = a.trim().toLowerCase();
  const bRaw = b.trim().toLowerCase();
  if (aRaw === bRaw) return true;

  const normA = normalizeModelId(a);
  const normB = normalizeModelId(b);
  if (normA && normB && normA === normB) return true;

  // If one has explicit ":latest" and the other doesn't
  const stripLatest = (s: string) => (s.endsWith(':latest') ? s.slice(0, -7) : s);
  if (normA && normB && stripLatest(normA) === stripLatest(normB)) return true;

  return false;
};

const DEFAULT_CLOUD_PROVIDERS: CloudProviderItem[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    providerCode: 'openai',
    status: 'NOT_CONFIGURED',
    models: ['gpt-4o', 'gpt-4o-mini', 'o1-preview', 'o1-mini'],
    hasKey: false,
    maskedEndpoint: 'api.openai.com/v1',
  },
  {
    id: 'anthropic',
    name: 'Anthropic',
    providerCode: 'anthropic',
    status: 'NOT_CONFIGURED',
    models: ['claude-3-5-sonnet', 'claude-3-5-haiku', 'claude-3-opus'],
    hasKey: false,
    maskedEndpoint: 'api.anthropic.com/v1',
  },
  {
    id: 'google',
    name: 'Google Gemini',
    providerCode: 'google',
    status: 'NOT_CONFIGURED',
    models: ['gemini-2.0-flash', 'gemini-1.5-pro', 'gemini-1.5-flash'],
    hasKey: false,
    maskedEndpoint: 'generativelanguage.googleapis.com',
  },
  {
    id: 'deepseek',
    name: 'DeepSeek Cloud',
    providerCode: 'deepseek',
    status: 'NOT_CONFIGURED',
    models: ['deepseek-chat', 'deepseek-reasoner'],
    hasKey: false,
    maskedEndpoint: 'api.deepseek.com/v1',
  },
];

import { loadStoredSettings, saveStoredSettings } from './SettingsContext';

const ModelManagerContext = createContext<ModelManagerContextType | undefined>(undefined);

export const ModelManagerProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const initialSettings = loadStoredSettings();

  const [models, setModels] = useState<ModelItem[]>(DEFAULT_LOCAL_MODELS);
  const [cloudProviders, setCloudProviders] = useState<CloudProviderItem[]>(() => {
    const keys = initialSettings.providerKeys || {};
    return DEFAULT_CLOUD_PROVIDERS.map((cp) => {
      const keyVal = keys[cp.id.toLowerCase()] || keys[cp.providerCode?.toLowerCase() || ''];
      if (keyVal) {
        return {
          ...cp,
          hasKey: true,
          status: 'CONFIGURED',
        };
      }
      return cp;
    });
  });

  const [activeModelId, setActiveModelIdState] = useState<string>(() => initialSettings.activeModelId || 'ollama:qwen2.5:latest');
  const [switchingModelId, setSwitchingModelId] = useState<string | null>(null);
  const [switchingError, setSwitchingError] = useState<string | null>(null);
  const [sourceTab, setSourceTab] = useState<ModelSourceType>('local');

  const setActiveModelId = useCallback((mId: string) => {
    setActiveModelIdState(mId);
    const curr = loadStoredSettings();
    saveStoredSettings({ ...curr, activeModelId: mId });
  }, []);

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
        const mId = payload?.active_model?.model_id || payload?.model?.model_id || payload?.active_model_id;
        if (mId) {
          setActiveModelId(mId);
          setSwitchingModelId(null);
          setSwitchingError(null);

          setModels((prev) =>
            prev.map((m) => ({
              ...m,
              status: isSameModel(m.id, mId) ? 'ACTIVE' : m.status === 'ACTIVE' ? 'INSTALLED' : m.status,
            }))
          );
        }
      }

      // Switch Started
      if (event_type === 'MODEL_SWITCH_STARTED' || event_type === 'MODEL_ACTIVATION_STARTED') {
        const targetId = payload?.active_model_id || payload?.target_model_id || payload?.model_id;
        if (targetId) {
          setSwitchingModelId(targetId);
          setSwitchingError(null);
          setSystemStatus((prev) => ({ ...prev, runtimeState: 'SWITCHING' }));
        }
      }

      // Switch Succeeded
      if (event_type === 'MODEL_SWITCH_SUCCEEDED' || event_type === 'MODEL_SWITCHED' || event_type === 'MODEL_ACTIVATED') {
        const targetId = payload?.active_model_id || payload?.target_model_id || payload?.model_id;
        if (targetId) {
          setActiveModelId(targetId);
          setSwitchingModelId(null);
          setSwitchingError(null);
          setSystemStatus((prev) => ({ ...prev, runtimeState: 'READY' }));

          setModels((prev) =>
            prev.map((m) => ({
              ...m,
              status: isSameModel(m.id, targetId) ? 'ACTIVE' : m.status === 'ACTIVE' ? 'INSTALLED' : m.status,
            }))
          );
        }
      }

      // Switch Failed
      if (event_type === 'MODEL_SWITCH_FAILED' || event_type === 'MODEL_RUNTIME_FAILED') {
        setSwitchingModelId(null);
        setSwitchingError(payload?.diagnostic_message || payload?.failure_reason || payload?.message || 'Model activation failed');
        setSystemStatus((prev) => ({ ...prev, runtimeState: 'DEGRADED' }));
      }

      // Error event
      if (event_type === 'ERROR') {
        if (switchingModelId) {
          setSwitchingModelId(null);
          setSwitchingError(payload?.message || 'Model operation rejected by gateway');
          setSystemStatus((prev) => ({ ...prev, runtimeState: 'DEGRADED' }));
        }
      }

      // Discovery Completed or List Response
      if (
        event_type === 'MODEL_DISCOVER_RESPONSE' ||
        event_type === 'MODEL_DISCOVERY_COMPLETED' ||
        event_type === 'MODEL_LIST_RESPONSE'
      ) {
        if (payload?.models && Array.isArray(payload.models)) {
          const actId = payload.active_model_id || activeModelId;
          const incoming: ModelItem[] = payload.models.map((m: any) => {
            const mId = m.model_id || m.id;
            const isLocal = m.runtime_kind === 'LOCAL_OLLAMA' || (m.provider && m.provider.toLowerCase().includes('ollama')) || (m.type === 'local');
            return {
              id: mId,
              name: m.display_name || m.name || mId,
              provider: m.provider || (isLocal ? 'Ollama / Local' : 'Cloud Provider'),
              type: isLocal ? 'local' : 'cloud',
              family: m.family || 'LLM',
              size: m.parameter_size || m.size || 'N/A',
              contextWindow: m.context_window || 32768,
              capabilities: (m.capabilities && m.capabilities.length > 0) ? m.capabilities : ['Text', 'Code'],
              installed: m.installed ?? true,
              status: (isSameModel(mId, actId) ? 'ACTIVE' : (m.status || 'INSTALLED')) as any,
              hardwareReq: m.hardware_req || (m.parameter_size?.includes('14') ? '16GB VRAM' : (m.parameter_size?.includes('7') ? '8GB VRAM' : 'Local Hardware')),
              description: m.description || `${m.display_name || mId} model running on ${m.provider || 'local host'}.`,
            };
          });
          if (incoming.length > 0) {
            setModels(incoming);
          }
          if (payload.active_model_id) {
            setActiveModelId(payload.active_model_id);
          }
        }

        if (payload?.cloud_providers && Array.isArray(payload.cloud_providers)) {
          setCloudProviders((prev) =>
            prev.map((cp) => {
              const matched = payload.cloud_providers.find(
                (p: any) =>
                  p.id?.toLowerCase() === cp.id?.toLowerCase() ||
                  p.providerCode?.toLowerCase() === cp.providerCode?.toLowerCase()
              );
              if (matched) {
                return {
                  ...cp,
                  status: matched.status || matched.authStatus || cp.status,
                  authStatus: matched.authStatus || matched.status,
                  hasKey: matched.hasKey ?? cp.hasKey,
                  diagnosticMessage: matched.diagnosticMessage || matched.diagnostic_message,
                  modelsCount: matched.modelsCount ?? matched.models_count,
                  maskedEndpoint: matched.maskedEndpoint || cp.maskedEndpoint,
                };
              }
              return cp;
            })
          );
        }
      }
    });

    // Auto-discover, list, and query active model on connect
    if (connectionState === 'CONNECTED') {
      orbitWS.sendCommand('MODEL_DISCOVER', { include_runtimes: true, include_cloud: true, include_files: true });
      orbitWS.sendCommand('MODEL_LIST', { include_all: true });
      orbitWS.sendCommand('MODEL_ACTIVE', {});
    }

    return () => {
      unsubEvents();
    };
  }, [activeModelId, switchingModelId, connectionState]);

  const switchModel = useCallback((modelId: string): boolean => {
    if (switchingModelId) return false;
    if (isSameModel(modelId, activeModelId)) return true;

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
      setSwitchingModelId(null);
      setSwitchingError('Cannot switch model: Gateway is disconnected.');
      setSystemStatus((prev) => ({ ...prev, runtimeState: 'DEGRADED' }));
      return false;
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

    // Persist provider API key to localStorage so it is retained across reloads
    const curr = loadStoredSettings();
    saveStoredSettings({
      ...curr,
      providerKeys: {
        ...curr.providerKeys,
        [providerId.toLowerCase()]: apiKey.trim(),
      },
    });

    // Transition to AUTHENTICATING status while backend validates credentials
    setCloudProviders((prev) =>
      prev.map((p) => {
        if (p.id.toLowerCase() === providerId.toLowerCase() || p.providerCode?.toLowerCase() === providerId.toLowerCase()) {
          return {
            ...p,
            status: 'AUTHENTICATING',
            authStatus: 'AUTHENTICATING',
            hasKey: true,
            diagnosticMessage: 'Validating credentials with provider...',
          };
        }
        return p;
      })
    );

    // Send configuration command to backend for live validation
    orbitWS.sendCommand('MODEL_CONFIGURE_PROVIDER', {
      provider_id: providerId,
      api_key: apiKey.trim(),
    });
    return true;
  }, []);

  const activeModel =
    models.find((m) => isSameModel(m.id, activeModelId)) ||
    models[0] ||
    null;

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
