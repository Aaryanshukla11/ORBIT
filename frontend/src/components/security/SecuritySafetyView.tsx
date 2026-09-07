import React from 'react';
import { SecurityHeader } from './SecurityHeader';
import { SafetyStatusCard } from './SafetyStatusCard';
import { GlobalCapabilityPolicies } from './GlobalCapabilityPolicies';
import { AppAccessControlList } from './AppAccessControlList';
import { HumanTakeoverCard } from './HumanTakeoverCard';
import { SecurityAuditTrail } from './SecurityAuditTrail';

export const SecuritySafetyView: React.FC = () => {
  return (
    <div style={styles.container}>
      {/* 1. Header */}
      <div style={styles.headerWrapper}>
        <SecurityHeader />
      </div>

      {/* 2. Scrollable Content Body */}
      <div style={styles.scrollArea}>
        {/* Safety & Permissions Guardrails Summary */}
        <SafetyStatusCard />

        {/* Global Capability Policies */}
        <GlobalCapabilityPolicies />

        {/* Application-Specific Access Policies & Discovered Software */}
        <AppAccessControlList />

        {/* Human Takeover & Fail-Safe Guard */}
        <HumanTakeoverCard />

        {/* Security Audit Trail */}
        <SecurityAuditTrail />
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  headerWrapper: {
    padding: '0 18px',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 18px 24px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
};
