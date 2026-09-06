import React, { useState } from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  SettingsIcon,
  PlugIcon,
  UnplugIcon,
  RefreshIcon,
  CheckCircleIcon,
} from '../components/icons/Icons';
import { NAVIGATION_ITEMS } from '../constants/navigation';

export const SettingsPage: React.FC = () => {
  const { gatewayUrl, setGatewayUrl, connectionState, connect, disconnect } = useOrbit();
  const [inputUrl, setInputUrl] = useState(gatewayUrl);
  const [saveSuccess, setSaveSuccess] = useState(false);

  const isConnected = connectionState === 'CONNECTED';

  const handleSaveAndConnect = (e: React.FormEvent) => {
    e.preventDefault();
    setGatewayUrl(inputUrl);
    connect(inputUrl);
    setSaveSuccess(true);
    setTimeout(() => setSaveSuccess(false), 2000);
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Settings & Configuration</h1>
          <p style={styles.description}>
            Configure WebSocket gateway endpoints, connection parameters, and desktop environment options.
          </p>
        </div>
      </div>

      {/* Settings Grid */}
      <div style={styles.grid}>
        {/* Gateway Connection Settings */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <PlugIcon size={18} color="var(--accent-primary)" />
              <h3 style={styles.cardTitle}>Gateway Endpoint</h3>
            </div>
            <span className={`badge ${isConnected ? 'badge-online' : 'badge-error'}`}>
              {isConnected ? 'Connected' : 'Disconnected'}
            </span>
          </div>

          <form onSubmit={handleSaveAndConnect} style={styles.form}>
            <div style={styles.inputGroup}>
              <label style={styles.label}>WebSocket URL</label>
              <input
                type="text"
                className="input-text"
                value={inputUrl}
                onChange={(e) => setInputUrl(e.target.value)}
                placeholder="ws://127.0.0.1:8765/ws"
                style={styles.input}
              />
              <span style={styles.helpText}>
                Default ORBIT FastAPI WebSocket gateway URL (typically <code>ws://127.0.0.1:8765/ws</code>).
              </span>
            </div>

            <div style={styles.buttonRow}>
              <button type="submit" className="btn btn-primary">
                <RefreshIcon size={14} />
                <span>Save & Connect</span>
              </button>

              {isConnected ? (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => disconnect()}
                >
                  <UnplugIcon size={14} />
                  <span>Disconnect</span>
                </button>
              ) : (
                <button
                  type="button"
                  className="btn btn-secondary"
                  onClick={() => connect(inputUrl)}
                >
                  <PlugIcon size={14} />
                  <span>Reconnect</span>
                </button>
              )}

              {saveSuccess && (
                <span style={styles.saveBadge}>
                  <CheckCircleIcon size={14} color="var(--status-online)" />
                  Settings saved
                </span>
              )}
            </div>
          </form>
        </div>

        {/* Keyboard Shortcuts Reference */}
        <div className="card" style={styles.card}>
          <div style={styles.cardHeader}>
            <div style={styles.cardTitleRow}>
              <SettingsIcon size={18} color="var(--accent-cyan)" />
              <h3 style={styles.cardTitle}>Desktop Keyboard Shortcuts</h3>
            </div>
            <span className="badge badge-online">Global</span>
          </div>

          <div style={styles.shortcutsList}>
            {NAVIGATION_ITEMS.map((item) => (
              <div key={item.id} style={styles.shortcutRow}>
                <span style={styles.shortcutLabel}>{item.label}</span>
                <kbd style={styles.kbd}>{item.shortcut}</kbd>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-6)',
    maxWidth: 1400,
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 'var(--font-size-2xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-1)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: 'var(--space-5)',
  },
  card: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  cardHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 'var(--space-3)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  cardTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  cardTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  label: {
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  input: {
    fontFamily: 'var(--font-mono)',
  },
  helpText: {
    fontSize: '11.5px',
    color: 'var(--text-muted)',
  },
  buttonRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    marginTop: 'var(--space-2)',
  },
  saveBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    fontSize: 'var(--font-size-xs)',
    color: 'var(--status-online)',
    fontWeight: 500,
  },
  shortcutsList: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  shortcutRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 'var(--space-2) 0',
    borderBottom: '1px solid var(--border-subtle)',
  },
  shortcutLabel: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-secondary)',
  },
  kbd: {
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-xs)',
    padding: '2px 8px',
    fontSize: '11px',
    color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)',
    fontWeight: 600,
  },
};
