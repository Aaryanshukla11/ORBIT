import React from 'react';
import { GptHexagonIcon, ChevronRightIcon, CpuChipIcon, CloudIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';

interface ActiveModelCardProps {
  onNavigateToModels?: () => void;
}

export const ActiveModelCard: React.FC<ActiveModelCardProps> = ({ onNavigateToModels }) => {
  const { overview } = useSystemOverview();
  const hasModel = Boolean(overview.activeModelName);

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.labelGroup}>
          <GptHexagonIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionLabel}>ACTIVE MODEL</span>
        </div>
        {onNavigateToModels && (
          <button
            type="button"
            style={styles.switchBtn}
            onClick={onNavigateToModels}
          >
            <span>Model Manager</span>
            <ChevronRightIcon size={12} color="var(--accent-primary)" />
          </button>
        )}
      </div>

      {hasModel ? (
        <div style={styles.modelContent}>
          <div style={styles.mainRow}>
            <div style={styles.modelNameRow}>
              <span style={styles.modelName}>{overview.activeModelName}</span>
              <span style={styles.tag}>
                {overview.activeModelIsLocal ? (
                  <>
                    <CpuChipIcon size={11} color="var(--text-secondary)" />
                    <span>Local</span>
                  </>
                ) : (
                  <>
                    <CloudIcon size={11} color="var(--text-secondary)" />
                    <span>Cloud</span>
                  </>
                )}
              </span>
            </div>

            <div style={styles.healthRow}>
              <span style={styles.healthDot} />
              <span style={styles.healthText}>
                {overview.activeModelHealth || 'Ready'}
                {overview.activeModelLatencyMs != null ? ` • ${Math.round(overview.activeModelLatencyMs)}ms` : ''}
              </span>
            </div>
          </div>

          <div style={styles.metaRow}>
            <span style={styles.providerText}>Provider: {overview.activeModelProvider || 'Local Ollama'}</span>
            <span style={styles.originText}>[LIVE BACKEND]</span>
          </div>
        </div>
      ) : (
        <div style={styles.emptyContent}>
          <p style={styles.emptyText}>No AI model currently selected or active.</p>
          {onNavigateToModels && (
            <button
              type="button"
              style={styles.selectModelBtn}
              onClick={onNavigateToModels}
            >
              Select Model in Manager
            </button>
          )}
        </div>
      )}
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  labelGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  sectionLabel: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  switchBtn: {
    background: 'none',
    border: 'none',
    padding: 0,
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    cursor: 'pointer',
  },
  modelContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  mainRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  modelNameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    overflow: 'hidden',
  },
  modelName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.01em',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  tag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    padding: '1px 6px',
    borderRadius: '4px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    flexShrink: 0,
  },
  healthRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    flexShrink: 0,
  },
  healthDot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
  },
  healthText: {
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10.5px',
    color: 'var(--text-muted)',
  },
  providerText: {
    color: 'var(--text-muted)',
  },
  originText: {
    fontSize: '9px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.02em',
  },
  emptyContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  emptyText: {
    fontSize: '11.5px',
    color: 'var(--text-muted)',
    margin: 0,
  },
  selectModelBtn: {
    alignSelf: 'flex-start',
    padding: '4px 10px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    cursor: 'pointer',
  },
};
