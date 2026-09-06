import React from 'react';
import { ArrowLeftIcon, RefreshIcon } from '../icons/Icons';
import { useModelManager } from '../../context/ModelManagerContext';

interface ModelHeaderProps {
  onBack?: () => void;
}

export const ModelHeader: React.FC<ModelHeaderProps> = ({ onBack }) => {
  const { systemStatus, discoverModels, switchingModelId } = useModelManager();

  return (
    <div style={styles.header}>
      <div style={styles.leftGroup}>
        {onBack && (
          <button
            type="button"
            onClick={onBack}
            style={styles.backBtn}
            title="Return to Chat"
          >
            <ArrowLeftIcon size={16} color="var(--text-secondary)" />
          </button>
        )}
        <div style={styles.titleWrap}>
          <h2 style={styles.title}>Model Manager</h2>
          <span style={styles.subtitle}>AI Runtime & Inventory</span>
        </div>
      </div>

      <div style={styles.rightGroup}>
        <button
          type="button"
          onClick={discoverModels}
          style={styles.refreshBtn}
          title="Scan Local & Cloud Models"
        >
          <RefreshIcon size={14} color="var(--text-muted)" />
        </button>

        <span
          style={{
            ...styles.statusBadge,
            backgroundColor: switchingModelId ? 'var(--accent-primary-subtle)' : 'var(--accent-green-subtle)',
            color: switchingModelId ? 'var(--accent-primary)' : 'var(--accent-green)',
            borderColor: switchingModelId ? 'var(--border-tab-active)' : 'rgba(34, 197, 94, 0.3)',
          }}
        >
          <span
            style={{
              ...styles.statusDot,
              backgroundColor: switchingModelId ? 'var(--accent-primary)' : 'var(--accent-green)',
            }}
          />
          {switchingModelId ? 'Switching' : systemStatus.runtimeState}
        </span>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '4px 0 12px 0',
    borderBottom: '1px solid var(--border-subtle)',
    userSelect: 'none',
  },
  leftGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  backBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 28,
    height: 28,
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-surface)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  titleWrap: {
    display: 'flex',
    flexDirection: 'column',
  },
  title: {
    fontSize: '14px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
  rightGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  refreshBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 26,
    height: 26,
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--bg-surface)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  statusBadge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '2px 8px',
    borderRadius: 'var(--radius-full)',
    border: '1px solid',
    fontSize: '10.5px',
    fontWeight: 700,
    letterSpacing: '0.03em',
  },
  statusDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
};
