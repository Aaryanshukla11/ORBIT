import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';

export type SettingsSection = 'models' | 'agent' | 'network';

export interface OrbitSettings {
  // Autonomy & Behavior
  autonomyMode: 'supervised' | 'autonomous';
  safetyGates: boolean;
  maxSteps: number;
  humanTakeoverEnabled: boolean;

  // Network & Gateway
  gatewayPort: string;
  gatewayUrl: string;

  // UI Navigation & Preferences
  activeSettingsSection: SettingsSection;
  theme: 'dark' | 'light' | 'system';
  inputMode: 'task' | 'chat';

  // AI Model Configuration
  activeModelId: string;
  providerKeys: Record<string, string>;
}

export const DEFAULT_SETTINGS: OrbitSettings = {
  autonomyMode: 'supervised',
  safetyGates: true,
  maxSteps: 15,
  humanTakeoverEnabled: true,
  gatewayPort: '8765',
  gatewayUrl: 'ws://127.0.0.1:8765/ws',
  activeSettingsSection: 'models',
  theme: 'dark',
  inputMode: 'task',
  activeModelId: 'ollama:qwen2.5:latest',
  providerKeys: {},
};

const SETTINGS_STORAGE_KEY = 'orbit_user_settings_v1';

export const loadStoredSettings = (): OrbitSettings => {
  try {
    const raw = typeof window !== 'undefined' ? localStorage.getItem(SETTINGS_STORAGE_KEY) : null;
    if (raw) {
      const parsed = JSON.parse(raw);
      return {
        ...DEFAULT_SETTINGS,
        ...parsed,
        providerKeys: {
          ...DEFAULT_SETTINGS.providerKeys,
          ...(parsed.providerKeys || {}),
        },
      };
    }
  } catch (err) {
    console.warn('Failed to load settings from localStorage, using defaults:', err);
  }
  return DEFAULT_SETTINGS;
};

export const saveStoredSettings = (settings: OrbitSettings): void => {
  try {
    if (typeof window !== 'undefined') {
      localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
    }
  } catch (err) {
    console.error('Failed to save settings to localStorage:', err);
  }
};

interface SettingsContextType {
  settings: OrbitSettings;
  updateSettings: (partial: Partial<OrbitSettings>) => void;
  saveSettings: (customOverrides?: Partial<OrbitSettings>) => void;
  resetSettings: () => void;
  saveProviderApiKey: (providerId: string, apiKey: string) => void;
  getProviderApiKey: (providerId: string) => string | undefined;
  savedToast: boolean;
  setSavedToast: (val: boolean) => void;
}

const SettingsContext = createContext<SettingsContextType | undefined>(undefined);

export const SettingsProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [settings, setSettings] = useState<OrbitSettings>(loadStoredSettings);
  const [savedToast, setSavedToast] = useState<boolean>(false);

  // Sync to localStorage on every explicit save or change
  const updateSettings = useCallback((partial: Partial<OrbitSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...partial };
      saveStoredSettings(next);
      return next;
    });
  }, []);

  const saveSettings = useCallback((customOverrides?: Partial<OrbitSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...(customOverrides || {}) };
      saveStoredSettings(next);

      // If gatewayPort changed, update gatewayUrl automatically
      if (customOverrides?.gatewayPort && !customOverrides?.gatewayUrl) {
        next.gatewayUrl = `ws://127.0.0.1:${customOverrides.gatewayPort}/ws`;
        saveStoredSettings(next);
      }

      // Sync updated API keys to gateway if connected
      if (Object.keys(next.providerKeys).length > 0 && orbitWS.isConnected) {
        Object.entries(next.providerKeys).forEach(([provId, key]) => {
          if (key && key.trim()) {
            orbitWS.sendCommand('MODEL_CONFIGURE_PROVIDER', {
              provider_id: provId,
              api_key: key.trim(),
            });
          }
        });
      }

      return next;
    });

    setSavedToast(true);
    setTimeout(() => {
      setSavedToast(false);
    }, 2500);
  }, []);

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS);
    saveStoredSettings(DEFAULT_SETTINGS);
    setSavedToast(true);
    setTimeout(() => {
      setSavedToast(false);
    }, 2500);
  }, []);

  const saveProviderApiKey = useCallback((providerId: string, apiKey: string) => {
    setSettings((prev) => {
      const cleanKey = apiKey.trim();
      const updatedKeys = {
        ...prev.providerKeys,
        [providerId.toLowerCase()]: cleanKey,
      };
      const next = {
        ...prev,
        providerKeys: updatedKeys,
      };
      saveStoredSettings(next);
      return next;
    });
  }, []);

  const getProviderApiKey = useCallback((providerId: string): string | undefined => {
    return settings.providerKeys[providerId.toLowerCase()];
  }, [settings.providerKeys]);

  // When WebSocket connects, auto-send saved cloud provider credentials to backend
  useEffect(() => {
    const unsub = orbitWS.onStateChange((state) => {
      if (state === 'CONNECTED') {
        const stored = loadStoredSettings();
        if (stored.providerKeys) {
          Object.entries(stored.providerKeys).forEach(([provId, key]) => {
            if (key && key.trim()) {
              orbitWS.sendCommand('MODEL_CONFIGURE_PROVIDER', {
                provider_id: provId,
                api_key: key.trim(),
              });
            }
          });
        }
      }
    });

    return () => unsub();
  }, []);

  return (
    <SettingsContext.Provider
      value={{
        settings,
        updateSettings,
        saveSettings,
        resetSettings,
        saveProviderApiKey,
        getProviderApiKey,
        savedToast,
        setSavedToast,
      }}
    >
      {children}
    </SettingsContext.Provider>
  );
};

export const useSettings = (): SettingsContextType => {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
};
