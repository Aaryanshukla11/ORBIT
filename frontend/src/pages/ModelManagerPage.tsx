import React from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  ModelsIcon,
  RefreshIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  XCircleIcon,
} from '../components/icons/Icons';
import { orbitWS } from '../services/websocket/OrbitWebSocketClient';

export const ModelManagerPage: React.FC = () => {
  const { connectionState, activeModel } = useOrbit();
  const isConnected = connectionState === 'CONNECTED';

  const handleDiscover = () => {
    if (isConnected) {
      orbitWS.sendCommand('MODEL_DISCOVER');
    }
  };

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Model Manager & LLM Runtime</h1>
          <p style={styles.description}>
            Multi-provider model inventory discovery, live runtime switching, and latency benchmarks.
          </p>
        </div>

        <button
          className="btn btn-secondary"
          onClick={handleDiscover}
          disabled={!isConnected}
        >
          <RefreshIcon size={15} />
          <span>Discover Providers</span>
        </button>
      </div>

      {/* Active Model Hero Card */}
      <div className="card card-elevated" style={styles.activeModelCard}>
        <div style={styles.activeHeader}>
          <div style={styles.activeTitleRow}>
            <ModelsIcon size={20} color="var(--accent-primary)" />
            <h3 style={styles.activeTitle}>Active Model Runtime</h3>
          </div>
          <span className={`badge ${activeModel ? 'badge-online' : 'badge-offline'}`}>
            {activeModel ? 'Active' : 'Offline / Disconnected'}
          </span>
        </div>

        {activeModel ? (
          <div style={styles.activeDetailsGrid}>
            <div style={styles.detailItem}>
              <span style={styles.detailLabel}>Provider</span>
              <span style={styles.detailValue}>{activeModel.provider}</span>
            </div>
            <div style={styles.detailItem}>
              <span style={styles.detailLabel}>Model ID</span>
              <span style={styles.detailValueMono}>{activeModel.modelId}</span>
            </div>
            <div style={styles.detailItem}>
              <span style={styles.detailLabel}>Family</span>
              <span style={styles.detailValue}>{activeModel.family}</span>
            </div>
            <div style={styles.detailItem}>
              <span style={styles.detailLabel}>Context Window</span>
              <span style={styles.detailValue}>{activeModel.contextWindow.toLocaleString()} tokens</span>
            </div>
          </div>
        ) : (
          <div style={styles.noModelWarning}>
            <AlertTriangleIcon size={18} color="var(--status-warning)" />
            <span style={styles.noModelText}>
              {isConnected 
                ? 'Querying active model state from backend gateway...'
                : 'Connect to ORBIT WebSocket Gateway to inspect model inventory and switch active models.'}
            </span>
          </div>
        )}
      </div>

      {/* Provider Matrix Cards */}
      <div style={styles.providerSection}>
        <h3 style={styles.sectionHeading}>Supported Model Providers</h3>
        <div style={styles.providerGrid}>
          {/* Anthropic Claude */}
          <div className="card" style={styles.providerCard}>
            <div style={styles.providerHeader}>
              <div style={styles.providerName}>Anthropic Claude</div>
              <span className="badge badge-online">Supported</span>
            </div>
            <p style={styles.providerDesc}>Claude 3.5 Sonnet / Haiku / Opus via Anthropic API</p>
            <div style={styles.providerMeta}>Direct streaming, multimodal vision perception</div>
          </div>

          {/* OpenAI GPT */}
          <div className="card" style={styles.providerCard}>
            <div style={styles.providerHeader}>
              <div style={styles.providerName}>OpenAI GPT</div>
              <span className="badge badge-online">Supported</span>
            </div>
            <p style={styles.providerDesc}>GPT-4o / GPT-4o-mini / o1 reasoning models</p>
            <div style={styles.providerMeta}>Structured JSON outputs, function calling</div>
          </div>

          {/* Ollama Local */}
          <div className="card" style={styles.providerCard}>
            <div style={styles.providerHeader}>
              <div style={styles.providerName}>Ollama (Local)</div>
              <span className="badge badge-online">Supported</span>
            </div>
            <p style={styles.providerDesc}>Llama 3.3, Qwen 2.5, DeepSeek-R1 local offline</p>
            <div style={styles.providerMeta}>Zero-telemetry local air-gapped inference</div>
          </div>

          {/* vLLM Server */}
          <div className="card" style={styles.providerCard}>
            <div style={styles.providerHeader}>
              <div style={styles.providerName}>vLLM Engine</div>
              <span className="badge badge-online">Supported</span>
            </div>
            <p style={styles.providerDesc}>High-throughput self-hosted inference server</p>
            <div style={styles.providerMeta}>PagedAttention, tensor parallel execution</div>
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
  activeModelCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  activeHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingBottom: 'var(--space-3)',
    borderBottom: '1px solid var(--border-subtle)',
  },
  activeTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  activeTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  activeDetailsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: 'var(--space-4)',
  },
  detailItem: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  detailLabel: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  detailValue: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  detailValueMono: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    fontFamily: 'var(--font-mono)',
  },
  noModelWarning: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
    padding: 'var(--space-3)',
    backgroundColor: 'var(--bg-input)',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
  },
  noModelText: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-secondary)',
  },
  providerSection: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
  },
  sectionHeading: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  providerGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: 'var(--space-4)',
  },
  providerCard: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-2)',
  },
  providerHeader: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  providerName: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  providerDesc: {
    fontSize: '12.5px',
    color: 'var(--text-secondary)',
  },
  providerMeta: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginTop: '4px',
  },
};
