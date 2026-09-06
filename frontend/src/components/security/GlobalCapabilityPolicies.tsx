import React from 'react';
import { useSecurity } from '../../context/SecurityContext';
import { PolicyLevel } from '../../types/security';
import { ShieldIcon } from '../icons/Icons';

export const GlobalCapabilityPolicies: React.FC = () => {
  const { capabilityPolicies, updateCapabilityPolicy, updatingPolicyId } = useSecurity();

  const handlePolicyChange = (id: string, level: PolicyLevel) => {
    updateCapabilityPolicy(id, level);
  };

  return (
    <div style={styles.card}>
      <div style={styles.cardHeader}>
        <div style={styles.titleWrap}>
          <ShieldIcon size={14} color="var(--accent-primary)" />
          <span style={styles.cardTitle}>ORBIT ACCESS CONTROLS</span>
        </div>
        <span style={styles.policySubtext}>Global System Policies</span>
      </div>

      <div style={styles.policyList}>
        {capabilityPolicies.map((policy) => {
          const isUpdating = updatingPolicyId === policy.id;

          return (
            <div key={policy.id} style={styles.policyRow}>
              <div style={styles.labelCol}>
                <span style={styles.policyName}>{policy.name}</span>
                <span style={styles.policyDesc}>{policy.description}</span>
              </div>

              {/* Segmented Allow | Ask | Deny Control */}
              <div style={styles.segmentedControl}>
                {(['ALLOW', 'ASK', 'DENY'] as const).map((lvl) => {
                  const isSelected = policy.level === lvl;

                  let activeBg = 'var(--bg-surface)';
                  let activeColor = 'var(--text-primary)';
                  if (isSelected) {
                    if (lvl === 'ALLOW') {
                      activeBg = 'var(--accent-green-subtle)';
                      activeColor = 'var(--accent-green)';
                    } else if (lvl === 'ASK') {
                      activeBg = 'var(--accent-primary-subtle)';
                      activeColor = 'var(--accent-primary)';
                    } else if (lvl === 'DENY') {
                      activeBg = 'var(--accent-red-subtle)';
                      activeColor = 'var(--accent-red)';
                    }
                  }

                  return (
                    <button
                      key={lvl}
                      type="button"
                      disabled={isUpdating}
                      style={{
                        ...styles.segmentBtn,
                        backgroundColor: isSelected ? activeBg : 'transparent',
                        color: isSelected ? activeColor : 'var(--text-muted)',
                        fontWeight: isSelected ? 700 : 500,
                      }}
                      onClick={() => handlePolicyChange(policy.id, lvl)}
                      title={`Set ${policy.name} to ${lvl}`}
                    >
                      {lvl.charAt(0) + lvl.slice(1).toLowerCase()}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
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
  cardHeader: {
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
  policySubtext: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  policyList: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  policyRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 0',
    borderBottom: '1px solid #f1f5f9',
    gap: '8px',
  },
  labelCol: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
    overflow: 'hidden',
    flex: 1,
  },
  policyName: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  policyDesc: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    lineHeight: 1.3,
  },
  segmentedControl: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '2px',
    border: '1px solid var(--border-subtle)',
    flexShrink: 0,
  },
  segmentBtn: {
    padding: '3px 7px',
    borderRadius: 'calc(var(--radius-md) - 2px)',
    border: 'none',
    fontSize: '10px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
};
