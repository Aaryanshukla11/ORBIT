import React from 'react';
import { GptHexagonIcon, ChevronDownIcon } from '../icons/Icons';
import { useOrbit } from '../../context/OrbitContext';
import { useModelManager } from '../../context/ModelManagerContext';

interface StatusAreaProps {
  onOpenModelManager?: () => void;
  onOpenSystem?: () => void;
}

export const StatusArea: React.FC<StatusAreaProps> = ({ onOpenModelManager, onOpenSystem }) => {
  const { connectionState } = useOrbit();
  const { activeModel } = useModelManager();
  const isConnected = connectionState === 'CONNECTED';

  return (
    <div style={styles.container}>
      {/* Left Card: Connection Status */}
      <div
        style={{
          ...styles.statusCard,
          cursor: onOpenSystem ? 'pointer' : 'default',
        }}
        onClick={onOpenSystem}
        title="Open Diagnostics & System Health"
      >
        <div style={styles.iconCol}>
          <span
            style={{
              ...styles.statusDot,
              backgroundColor: isConnected ? 'var(--accent-green)' : '#f59e0b',
            }}
          />
        </div>
        <div style={styles.textCol}>
          <div style={styles.primaryLabel}>
            {isConnected ? 'Online' : 'Connecting...'}
          </div>
          <div style={styles.secondaryLabel}>
            {isConnected ? 'Gateway Connected' : 'Checking Gateway'}
          </div>
        </div>
      </div>

      {/* Right Card: Active Model Selector */}
      <div
        style={{
          ...styles.statusCard,
          cursor: onOpenModelManager ? 'pointer' : 'default',
        }}
        onClick={onOpenModelManager}
        title="Open Model Manager"
      >
        <div style={styles.iconCol}>
          <GptHexagonIcon size={22} color="var(--accent-primary)" />
        </div>
        <div style={styles.textCol}>
          <div style={styles.modelRow}>
            <span style={styles.primaryLabel}>
              {activeModel ? activeModel.name : 'Qwen2.5-Coder'}
            </span>
            <ChevronDownIcon size={13} color="var(--text-muted)" />
          </div>
          <div style={styles.secondaryLabel}>Active Model</div>
        </div>
      </div>
    </div>
  );
};


const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '12px',
    padding: '0 18px 12px 18px',
  },
  statusCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 14px',
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    boxShadow: 'var(--shadow-card)',
    userSelect: 'none',
    transition: 'all var(--transition-fast)',
  },
  iconCol: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  statusDot: {
    width: 10,
    height: 10,
    borderRadius: '50%',
    boxShadow: '0 0 6px rgba(34, 197, 94, 0.4)',
  },
  textCol: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  modelRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
  },
  primaryLabel: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  secondaryLabel: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginTop: '2px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
};

