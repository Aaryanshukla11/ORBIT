import React from 'react';
import { useSystem } from '../../context/SystemContext';
import { ShieldIcon, CheckIcon } from '../icons/Icons';

export const CapabilitiesList: React.FC = () => {
  const { capabilities } = useSystem();

  return (
    <div style={styles.card}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <ShieldIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>SYSTEM CAPABILITIES & SECURITY</span>
        </div>
        <span style={styles.countBadge}>{capabilities.length} Verified</span>
      </div>

      <div style={styles.list}>
        {capabilities.map((cap) => (
          <div key={cap.id} style={styles.itemRow}>
            <div style={styles.itemMain}>
              <div style={styles.itemTitleRow}>
                <span style={styles.name}>{cap.name}</span>
                <span style={styles.techBadge}>{cap.badge}</span>
              </div>
              <span style={styles.description}>{cap.description}</span>
            </div>

            <span
              style={{
                ...styles.statusTag,
                backgroundColor:
                  cap.status === 'AVAILABLE' || cap.status === 'ALLOWED'
                    ? 'var(--accent-green-subtle)'
                    : 'var(--accent-primary-subtle)',
                color:
                  cap.status === 'AVAILABLE' || cap.status === 'ALLOWED'
                    ? 'var(--accent-green)'
                    : 'var(--accent-primary)',
              }}
            >
              <CheckIcon size={10} color="currentColor" />
              {cap.status}
            </span>
          </div>
        ))}
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
    gap: '8px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '4px',
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
  countBadge: {
    fontSize: '9.5px',
    fontWeight: 600,
    color: 'var(--text-muted)',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  itemRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 0',
    borderBottom: '1px solid #f1f5f9',
    gap: '8px',
  },
  itemMain: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    overflow: 'hidden',
  },
  itemTitleRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  name: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  techBadge: {
    fontSize: '9px',
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '1px 4px',
    borderRadius: 'var(--radius-sm)',
  },
  description: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    lineHeight: 1.3,
  },
  statusTag: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '3px',
    fontSize: '9.5px',
    fontWeight: 700,
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    flexShrink: 0,
  },
};
