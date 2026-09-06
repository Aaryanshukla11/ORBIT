import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { CheckIcon, SystemIcon } from '../icons/Icons';

export const DisplayOverview: React.FC = () => {
  const { displays, selectedDisplayId, setSelectedDisplayId } = useSystem();

  return (
    <div style={styles.container}>
      <div style={styles.sectionHead}>
        <div style={styles.titleWrap}>
          <SystemIcon size={14} color="var(--accent-primary)" />
          <span style={styles.sectionTitle}>CONNECTED DISPLAYS</span>
        </div>
        <span style={styles.monitorCount}>
          {displays.length} {displays.length === 1 ? 'Monitor' : 'Monitors'} Detected
        </span>
      </div>

      <div style={styles.displayList}>
        {displays.map((disp) => {
          const isSelected = selectedDisplayId === disp.id;

          return (
            <div
              key={disp.id}
              style={{
                ...styles.card,
                borderColor: isSelected ? 'var(--accent-primary)' : 'var(--border-default)',
                backgroundColor: isSelected ? '#f8faff' : 'var(--bg-surface)',
              }}
              onClick={() => setSelectedDisplayId(disp.id)}
            >
              {/* Top Row: Name & Badges */}
              <div style={styles.cardHeader}>
                <div style={styles.nameRow}>
                  <span style={styles.displayName}>{disp.name}</span>
                  {disp.isPrimary && <span style={styles.primaryBadge}>Primary</span>}
                </div>
                <span style={styles.activeTag}>
                  <CheckIcon size={11} color="var(--accent-green)" />
                  Active
                </span>
              </div>

              {/* Proportional Mini Preview Graphic */}
              <div style={styles.miniDisplayPreview}>
                <div style={styles.miniScreenArea}>
                  <div style={styles.desktopCanvasArea}>
                    <span style={styles.canvasText}>75% Windows Desktop</span>
                  </div>
                  <div style={styles.orbitDockArea}>
                    <span style={styles.orbitDockText}>ORBIT (25%)</span>
                  </div>
                </div>
              </div>

              {/* Metrics Grid */}
              <div style={styles.metricsGrid}>
                <div style={styles.metricItem}>
                  <span style={styles.metricLabel}>Resolution</span>
                  <span style={styles.metricValue}>{disp.resolution}</span>
                </div>
                <div style={styles.metricItem}>
                  <span style={styles.metricLabel}>DPI Scale</span>
                  <span style={styles.metricValue}>{disp.scalePercent}%</span>
                </div>
                <div style={styles.metricItem}>
                  <span style={styles.metricLabel}>Work Area</span>
                  <span style={styles.metricValue}>
                    {disp.workArea.width} × {disp.workArea.height}
                  </span>
                </div>
              </div>
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
  sectionHead: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '2px',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  sectionTitle: {
    fontSize: '10.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  monitorCount: {
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--accent-primary)',
  },
  displayList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  card: {
    border: '1px solid',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
    userSelect: 'none',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  nameRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  displayName: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  primaryBadge: {
    fontSize: '9.5px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    backgroundColor: 'var(--accent-primary-subtle)',
    padding: '1px 5px',
    borderRadius: 'var(--radius-sm)',
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
  miniDisplayPreview: {
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '4px',
    height: '42px',
    display: 'flex',
  },
  miniScreenArea: {
    flex: 1,
    display: 'flex',
    borderRadius: 'var(--radius-sm)',
    overflow: 'hidden',
    border: '1px dashed var(--border-default)',
  },
  desktopCanvasArea: {
    flex: 3,
    backgroundColor: '#ffffff',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRight: '1px solid var(--border-subtle)',
  },
  canvasText: {
    fontSize: '9px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    letterSpacing: '-0.01em',
  },
  orbitDockArea: {
    flex: 1,
    backgroundColor: 'var(--accent-primary-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  orbitDockText: {
    fontSize: '8.5px',
    fontWeight: 700,
    color: 'var(--accent-primary)',
    whiteSpace: 'nowrap',
  },
  metricsGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(3, 1fr)',
    gap: '6px',
    paddingTop: '6px',
    borderTop: '1px solid var(--border-subtle)',
  },
  metricItem: {
    display: 'flex',
    flexDirection: 'column',
  },
  metricLabel: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
  },
  metricValue: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginTop: '2px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
};
