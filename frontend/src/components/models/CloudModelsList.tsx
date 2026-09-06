import React, { useState } from 'react';
import { CloudProviderItem } from '../../types/models';
import { useModelManager } from '../../context/ModelManagerContext';
import { KeyIcon, CheckIcon, CloudIcon, GptHexagonIcon } from '../icons/Icons';
import { ConfigureProviderModal } from './ConfigureProviderModal';

export const CloudModelsList: React.FC = () => {
  const { cloudProviders, activeModelId, switchModel, switchingModelId } = useModelManager();
  const [selectedProvider, setSelectedProvider] = useState<CloudProviderItem | null>(null);

  return (
    <div style={styles.container}>
      <div style={styles.list}>
        {cloudProviders.map((provider) => {
          const isConfigured = provider.hasKey || provider.status === 'CONFIGURED';

          return (
            <div key={provider.id} style={styles.card}>
              {/* Provider Header */}
              <div style={styles.cardHeader}>
                <div style={styles.titleWrap}>
                  <div style={styles.providerIcon}>
                    {provider.id === 'openai' ? (
                      <GptHexagonIcon size={16} color="var(--accent-primary)" />
                    ) : (
                      <CloudIcon size={16} color="var(--accent-primary)" />
                    )}
                  </div>
                  <div>
                    <span style={styles.providerName}>{provider.name}</span>
                    <div style={styles.statusLine}>
                      {isConfigured ? (
                        <span style={styles.configuredText}>
                          <span style={styles.greenDot} /> Key Configured
                        </span>
                      ) : (
                        <span style={styles.unconfiguredText}>API Key Required</span>
                      )}
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  style={styles.configBtn}
                  onClick={() => setSelectedProvider(provider)}
                  title={`Configure ${provider.name} API Key`}
                >
                  <KeyIcon size={12} color="var(--text-secondary)" />
                  <span>{isConfigured ? 'Update Key' : 'Configure'}</span>
                </button>
              </div>

              {/* Models List within provider */}
              <div style={styles.modelsContainer}>
                <span style={styles.modelsHeader}>Available Models:</span>
                <div style={styles.modelsGrid}>
                  {provider.models.map((modelName) => {
                    const fullModelId = `${provider.id}:${modelName}`;
                    const isModelActive = activeModelId === fullModelId || activeModelId === modelName;
                    const isSwitching = switchingModelId === fullModelId || switchingModelId === modelName;

                    return (
                      <div
                        key={modelName}
                        style={{
                          ...styles.modelRow,
                          borderColor: isModelActive ? 'var(--accent-primary)' : 'var(--border-subtle)',
                          backgroundColor: isModelActive ? '#f8faff' : 'var(--bg-app)',
                        }}
                      >
                        <span style={styles.modelLabel}>{modelName}</span>

                        {isModelActive ? (
                          <span style={styles.activeTag}>
                            <CheckIcon size={11} color="var(--accent-green)" />
                            Active
                          </span>
                        ) : (
                          <button
                            type="button"
                            style={{
                              ...styles.activateBtn,
                              opacity: isConfigured && !switchingModelId ? 1 : 0.5,
                              cursor: isConfigured && !switchingModelId ? 'pointer' : 'not-allowed',
                            }}
                            disabled={!isConfigured || Boolean(switchingModelId)}
                            onClick={() => switchModel(fullModelId)}
                          >
                            {isSwitching ? 'Activating...' : 'Activate'}
                          </button>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {selectedProvider && (
        <ConfigureProviderModal
          provider={selectedProvider}
          onClose={() => setSelectedProvider(null)}
        />
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
  },
  card: {
    padding: '12px',
    borderRadius: 'var(--radius-lg)',
    border: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--bg-surface)',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    userSelect: 'none',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  providerIcon: {
    width: 28,
    height: 28,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  providerName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  statusLine: {
    display: 'flex',
    alignItems: 'center',
    marginTop: '2px',
  },
  configuredText: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-green)',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  greenDot: {
    width: 5,
    height: 5,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
  },
  unconfiguredText: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  configBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '4px 8px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    color: 'var(--text-secondary)',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  modelsContainer: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
    paddingTop: '6px',
    borderTop: '1px solid var(--border-subtle)',
  },
  modelsHeader: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  modelsGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  modelRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 8px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid',
  },
  modelLabel: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    fontFamily: 'Consolas, monospace',
  },
  activeTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
  },
  activateBtn: {
    padding: '3px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    color: 'var(--text-primary)',
    fontSize: '10.5px',
    fontWeight: 600,
    transition: 'all var(--transition-fast)',
  },
};
