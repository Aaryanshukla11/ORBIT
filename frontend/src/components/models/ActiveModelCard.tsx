import React from 'react';
import { GptHexagonIcon, CpuChipIcon, CheckCircleIcon, SparklesIcon } from '../icons/Icons';
import { useModelManager } from '../../context/ModelManagerContext';

export const ActiveModelCard: React.FC = () => {
  const { activeModel, switchingModelId } = useModelManager();

  if (!activeModel) return null;

  return (
    <div style={styles.card}>
      <div style={styles.topRow}>
        <div style={styles.badgeWrap}>
          <span style={styles.activeDot} />
          <span style={styles.sectionBadge}>ACTIVE MODEL</span>
        </div>
        <div style={styles.providerTag}>
          <CpuChipIcon size={12} color="var(--accent-primary)" />
          <span>{activeModel.provider}</span>
        </div>
      </div>

      <div style={styles.mainInfo}>
        <div style={styles.iconWrap}>
          <GptHexagonIcon size={26} color="var(--accent-primary)" />
        </div>
        <div style={styles.titleCol}>
          <div style={styles.modelName}>{activeModel.name}</div>
          <div style={styles.familyText}>
            {activeModel.family} • {activeModel.type === 'local' ? 'Offline Local Runtime' : 'Cloud Endpoint'}
          </div>
        </div>
      </div>

      {/* Capabilities Badges */}
      <div style={styles.capsRow}>
        {activeModel.capabilities.map((cap) => (
          <span key={cap} style={styles.capPill}>
            {cap === 'Code' && <span style={styles.capDot} />}
            {cap}
          </span>
        ))}
        {activeModel.contextWindow && (
          <span style={styles.contextPill}>
            {(activeModel.contextWindow / 1024).toFixed(0)}k Ctx
          </span>
        )}
      </div>

      {/* Metric specs */}
      <div style={styles.specsRow}>
        {activeModel.size && (
          <div style={styles.specItem}>
            <span style={styles.specLabel}>Disk Size</span>
            <span style={styles.specValue}>{activeModel.size}</span>
          </div>
        )}
        {activeModel.hardwareReq && (
          <div style={styles.specItem}>
            <span style={styles.specLabel}>Hardware Req</span>
            <span style={styles.specValue}>{activeModel.hardwareReq}</span>
          </div>
        )}
        <div style={styles.specItem}>
          <span style={styles.specLabel}>Status</span>
          <span style={{ ...styles.specValue, color: 'var(--accent-green)', fontWeight: 600 }}>
            <CheckCircleIcon size={12} color="var(--accent-green)" /> Ready
          </span>
        </div>
      </div>

      {switchingModelId && (
        <div style={styles.switchingBanner}>
          <span style={styles.spinner} />
          <span>Activating new model...</span>
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
    padding: '14px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    userSelect: 'none',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  badgeWrap: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
  },
  activeDot: {
    width: 7,
    height: 7,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-green)',
    boxShadow: '0 0 6px rgba(34, 197, 94, 0.4)',
  },
  sectionBadge: {
    fontSize: '10px',
    fontWeight: 700,
    letterSpacing: '0.06em',
    color: 'var(--accent-green)',
  },
  providerTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 7px',
    borderRadius: 'var(--radius-sm)',
  },
  mainInfo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  iconWrap: {
    width: 36,
    height: 36,
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  titleCol: {
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
  },
  modelName: {
    fontSize: '15px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    letterSpacing: '-0.01em',
    lineHeight: 1.2,
  },
  familyText: {
    fontSize: '11px',
    color: 'var(--text-muted)',
    marginTop: '2px',
  },
  capsRow: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '5px',
  },
  capPill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    backgroundColor: 'var(--bg-subtle)',
    border: '1px solid var(--border-subtle)',
    padding: '2px 7px',
    borderRadius: 'var(--radius-full)',
  },
  capDot: {
    width: 4,
    height: 4,
    borderRadius: '50%',
    backgroundColor: 'var(--accent-primary)',
  },
  contextPill: {
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-primary-subtle)',
    padding: '2px 7px',
    borderRadius: 'var(--radius-full)',
  },
  specsRow: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '6px',
    paddingTop: '8px',
    borderTop: '1px solid var(--border-subtle)',
  },
  specItem: {
    display: 'flex',
    flexDirection: 'column',
  },
  specLabel: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
    letterSpacing: '0.04em',
  },
  specValue: {
    fontSize: '11.5px',
    fontWeight: 500,
    color: 'var(--text-primary)',
    marginTop: '2px',
    display: 'flex',
    alignItems: 'center',
    gap: '3px',
  },
  switchingBanner: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 10px',
    borderRadius: 'var(--radius-sm)',
    backgroundColor: 'var(--accent-primary-subtle)',
    color: 'var(--accent-primary)',
    fontSize: '11px',
    fontWeight: 600,
  },
  spinner: {
    width: 10,
    height: 10,
    border: '2px solid var(--accent-primary)',
    borderTopColor: 'transparent',
    borderRadius: '50%',
    display: 'inline-block',
  },
};
