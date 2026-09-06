import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { ExpandScanIcon, TerminalIcon, CheckCircleIcon } from '../icons/Icons';

export const WorkspaceContextCard: React.FC = () => {
  const { workspaceContext } = useSystem();

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <div style={styles.titleWrap}>
          <ExpandScanIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>DESKTOP AWARENESS & WORKSPACE</span>
        </div>
        <span style={styles.pipelineBadge}>
          <CheckCircleIcon size={11} color="var(--accent-green)" />
          Vision Grounded
        </span>
      </div>

      <div style={styles.grid}>
        {/* Focused Window */}
        <div style={styles.gridItemFull}>
          <span style={styles.itemLabel}>Focused Application</span>
          <div style={styles.focusedBox}>
            <TerminalIcon size={13} color="var(--accent-primary)" />
            <span style={styles.focusedTitle}>{workspaceContext.focusedWindow}</span>
            <span style={styles.hwndBadge}>{workspaceContext.focusedHwnd}</span>
          </div>
        </div>

        {/* Active Display */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Active Display</span>
          <span style={styles.itemValue}>{workspaceContext.activeDisplay}</span>
        </div>

        {/* Dock Reservation */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Dock Allocation</span>
          <span style={styles.itemValue}>
            {workspaceContext.dockEdge} Edge ({workspaceContext.dockWidthPx}px)
          </span>
        </div>

        {/* Usable Workspace Canvas */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Usable OS Canvas</span>
          <span style={styles.itemValue}>{workspaceContext.usableCanvas}</span>
        </div>

        {/* Vision Resolution */}
        <div style={styles.gridItem}>
          <span style={styles.itemLabel}>Observation Pipeline</span>
          <span style={{ ...styles.itemValue, color: 'var(--accent-green)' }}>
            {workspaceContext.observationPipeline} ({workspaceContext.visionResolution})
          </span>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    userSelect: 'none',
  },
  cardHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '6px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  cardTitle: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  pipelineBadge: {
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
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(2, 1fr)',
    gap: '8px 10px',
  },
  gridItemFull: {
    gridColumn: '1 / -1',
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  focusedBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '6px 8px',
  },
  focusedTitle: {
    flex: 1,
    fontSize: '12px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  hwndBadge: {
    fontSize: '9.5px',
    fontFamily: 'Consolas, monospace',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 4px',
    borderRadius: 'var(--radius-sm)',
  },
  gridItem: {
    display: 'flex',
    flexDirection: 'column',
  },
  itemLabel: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    textTransform: 'uppercase',
  },
  itemValue: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    marginTop: '2px',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
  },
};
