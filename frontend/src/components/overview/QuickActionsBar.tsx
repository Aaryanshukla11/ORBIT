import React from 'react';
import { ChatTabIcon, StopIcon, ModelsIcon, ActivityTabIcon } from '../icons/Icons';
import { useSystemOverview } from '../../context/SystemOverviewContext';
import { TabId } from '../navigation/HorizontalNav';

interface QuickActionsBarProps {
  onNavigateTab: (tab: TabId) => void;
}

export const QuickActionsBar: React.FC<QuickActionsBarProps> = ({ onNavigateTab }) => {
  const { overview, stopCurrentTask } = useSystemOverview();
  const isExecuting =
    overview.operationalState === 'EXECUTING' ||
    overview.operationalState === 'REPLANNING' ||
    overview.operationalState === 'PLANNING';

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <span style={styles.sectionLabel}>OPERATIONAL QUICK ACTIONS</span>
      </div>

      <div style={styles.btnGrid}>
        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => onNavigateTab('chat')}
          title="Open Chat & Task Console"
        >
          <ChatTabIcon size={14} color="var(--accent-primary)" />
          <span>New Task</span>
        </button>

        <button
          type="button"
          style={{
            ...styles.actionBtn,
            opacity: isExecuting ? 1 : 0.45,
            cursor: isExecuting ? 'pointer' : 'not-allowed',
            borderColor: isExecuting ? 'rgba(220, 38, 38, 0.3)' : 'var(--border-default)',
          }}
          disabled={!isExecuting}
          onClick={() => stopCurrentTask()}
          title={isExecuting ? 'Stop Current Task' : 'No task currently running'}
        >
          <StopIcon size={14} color={isExecuting ? '#dc2626' : 'var(--text-muted)'} />
          <span style={{ color: isExecuting ? '#dc2626' : 'var(--text-muted)' }}>Stop Task</span>
        </button>

        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => onNavigateTab('models')}
          title="Open Model Manager"
        >
          <ModelsIcon size={14} color="var(--accent-primary)" />
          <span>Models</span>
        </button>

        <button
          type="button"
          style={styles.actionBtn}
          onClick={() => onNavigateTab('activity')}
          title="Open Execution History & Activity"
        >
          <ActivityTabIcon size={14} color="var(--accent-primary)" />
          <span>Activity</span>
        </button>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '10px 14px',
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
  sectionLabel: {
    fontSize: '10px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  btnGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '6px',
  },
  actionBtn: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    padding: '8px 2px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    fontSize: '10.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
