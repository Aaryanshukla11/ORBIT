import React from 'react';
import { useDiagnostics } from '../../context/DiagnosticsContext';
import {
  PulseHeartIcon,
  RefreshIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  XCircleIcon,
} from '../icons/Icons';

export const DiagnosticSummaryHeader: React.FC = () => {
  const { report, isProbing, runDiagnostics, lastProbedAt } = useDiagnostics();

  const status = report?.overall_status || 'UNKNOWN';

  const getStatusBadge = () => {
    switch (status) {
      case 'HEALTHY':
        return {
          label: 'System Operational',
          color: 'var(--accent-green)',
          bg: 'var(--accent-green-subtle)',
          icon: CheckCircleIcon,
        };
      case 'DEGRADED':
        return {
          label: 'Attention Required',
          color: '#f59e0b',
          bg: '#fef3c7',
          icon: AlertTriangleIcon,
        };
      case 'FAILED':
        return {
          label: 'System Impaired',
          color: 'var(--accent-rose)',
          bg: 'var(--accent-rose-subtle)',
          icon: XCircleIcon,
        };
      default:
        return {
          label: 'Evaluating Status...',
          color: 'var(--text-muted)',
          bg: 'var(--bg-subtle)',
          icon: PulseHeartIcon,
        };
    }
  };

  const badge = getStatusBadge();
  const Icon = badge.icon;
  const metrics = report?.metrics;

  return (
    <div style={styles.card}>
      {/* Top row: Title and Status badge */}
      <div style={styles.topRow}>
        <div style={styles.titleWrap}>
          <PulseHeartIcon size={18} color="var(--accent-primary)" />
          <div>
            <div style={styles.title}>Diagnostics & Health</div>
            <div style={styles.subtitle}>
              {lastProbedAt
                ? `Last evaluated: ${lastProbedAt.toLocaleTimeString()}`
                : 'Evaluating system integrity...'}
            </div>
          </div>
        </div>

        <button
          type="button"
          style={{
            ...styles.runBtn,
            opacity: isProbing ? 0.7 : 1,
          }}
          onClick={() => runDiagnostics()}
          disabled={isProbing}
          title="Execute deep system diagnostic probe"
        >
          <RefreshIcon
            size={13}
            color="#ffffff"
            style={{
              animation: isProbing ? 'spin 1s linear infinite' : 'none',
            }}
          />
          <span>{isProbing ? 'Probing...' : 'Run Probe'}</span>
        </button>
      </div>

      {/* Main Status Pill Banner */}
      <div
        style={{
          ...styles.statusBanner,
          backgroundColor: badge.bg,
          borderColor: badge.color,
        }}
      >
        <div style={styles.bannerLeft}>
          <Icon size={18} color={badge.color} />
          <div style={styles.bannerText}>
            <div style={{ ...styles.bannerTitle, color: badge.color }}>
              {badge.label}
            </div>
            <div style={styles.bannerDesc}>
              {report?.summary_text || 'Collecting diagnostic telemetry across ORBIT subsystems.'}
            </div>
          </div>
        </div>
      </div>

      {/* Quick Subsystem Metric Counters */}
      {metrics && (
        <div style={styles.metricsRow}>
          <div style={styles.metricItem}>
            <span style={styles.metricVal}>{metrics.total_subsystems}</span>
            <span style={styles.metricLabel}>Total Subsystems</span>
          </div>
          <div style={styles.metricDivider} />
          <div style={styles.metricItem}>
            <span style={{ ...styles.metricVal, color: 'var(--accent-green)' }}>
              {metrics.healthy_count}
            </span>
            <span style={styles.metricLabel}>Healthy</span>
          </div>
          <div style={styles.metricDivider} />
          <div style={styles.metricItem}>
            <span
              style={{
                ...styles.metricVal,
                color: metrics.degraded_count > 0 ? '#f59e0b' : 'var(--text-muted)',
              }}
            >
              {metrics.degraded_count}
            </span>
            <span style={styles.metricLabel}>Degraded</span>
          </div>
          <div style={styles.metricDivider} />
          <div style={styles.metricItem}>
            <span
              style={{
                ...styles.metricVal,
                color: metrics.failed_count > 0 ? 'var(--accent-rose)' : 'var(--text-muted)',
              }}
            >
              {metrics.failed_count}
            </span>
            <span style={styles.metricLabel}>Failed</span>
          </div>
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
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    boxShadow: 'var(--shadow-card)',
  },
  topRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  title: {
    fontSize: '13.5px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '10px',
    color: 'var(--text-muted)',
    marginTop: '2px',
  },
  runBtn: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '5px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    border: 'none',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  statusBanner: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 12px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid',
  },
  bannerLeft: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '10px',
  },
  bannerText: {
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  bannerTitle: {
    fontSize: '12px',
    fontWeight: 700,
  },
  bannerDesc: {
    fontSize: '11px',
    color: 'var(--text-secondary)',
    lineHeight: 1.35,
  },
  metricsRow: {
    display: 'grid',
    gridTemplateColumns: '1fr auto 1fr auto 1fr auto 1fr',
    alignItems: 'center',
    backgroundColor: 'var(--bg-app)',
    borderRadius: 'var(--radius-md)',
    padding: '8px 10px',
  },
  metricItem: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '1px',
  },
  metricVal: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  metricLabel: {
    fontSize: '9.5px',
    color: 'var(--text-muted)',
    letterSpacing: '-0.01em',
  },
  metricDivider: {
    width: 1,
    height: 18,
    backgroundColor: 'var(--border-subtle)',
  },
};
