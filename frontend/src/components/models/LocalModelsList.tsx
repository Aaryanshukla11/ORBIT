import React from 'react';
import { ModelItem } from '../../types/models';
import { useModelManager, isSameModel } from '../../context/ModelManagerContext';
import { CheckIcon, CpuChipIcon, AlertTriangleIcon } from '../icons/Icons';

export const LocalModelsList: React.FC = () => {
  const { models, activeModelId, switchingModelId, switchingError, switchModel } = useModelManager();

  const localModels = models.filter((m) => m.type === 'local');

  return (
    <div style={styles.container}>
      {switchingError && (
        <div style={styles.errorBanner}>
          <AlertTriangleIcon size={14} color="var(--accent-red)" />
          <span style={styles.errorText}>{switchingError}</span>
        </div>
      )}

      <div style={styles.list}>
        {localModels.map((model) => {
          const isActive = isSameModel(model.id, activeModelId);
          const isSwitchingThis = isSameModel(model.id, switchingModelId);

          return (
            <div
              key={model.id}
              style={{
                ...styles.modelCard,
                borderColor: isActive ? 'var(--accent-primary)' : 'var(--border-subtle)',
                backgroundColor: isActive ? '#f8faff' : 'var(--bg-surface)',
              }}
            >
              {/* Card Header Row */}
              <div style={styles.cardHeader}>
                <div style={styles.titleArea}>
                  <span style={styles.modelName}>{model.name}</span>
                  <span style={styles.familyBadge}>{model.family}</span>
                </div>

                {/* Action button / Status indicator */}
                {isActive ? (
                  <span style={styles.activePill}>
                    <CheckIcon size={12} color="var(--accent-green)" />
                    Active
                  </span>
                ) : (
                  <button
                    type="button"
                    style={{
                      ...styles.switchBtn,
                      opacity: switchingModelId ? 0.6 : 1,
                      cursor: switchingModelId ? 'not-allowed' : 'pointer',
                    }}
                    disabled={Boolean(switchingModelId)}
                    onClick={() => switchModel(model.id)}
                  >
                    {isSwitchingThis ? (
                      <>
                        <span style={styles.btnSpinner} />
                        Activating...
                      </>
                    ) : (
                      'Switch'
                    )}
                  </button>
                )}
              </div>

              {/* Description if present */}
              {model.description && (
                <div style={styles.description}>{model.description}</div>
              )}

              {/* Specs & Capabilities */}
              <div style={styles.metaRow}>
                {model.size && (
                  <span style={styles.metaBadge}>{model.size}</span>
                )}
                {model.contextWindow && (
                  <span style={styles.metaBadge}>
                    {(model.contextWindow / 1024).toFixed(0)}k ctx
                  </span>
                )}
                {model.capabilities.map((cap) => (
                  <span key={cap} style={styles.capBadge}>
                    {cap}
                  </span>
                ))}
              </div>

              {/* Hardware requirement strip */}
              {model.hardwareReq && (
                <div style={styles.hardwareStrip}>
                  <CpuChipIcon size={11} color="var(--text-muted)" />
                  <span style={styles.hardwareText}>Requires: {model.hardwareReq}</span>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
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
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  modelCard: {
    padding: '11px 12px',
    borderRadius: 'var(--radius-lg)',
    border: '1px solid',
    display: 'flex',
    flexDirection: 'column',
    gap: '7px',
    boxShadow: 'var(--shadow-card)',
    transition: 'all var(--transition-fast)',
    userSelect: 'none',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: '8px',
  },
  titleArea: {
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
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
  familyBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
  },
  activePill: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '4px',
    padding: '3px 8px',
    borderRadius: 'var(--radius-full)',
    backgroundColor: 'var(--accent-green-subtle)',
    border: '1px solid rgba(34, 197, 94, 0.3)',
    color: 'var(--accent-green)',
    fontSize: '10.5px',
    fontWeight: 700,
    flexShrink: 0,
  },
  switchBtn: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '5px',
    padding: '4px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary)',
    border: 'none',
    color: '#ffffff',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    flexShrink: 0,
    transition: 'all var(--transition-fast)',
  },
  btnSpinner: {
    width: 9,
    height: 9,
    border: '1.5px solid #ffffff',
    borderTopColor: 'transparent',
    borderRadius: '50%',
    display: 'inline-block',
  },
  description: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
    lineHeight: 1.35,
  },
  metaRow: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '4px',
  },
  metaBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-secondary)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
  },
  capBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-primary-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
  },
  hardwareStrip: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    fontSize: '10px',
    color: 'var(--text-muted)',
    marginTop: '2px',
  },
  hardwareText: {
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
};
