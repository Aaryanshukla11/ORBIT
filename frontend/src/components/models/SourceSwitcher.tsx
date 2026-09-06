import React from 'react';
import { ModelSourceType } from '../../types/models';
import { HardDriveIcon, CloudIcon } from '../icons/Icons';
import { useModelManager } from '../../context/ModelManagerContext';

export const SourceSwitcher: React.FC = () => {
  const { sourceTab, setSourceTab, models, cloudProviders } = useModelManager();

  const localCount = models.filter((m) => m.type === 'local').length;
  const cloudCount = cloudProviders.length;

  return (
    <div style={styles.container}>
      <button
        type="button"
        style={{
          ...styles.tabBtn,
          ...(sourceTab === 'local' ? styles.activeTab : styles.inactiveTab),
        }}
        onClick={() => setSourceTab('local')}
      >
        <HardDriveIcon
          size={14}
          color={sourceTab === 'local' ? 'var(--accent-primary)' : 'var(--text-muted)'}
        />
        <span style={styles.tabLabel}>Local Models</span>
        <span
          style={{
            ...styles.countBadge,
            backgroundColor: sourceTab === 'local' ? 'var(--accent-primary-subtle)' : 'var(--bg-subtle)',
            color: sourceTab === 'local' ? 'var(--accent-primary)' : 'var(--text-muted)',
          }}
        >
          {localCount}
        </span>
      </button>

      <button
        type="button"
        style={{
          ...styles.tabBtn,
          ...(sourceTab === 'cloud' ? styles.activeTab : styles.inactiveTab),
        }}
        onClick={() => setSourceTab('cloud')}
      >
        <CloudIcon
          size={14}
          color={sourceTab === 'cloud' ? 'var(--accent-primary)' : 'var(--text-muted)'}
        />
        <span style={styles.tabLabel}>Cloud Models</span>
        <span
          style={{
            ...styles.countBadge,
            backgroundColor: sourceTab === 'cloud' ? 'var(--accent-primary-subtle)' : 'var(--bg-subtle)',
            color: sourceTab === 'cloud' ? 'var(--accent-primary)' : 'var(--text-muted)',
          }}
        >
          {cloudCount}
        </span>
      </button>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    padding: '3px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-subtle)',
    userSelect: 'none',
  },
  tabBtn: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding: '7px 10px',
    borderRadius: 'calc(var(--radius-md) - 2px)',
    border: 'none',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  activeTab: {
    backgroundColor: 'var(--bg-surface)',
    boxShadow: '0 1px 3px rgba(0, 0, 0, 0.06)',
    color: 'var(--text-primary)',
    fontWeight: 600,
  },
  inactiveTab: {
    backgroundColor: 'transparent',
    color: 'var(--text-secondary)',
    fontWeight: 500,
  },
  tabLabel: {
    fontSize: '11.5px',
    letterSpacing: '-0.01em',
  },
  countBadge: {
    fontSize: '10px',
    fontWeight: 700,
    padding: '1px 5px',
    borderRadius: 'var(--radius-full)',
    lineHeight: 1.1,
  },
};
