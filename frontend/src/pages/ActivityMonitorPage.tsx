import React, { useState } from 'react';
import { useOrbit } from '../context/OrbitContext';
import {
  ActivityIcon,
  RefreshIcon,
  SearchIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  XCircleIcon,
} from '../components/icons/Icons';

export const ActivityMonitorPage: React.FC = () => {
  const { telemetryLogs, clearTelemetryLogs, connectionState } = useOrbit();
  const [filterLevel, setFilterLevel] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const filteredLogs = telemetryLogs.filter((log) => {
    const matchesLevel = filterLevel === 'ALL' || log.level === filterLevel;
    const matchesQuery = searchQuery === '' || 
      log.message.toLowerCase().includes(searchQuery.toLowerCase()) ||
      log.source.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesLevel && matchesQuery;
  });

  return (
    <div style={styles.container}>
      {/* Header */}
      <div style={styles.header}>
        <div>
          <h1 style={styles.title}>Live Activity Monitor</h1>
          <p style={styles.description}>
            Real-time telemetry event stream, action execution breakdown, and WebSocket envelope logs.
          </p>
        </div>

        <div style={styles.headerActions}>
          <button className="btn btn-secondary btn-sm" onClick={clearTelemetryLogs}>
            Clear Stream
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="card" style={styles.toolbarCard}>
        <div style={styles.filterGroup}>
          {['ALL', 'INFO', 'ACTION', 'WARN', 'ERROR'].map((lvl) => (
            <button
              key={lvl}
              style={{
                ...styles.filterBtn,
                ...(filterLevel === lvl ? styles.filterBtnActive : {}),
              }}
              onClick={() => setFilterLevel(lvl)}
            >
              {lvl}
            </button>
          ))}
        </div>

        <div style={styles.searchBox}>
          <SearchIcon size={14} color="var(--text-muted)" />
          <input
            type="text"
            placeholder="Filter logs by message or source..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            style={styles.searchInput}
          />
        </div>
      </div>

      {/* Stream Table */}
      <div className="card" style={styles.logCard}>
        {filteredLogs.length === 0 ? (
          <div style={styles.emptyLogs}>
            <ActivityIcon size={32} color="var(--text-muted)" />
            <div style={styles.emptyTitle}>No Telemetry Events Recorded</div>
            <p style={styles.emptySubtitle}>
              {connectionState === 'CONNECTED' 
                ? 'Waiting for runtime execution events...' 
                : 'Connect to ORBIT gateway to capture live runtime telemetry.'}
            </p>
          </div>
        ) : (
          <div style={styles.tableWrapper}>
            <table style={styles.table}>
              <thead>
                <tr style={styles.theadRow}>
                  <th style={{ ...styles.th, width: 100 }}>TIME</th>
                  <th style={{ ...styles.th, width: 90 }}>LEVEL</th>
                  <th style={{ ...styles.th, width: 130 }}>SOURCE</th>
                  <th style={styles.th}>MESSAGE</th>
                </tr>
              </thead>
              <tbody>
                {filteredLogs.map((log) => (
                  <tr key={log.id} style={styles.tr}>
                    <td style={styles.tdTime}>{log.timestamp}</td>
                    <td style={styles.td}>
                      <span className={`badge ${
                        log.level === 'INFO' ? 'badge-online' :
                        log.level === 'ACTION' ? 'badge-busy' :
                        log.level === 'WARN' ? 'badge-warning' : 'badge-error'
                      }`}>
                        {log.level}
                      </span>
                    </td>
                    <td style={styles.tdSource}>
                      <span style={styles.sourceTag}>{log.source}</span>
                    </td>
                    <td style={styles.tdMessage}>
                      <div style={styles.messageText}>{log.message}</div>
                      {log.payload && Object.keys(log.payload).length > 0 && (
                        <pre style={styles.payloadPre}>
                          {JSON.stringify(log.payload, null, 2)}
                        </pre>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: 'var(--space-4)',
    height: '100%',
    maxWidth: 1400,
    margin: '0 auto',
  },
  header: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  title: {
    fontSize: 'var(--font-size-2xl)',
    fontWeight: 700,
    color: 'var(--text-primary)',
    marginBottom: 'var(--space-1)',
  },
  description: {
    fontSize: 'var(--font-size-sm)',
    color: 'var(--text-muted)',
  },
  headerActions: {
    display: 'flex',
    gap: 'var(--space-2)',
  },
  toolbarCard: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 'var(--space-3) var(--space-4)',
  },
  filterGroup: {
    display: 'flex',
    gap: '6px',
  },
  filterBtn: {
    padding: '4px 10px',
    fontSize: '11px',
    fontWeight: 600,
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-default)',
    background: 'var(--bg-surface-elevated)',
    color: 'var(--text-muted)',
    cursor: 'pointer',
  },
  filterBtnActive: {
    background: 'var(--accent-primary)',
    borderColor: 'var(--accent-primary)',
    color: '#ffffff',
  },
  searchBox: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    background: 'var(--bg-input)',
    width: 320,
  },
  searchInput: {
    background: 'transparent',
    border: 'none',
    color: 'var(--text-primary)',
    fontSize: 'var(--font-size-xs)',
    outline: 'none',
    width: '100%',
  },
  logCard: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    padding: 0,
    overflow: 'hidden',
  },
  tableWrapper: {
    flex: 1,
    overflowY: 'auto',
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    textAlign: 'left',
  },
  theadRow: {
    backgroundColor: 'var(--bg-surface-elevated)',
    borderBottom: '1px solid var(--border-default)',
    position: 'sticky',
    top: 0,
    zIndex: 2,
  },
  th: {
    padding: '8px var(--space-4)',
    fontSize: '10.5px',
    fontWeight: 700,
    color: 'var(--text-muted)',
    letterSpacing: '0.06em',
  },
  tr: {
    borderBottom: '1px solid var(--border-subtle)',
    transition: 'background var(--transition-fast)',
  },
  tdTime: {
    padding: '8px var(--space-4)',
    fontFamily: 'var(--font-mono)',
    fontSize: '11px',
    color: 'var(--text-muted)',
    whiteSpace: 'nowrap',
  },
  td: {
    padding: '8px var(--space-4)',
    verticalAlign: 'top',
  },
  tdSource: {
    padding: '8px var(--space-4)',
    verticalAlign: 'top',
  },
  sourceTag: {
    fontSize: '11px',
    fontFamily: 'var(--font-mono)',
    color: 'var(--accent-cyan)',
  },
  tdMessage: {
    padding: '8px var(--space-4)',
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-primary)',
    verticalAlign: 'top',
  },
  messageText: {
    lineHeight: 1.4,
  },
  payloadPre: {
    marginTop: '6px',
    padding: 'var(--space-2) var(--space-3)',
    backgroundColor: 'var(--bg-input)',
    borderRadius: 'var(--radius-sm)',
    border: '1px solid var(--border-subtle)',
    fontSize: '11px',
    color: 'var(--text-secondary)',
    overflowX: 'auto',
  },
  emptyLogs: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 'var(--space-3)',
    padding: 'var(--space-10)',
    textAlign: 'center',
  },
  emptyTitle: {
    fontSize: 'var(--font-size-md)',
    fontWeight: 600,
    color: 'var(--text-secondary)',
  },
  emptySubtitle: {
    fontSize: 'var(--font-size-xs)',
    color: 'var(--text-muted)',
    maxWidth: 400,
  },
};
