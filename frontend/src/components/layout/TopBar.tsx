import React from 'react';
import { useOrbit } from '../../context/OrbitContext';
import { NAVIGATION_ITEMS } from '../../constants/navigation';
import {
  AlertTriangleIcon,
  PlugIcon,
  UnplugIcon,
  RefreshIcon,
  ModelsIcon,
  ShieldIcon,
  ChevronRightIcon,
} from '../icons/Icons';

export const TopBar: React.FC = () => {
  const {
    activePage,
    connectionState,
    activeModel,
    connect,
    disconnect,
    triggerTakeover,
  } = useOrbit();

  const currentItem = NAVIGATION_ITEMS.find((item) => item.id === activePage) || NAVIGATION_ITEMS[0];
  const isConnected = connectionState === 'CONNECTED';

  return (
    <header style={styles.topbar}>
      {/* Breadcrumb / Page Title */}
      <div style={styles.leftSection}>
        <span style={styles.breadcrumbRoot}>ORBIT</span>
        <ChevronRightIcon size={14} color="var(--text-muted)" />
        <span style={styles.currentPageLabel}>{currentItem.label}</span>
      </div>

      {/* Center / Right Telemetry & Controls */}
      <div style={styles.rightSection}>
        {/* Active AI Model Indicator */}
        <div style={styles.indicatorPill}>
          <ModelsIcon size={15} color={activeModel ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <span style={styles.pillLabel}>Model:</span>
          <span style={{
            ...styles.pillValue,
            color: activeModel ? 'var(--text-primary)' : 'var(--text-muted)',
          }}>
            {activeModel ? `${activeModel.modelId}` : 'Unavailable (Disconnected)'}
          </span>
        </div>

        {/* WebSocket Connection Status Pill */}
        <div style={{
          ...styles.connectionPill,
          borderColor:
            isConnected
              ? 'var(--status-online-border)'
              : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
              ? 'var(--status-warning-border)'
              : 'var(--status-error-border)',
          backgroundColor:
            isConnected
              ? 'var(--status-online-subtle)'
              : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
              ? 'var(--status-warning-subtle)'
              : 'var(--status-error-subtle)',
        }}>
          <span
            style={{
              ...styles.statusIndicatorDot,
              backgroundColor:
                isConnected
                  ? 'var(--status-online)'
                  : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
                  ? 'var(--status-warning)'
                  : 'var(--status-error)',
            }}
          />
          <span style={{
            ...styles.connectionText,
            color:
              isConnected
                ? 'var(--status-online)'
                : connectionState === 'CONNECTING' || connectionState === 'RECONNECTING'
                ? 'var(--status-warning)'
                : 'var(--status-error)',
          }}>
            {connectionState === 'CONNECTED'
              ? 'Gateway Connected'
              : connectionState === 'CONNECTING'
              ? 'Connecting...'
              : connectionState === 'RECONNECTING'
              ? 'Reconnecting...'
              : 'Gateway Disconnected'}
          </span>

          {isConnected ? (
            <button
              onClick={() => disconnect()}
              style={styles.pillActionBtn}
              title="Disconnect WebSocket"
            >
              <UnplugIcon size={13} />
            </button>
          ) : (
            <button
              onClick={() => connect()}
              style={styles.pillActionBtn}
              title="Connect to Gateway"
            >
              <RefreshIcon size={13} />
            </button>
          )}
        </div>

        {/* Human Takeover Quick Trigger Button */}
        <button
          onClick={() => triggerTakeover()}
          style={styles.takeoverBtn}
          title="Emergency Human Takeover Preemption"
        >
          <AlertTriangleIcon size={14} color="var(--status-warning)" />
          <span>Takeover</span>
        </button>
      </div>
    </header>
  );
};

const styles: Record<string, React.CSSProperties> = {
  topbar: {
    height: 'var(--topbar-height)',
    minHeight: 'var(--topbar-height)',
    backgroundColor: 'var(--bg-surface)',
    borderBottom: '1px solid var(--border-subtle)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 var(--space-5)',
    userSelect: 'none',
    zIndex: 9,
  },
  leftSection: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-2)',
  },
  breadcrumbRoot: {
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    color: 'var(--text-muted)',
    letterSpacing: '0.05em',
  },
  currentPageLabel: {
    fontSize: 'var(--font-size-sm)',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
  rightSection: {
    display: 'flex',
    alignItems: 'center',
    gap: 'var(--space-3)',
  },
  indicatorPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    backgroundColor: 'var(--bg-surface-elevated)',
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    fontSize: 'var(--font-size-xs)',
  },
  pillLabel: {
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  pillValue: {
    fontFamily: 'var(--font-mono)',
    fontWeight: 500,
  },
  connectionPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid',
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
  },
  statusIndicatorDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
  },
  connectionText: {
    fontSize: 'var(--font-size-xs)',
    letterSpacing: '0.02em',
  },
  pillActionBtn: {
    background: 'transparent',
    border: 'none',
    color: 'currentColor',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    padding: '1px',
    marginLeft: '2px',
    opacity: 0.8,
  },
  takeoverBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    backgroundColor: 'var(--status-warning-subtle)',
    border: '1px solid var(--status-warning-border)',
    borderRadius: 'var(--radius-md)',
    color: 'var(--status-warning)',
    fontSize: 'var(--font-size-xs)',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'background var(--transition-fast)',
  },
};
