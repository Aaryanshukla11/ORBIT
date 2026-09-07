import React, { useState } from 'react';
import { CloudProviderItem } from '../../types/models';
import { useModelManager, isSameModel } from '../../context/ModelManagerContext';
import { KeyIcon, CheckIcon, CloudIcon, GptHexagonIcon } from '../icons/Icons';
import { ConfigureProviderModal } from './ConfigureProviderModal';

export const CloudModelsList: React.FC = () => {
  const { cloudProviders, activeModelId, switchModel, switchingModelId, switchingError } = useModelManager();
  const [selectedProvider, setSelectedProvider] = useState<CloudProviderItem | null>(null);

  return (
    <div style={styles.container}>
      {switchingError && (
        <div style={styles.errorBanner}>
          <span style={styles.errorText}>{switchingError}</span>
        </div>
      )}

      <div style={styles.list}>
        {cloudProviders.map((provider) => {
          const isAuth = provider.status === 'AUTHENTICATED';
          const isAuthFailed = provider.status === 'AUTH_FAILED';
          const isAuthenticating = provider.status === 'AUTHENTICATING';
          const isUnreachable = provider.status === 'UNREACHABLE' || provider.status === 'UNAVAILABLE';
          const isUnverified = provider.status === 'CONFIGURED_UNVERIFIED';
          const isConfigured = Boolean(provider.hasKey || isAuth || isAuthFailed || isUnverified);

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
                      {isAuth ? (
                        <span style={styles.authenticatedText}>
                          <span style={styles.greenDot} /> Authenticated
                        </span>
                      ) : isAuthFailed ? (
                        <span style={styles.authFailedText}>
                          <span style={styles.redDot} /> Authentication Failed
                        </span>
                      ) : isAuthenticating ? (
                        <span style={styles.authenticatingText}>
                          <span style={styles.yellowDot} /> Verifying Credentials...
                        </span>
                      ) : isUnreachable ? (
                        <span style={styles.unreachableText}>
                          <span style={styles.yellowDot} /> Unreachable
                        </span>
                      ) : isUnverified ? (
                        <span style={styles.authenticatingText}>
                          <span style={styles.yellowDot} /> Key Configured (Unverified)
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
                  <span>{isAuth ? 'Update Key' : isAuthFailed ? 'Fix Key' : 'Configure'}</span>
                </button>
              </div>

              {/* Diagnostic Error Strip for Auth Failure */}
              {isAuthFailed && provider.diagnosticMessage && (
                <div style={styles.providerDiagBanner}>
                  <span style={styles.providerDiagText}>
                    {provider.diagnosticMessage}
                  </span>
                </div>
              )}

              {/* Models List within provider */}
              <div style={styles.modelsContainer}>
                <span style={styles.modelsHeader}>
                  {isAuth
                    ? 'Available Models:'
                    : isAuthFailed
                    ? 'Supported Models (Auth Failed - Invalid Key):'
                    : 'Supported Models (API Key Required):'}
                </span>
                <div style={styles.modelsGrid}>
                  {provider.models.map((modelName) => {
                    const fullModelId = `cloud:${provider.id}:${modelName}`;
                    const altModelId = `${provider.id}:${modelName}`;
                    const isModelActive =
                      isSameModel(activeModelId, fullModelId) ||
                      isSameModel(activeModelId, altModelId) ||
                      isSameModel(activeModelId, modelName);
                    const isSwitching =
                      isSameModel(switchingModelId, fullModelId) ||
                      isSameModel(switchingModelId, altModelId) ||
                      isSameModel(switchingModelId, modelName);

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
                        ) : isAuth ? (
                          <button
                            type="button"
                            style={{
                              ...styles.activateBtn,
                              opacity: switchingModelId ? 0.6 : 1,
                              cursor: switchingModelId ? 'not-allowed' : 'pointer',
                            }}
                            disabled={Boolean(switchingModelId)}
                            onClick={() => switchModel(fullModelId)}
                          >
                            {isSwitching ? 'Activating...' : 'Activate'}
                          </button>
                        ) : isAuthFailed ? (
                          <button
                            type="button"
                            style={styles.fixKeyBtn}
                            onClick={() => setSelectedProvider(provider)}
                            title={`Authentication failed for ${provider.name}. Click to update API key.`}
                          >
                            <KeyIcon size={11} color="var(--accent-red)" />
                            <span>Fix Key</span>
                          </button>
                        ) : (
                          <button
                            type="button"
                            style={styles.setKeyBtn}
                            onClick={() => setSelectedProvider(provider)}
                            title={`Set ${provider.name} API key to enable ${modelName}`}
                          >
                            <KeyIcon size={11} color="var(--accent-primary)" />
                            <span>Set Key</span>
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
  authenticatedText: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-green)',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  authFailedText: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-red)',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  authenticatingText: {
    fontSize: '10px',
    fontWeight: 600,
    color: '#d97706',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  unreachableText: {
    fontSize: '10px',
    fontWeight: 600,
    color: '#d97706',
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  greenDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
  },
  redDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-red)',
  },
  yellowDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    backgroundColor: '#d97706',
  },
  unconfiguredText: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  providerDiagBanner: {
    padding: '6px 8px',
    borderRadius: 'var(--radius-sm)',
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
  },
  providerDiagText: {
    fontSize: '10.5px',
    color: 'var(--accent-red)',
    fontWeight: 500,
    lineHeight: 1.3,
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
  fixKeyBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid rgba(239, 68, 68, 0.3)',
    backgroundColor: 'rgba(239, 68, 68, 0.08)',
    color: 'var(--accent-red)',
    fontSize: '10.5px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  setKeyBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--accent-primary-subtle)',
    backgroundColor: 'var(--accent-primary-subtle)',
    color: 'var(--accent-primary)',
    fontSize: '10.5px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  errorBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-red-subtle)',
    border: '1px solid rgba(239, 68, 68, 0.2)',
  },
  errorText: {
    fontSize: '11px',
    color: 'var(--accent-red)',
    fontWeight: 500,
    lineHeight: 1.3,
  },
};
