import React, { useState } from 'react';
import { CloudProviderItem } from '../../types/models';
import { KeyIcon, CloseIcon, ShieldIcon, EyeIcon, EyeOffIcon, CheckCircleIcon } from '../icons/Icons';
import { useModelManager } from '../../context/ModelManagerContext';

interface ConfigureProviderModalProps {
  provider: CloudProviderItem;
  onClose: () => void;
}

export const ConfigureProviderModal: React.FC<ConfigureProviderModalProps> = ({ provider, onClose }) => {
  const { saveProviderKey } = useModelManager();
  const [apiKey, setApiKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [savedSuccess, setSavedSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    if (!apiKey.trim()) {
      setError('Please enter a valid API key');
      return;
    }

    const ok = saveProviderKey(provider.id, apiKey.trim());
    if (ok) {
      setSavedSuccess(true);
      setTimeout(() => {
        onClose();
      }, 900);
    } else {
      setError('Failed to securely store provider credentials');
    }
  };

  return (
    <div style={styles.backdrop} onClick={onClose}>
      <div style={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Modal Header */}
        <div style={styles.header}>
          <div style={styles.titleWrap}>
            <KeyIcon size={16} color="var(--accent-primary)" />
            <h3 style={styles.title}>Configure {provider.name}</h3>
          </div>
          <button type="button" onClick={onClose} style={styles.closeBtn}>
            <CloseIcon size={13} color="var(--text-muted)" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSave} style={styles.body}>
          <div style={styles.securityNotice}>
            <ShieldIcon size={14} color="var(--accent-primary)" />
            <span style={styles.securityText}>
              Credentials are encrypted into the local Windows Secure Vault. Plaintext keys are never transmitted or exposed in the UI.
            </span>
          </div>

          <div style={styles.fieldGroup}>
            <label style={styles.label}>
              {provider.name} API Key
              {provider.hasKey && <span style={styles.configuredBadge}>Key Configured</span>}
            </label>
            <div style={styles.inputWrapper}>
              <input
                type={showKey ? 'text' : 'password'}
                value={apiKey}
                onChange={(e) => {
                  setApiKey(e.target.value);
                  setError(null);
                }}
                placeholder={provider.hasKey ? '••••••••••••••••••••••••••••••••' : `Enter ${provider.name} API Key...`}
                style={styles.input}
                autoFocus
              />
              <button
                type="button"
                style={styles.eyeBtn}
                onClick={() => setShowKey(!showKey)}
                title={showKey ? 'Hide Key' : 'Show Key'}
              >
                {showKey ? (
                  <EyeOffIcon size={14} color="var(--text-muted)" />
                ) : (
                  <EyeIcon size={14} color="var(--text-muted)" />
                )}
              </button>
            </div>
            {error && <span style={styles.errorText}>{error}</span>}
          </div>

          {provider.maskedEndpoint && (
            <div style={styles.endpointRow}>
              <span style={styles.endpointLabel}>Endpoint:</span>
              <span style={styles.endpointVal}>{provider.maskedEndpoint}</span>
            </div>
          )}

          {/* Action Footer */}
          <div style={styles.footer}>
            <button type="button" onClick={onClose} style={styles.cancelBtn}>
              Cancel
            </button>
            <button
              type="submit"
              style={{
                ...styles.saveBtn,
                backgroundColor: savedSuccess ? 'var(--accent-green)' : 'var(--accent-primary)',
              }}
            >
              {savedSuccess ? (
                <>
                  <CheckCircleIcon size={13} color="#ffffff" />
                  Saved Encrypted
                </>
              ) : (
                'Save & Verify'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  backdrop: {
    position: 'fixed',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(15, 23, 42, 0.45)',
    backdropFilter: 'blur(3px)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 1000,
    padding: '16px',
    userSelect: 'none',
  },
  modal: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    boxShadow: 'var(--shadow-lg)',
    width: '100%',
    maxWidth: '360px',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '12px 14px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  title: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: 0,
  },
  closeBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 24,
    height: 24,
    borderRadius: 'var(--radius-sm)',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
  },
  body: {
    padding: '14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
  securityNotice: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    padding: '8px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary-subtle)',
    border: '1px solid rgba(37, 99, 235, 0.15)',
  },
  securityText: {
    fontSize: '10.5px',
    color: 'var(--accent-primary)',
    lineHeight: 1.35,
    fontWeight: 500,
  },
  fieldGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  label: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  configuredBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--accent-green)',
    backgroundColor: 'var(--accent-green-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
  },
  inputWrapper: {
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
  },
  input: {
    width: '100%',
    padding: '7px 32px 7px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-app)',
    fontSize: '12px',
    color: 'var(--text-primary)',
    outline: 'none',
    fontFamily: 'inherit',
  },
  eyeBtn: {
    position: 'absolute',
    right: 8,
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    padding: 0,
  },
  errorText: {
    fontSize: '10.5px',
    color: 'var(--accent-red)',
    marginTop: '2px',
  },
  endpointRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
  endpointLabel: {
    fontWeight: 600,
  },
  endpointVal: {
    fontFamily: 'Consolas, monospace',
    fontSize: '10px',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'flex-end',
    gap: '8px',
    marginTop: '6px',
  },
  cancelBtn: {
    padding: '6px 12px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    color: 'var(--text-secondary)',
    fontSize: '11.5px',
    fontWeight: 600,
    cursor: 'pointer',
  },
  saveBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '6px 14px',
    borderRadius: 'var(--radius-md)',
    border: 'none',
    color: '#ffffff',
    fontSize: '11.5px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
