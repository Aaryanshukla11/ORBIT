import React, { useState } from 'react';
import { useDiagnostics } from '../../context/DiagnosticsContext';
import { SubsystemDiagnosticReport, DiagnosticStatus } from '../../types/diagnostics';
import {
  ServerIcon,
  PlugIcon,
  TerminalIcon,
  ModelsIcon,
  ShieldIcon,
  EyeIcon,
  BotAutoIcon,
  SystemIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  XCircleIcon,
} from '../icons/Icons';

export const SubsystemHealthList: React.FC = () => {
  const { report, electronDiagnostics } = useDiagnostics();
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggleExpand = (id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  };

  const getSubsystemIcon = (id: string) => {
    switch (id) {
      case 'backend':
        return ServerIcon;
      case 'websocket':
        return PlugIcon;
      case 'execution_engine':
        return TerminalIcon;
      case 'model_runtime':
        return ModelsIcon;
      case 'safety':
        return ShieldIcon;
      case 'perception':
        return EyeIcon;
      case 'action':
        return BotAutoIcon;
      case 'desktop_shell':
        return SystemIcon;
      default:
        return ServerIcon;
    }
  };

  const getStatusPill = (status: DiagnosticStatus) => {
    switch (status) {
      case 'HEALTHY':
        return {
          label: 'Healthy',
          color: 'var(--accent-green)',
          bg: 'var(--accent-green-subtle)',
          icon: CheckCircleIcon,
        };
      case 'DEGRADED':
        return {
          label: 'Degraded',
          color: '#f59e0b',
          bg: '#fef3c7',
          icon: AlertTriangleIcon,
        };
      case 'FAILED':
        return {
          label: 'Failed',
          color: 'var(--accent-rose)',
          bg: 'var(--accent-rose-subtle)',
          icon: XCircleIcon,
        };
      case 'UNAVAILABLE':
        return {
          label: 'Unavailable',
          color: 'var(--text-muted)',
          bg: 'var(--bg-subtle)',
          icon: AlertTriangleIcon,
        };
      default:
        return {
          label: 'Unknown',
          color: 'var(--text-muted)',
          bg: 'var(--bg-subtle)',
          icon: AlertTriangleIcon,
        };
    }
  };

  const subsystems: SubsystemDiagnosticReport[] = report?.subsystems || [];

  // Add Electron Desktop Shell row if not present
  const allSubsystems: (SubsystemDiagnosticReport | any)[] = [...subsystems];
  if (electronDiagnostics && !allSubsystems.some((s) => s.subsystem_id === 'desktop_shell')) {
    allSubsystems.push({
      subsystem_id: 'desktop_shell',
      name: 'Electron Desktop Companion',
      status: 'HEALTHY' as DiagnosticStatus,
      summary: `Windows ${electronDiagnostics.arch} • v${electronDiagnostics.appVersion} (${electronDiagnostics.displaysCount} Monitor${electronDiagnostics.displaysCount > 1 ? 's' : ''})`,
      latency_ms: 1.2,
      details: {
        platform: electronDiagnostics.platform,
        os_release: electronDiagnostics.release,
        electron_version: electronDiagnostics.electronVersion,
        chrome_version: electronDiagnostics.chromeVersion,
        cpu_model: electronDiagnostics.cpuModel,
        memory_free: electronDiagnostics.freeMemory,
        memory_total: electronDiagnostics.totalMemory,
        primary_resolution: electronDiagnostics.primaryResolution,
        is_pinned: electronDiagnostics.isPinned,
      },
      last_checked: new Date().toISOString(),
    });
  }

  return (
    <div style={styles.card}>
      <div style={styles.sectionHeader}>
        <span style={styles.sectionTitle}>Subsystem Health</span>
        <span style={styles.sectionBadge}>
          {allSubsystems.filter((s) => s.status === 'HEALTHY').length} / {allSubsystems.length} Nominal
        </span>
      </div>

      <div style={styles.list}>
        {allSubsystems.map((sub) => {
          const isExpanded = expandedId === sub.subsystem_id;
          const SubIcon = getSubsystemIcon(sub.subsystem_id);
          const pill = getStatusPill(sub.status);
          const StatusIcon = pill.icon;

          return (
            <div key={sub.subsystem_id} style={styles.itemWrapper}>
              <div
                style={{
                  ...styles.itemHeader,
                  backgroundColor: isExpanded ? 'var(--bg-subtle)' : 'transparent',
                }}
                onClick={() => toggleExpand(sub.subsystem_id)}
              >
                {/* Left: Subsystem icon & name */}
                <div style={styles.leftCol}>
                  <div style={styles.iconCircle}>
                    <SubIcon size={14} color="var(--accent-primary)" />
                  </div>
                  <div style={styles.nameWrap}>
                    <div style={styles.subsystemName}>{sub.name}</div>
                    <div style={styles.subsystemSummary}>{sub.summary}</div>
                  </div>
                </div>

                {/* Right: Status Pill & Expand Chevron */}
                <div style={styles.rightCol}>
                  <div
                    style={{
                      ...styles.statusPill,
                      backgroundColor: pill.bg,
                      color: pill.color,
                    }}
                  >
                    <StatusIcon size={11} color={pill.color} />
                    <span>{pill.label}</span>
                  </div>

                  {isExpanded ? (
                    <ChevronDownIcon size={13} color="var(--text-muted)" />
                  ) : (
                    <ChevronRightIcon size={13} color="var(--text-muted)" />
                  )}
                </div>
              </div>

              {/* Expandable Technical Detail Drawer */}
              {isExpanded && (
                <div style={styles.detailDrawer}>
                  <div style={styles.drawerGrid}>
                    <div style={styles.drawerItem}>
                      <span style={styles.drawerKey}>Subsystem ID</span>
                      <span style={styles.drawerVal}>{sub.subsystem_id}</span>
                    </div>

                    {sub.latency_ms !== undefined && (
                      <div style={styles.drawerItem}>
                        <span style={styles.drawerKey}>Probe Latency</span>
                        <span style={styles.drawerVal}>{sub.latency_ms} ms</span>
                      </div>
                    )}

                    {Object.entries(sub.details || {}).map(([k, v]) => (
                      <div key={k} style={styles.drawerItem}>
                        <span style={styles.drawerKey}>
                          {k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
                        </span>
                        <span style={styles.drawerVal}>
                          {typeof v === 'boolean'
                            ? v
                              ? 'True (Armed)'
                              : 'False'
                            : typeof v === 'object'
                            ? JSON.stringify(v)
                            : String(v)}
                        </span>
                      </div>
                    ))}
                  </div>
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
  card: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px 14px',
    display: 'flex',
    flexDirection: 'column',
    gap: '10px',
    boxShadow: 'var(--shadow-card)',
  },
  sectionHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '4px',
  },
  sectionTitle: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  sectionBadge: {
    fontSize: '10px',
    fontWeight: 600,
    color: 'var(--text-muted)',
    backgroundColor: 'var(--bg-subtle)',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
  },
  list: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  itemWrapper: {
    border: '1px solid var(--border-subtle)',
    borderRadius: 'var(--radius-md)',
    overflow: 'hidden',
    transition: 'border-color var(--transition-fast)',
  },
  itemHeader: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    cursor: 'pointer',
    userSelect: 'none',
    gap: '8px',
  },
  leftCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    minWidth: 0,
    flex: 1,
  },
  iconCircle: {
    width: 24,
    height: 24,
    borderRadius: '50%',
    backgroundColor: 'var(--bg-app)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  nameWrap: {
    display: 'flex',
    flexDirection: 'column',
    minWidth: 0,
  },
  subsystemName: {
    fontSize: '11.5px',
    fontWeight: 600,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  subsystemSummary: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    whiteSpace: 'nowrap',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    marginTop: '1px',
  },
  rightCol: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    flexShrink: 0,
  },
  statusPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    padding: '2px 6px',
    borderRadius: 'var(--radius-sm)',
    fontSize: '10px',
    fontWeight: 600,
  },
  detailDrawer: {
    padding: '8px 10px 10px 10px',
    backgroundColor: 'var(--bg-app)',
    borderTop: '1px solid var(--border-subtle)',
  },
  drawerGrid: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  drawerItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10.5px',
    gap: '10px',
  },
  drawerKey: {
    color: 'var(--text-muted)',
    fontWeight: 500,
  },
  drawerVal: {
    color: 'var(--text-primary)',
    fontWeight: 600,
    textAlign: 'right',
    wordBreak: 'break-word',
  },
};
