import React, { useState } from 'react';
import { SettingsTabIcon, ShieldIcon, ServerIcon, CheckCircleIcon } from '../icons/Icons';

export const SettingsView: React.FC = () => {
  const [autonomyMode, setAutonomyMode] = useState<'supervised' | 'autonomous'>('supervised');
  const [safetyGates, setSafetyGates] = useState<boolean>(true);
  const [maxSteps, setMaxSteps] = useState<number>(15);
  const [gatewayPort, setGatewayPort] = useState<string>('8765');
  const [savedToast, setSavedToast] = useState<boolean>(false);

  const handleSave = () => {
    setSavedToast(true);
    setTimeout(() => {
      setSavedToast(false);
    }, 2000);
  };

  return (
    <div style={styles.container}>
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <SettingsTabIcon size={16} color="var(--accent-primary)" />
          <span style={styles.title}>Agent Preferences</span>
        </div>
        <button type="button" style={styles.saveBtn} onClick={handleSave}>
          Apply Changes
        </button>
      </div>

      {savedToast && (
        <div style={styles.toast}>
          <CheckCircleIcon size={13} color="var(--accent-green)" />
          <span>Configuration applied successfully</span>
        </div>
      )}

      {/* Autonomy Level */}
      <div style={styles.sectionCard}>
        <div style={styles.cardTitle}>Autonomy Control Level</div>
        <div style={styles.modeToggleGroup}>
          <button
            type="button"
            style={{
              ...styles.modeBtn,
              backgroundColor: autonomyMode === 'supervised' ? 'var(--bg-surface)' : 'transparent',
              color: autonomyMode === 'supervised' ? 'var(--accent-primary)' : 'var(--text-muted)',
              boxShadow: autonomyMode === 'supervised' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setAutonomyMode('supervised')}
          >
            Human-Supervised
          </button>
          <button
            type="button"
            style={{
              ...styles.modeBtn,
              backgroundColor: autonomyMode === 'autonomous' ? 'var(--bg-surface)' : 'transparent',
              color: autonomyMode === 'autonomous' ? 'var(--accent-primary)' : 'var(--text-muted)',
              boxShadow: autonomyMode === 'autonomous' ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
            }}
            onClick={() => setAutonomyMode('autonomous')}
          >
            Autonomous Agent
          </button>
        </div>
        <span style={styles.helperText}>
          {autonomyMode === 'supervised'
            ? 'Prompts confirmation before executing mouse clicks or file changes.'
            : 'Executes chained workflow actions autonomously without prompt blocking.'}
        </span>
      </div>

      {/* Safety Gate Toggle */}
      <div style={styles.sectionCard}>
        <div style={styles.toggleRow}>
          <div style={styles.toggleLabelWrap}>
            <div style={styles.cardTitle}>Tier 3 Safety Gate (Hard-Block)</div>
            <span style={styles.helperText}>Block destructive disk/network requests</span>
          </div>
          <button
            type="button"
            style={{
              ...styles.switchTrack,
              backgroundColor: safetyGates ? 'var(--accent-green)' : 'var(--bg-subtle)',
            }}
            onClick={() => setSafetyGates(!safetyGates)}
          >
            <div
              style={{
                ...styles.switchThumb,
                transform: safetyGates ? 'translateX(16px)' : 'translateX(2px)',
              }}
            />
          </button>
        </div>
      </div>

      {/* Execution Limits */}
      <div style={styles.sectionCard}>
        <div style={styles.cardTitle}>Max Chained Steps: {maxSteps}</div>
        <input
          type="range"
          min={5}
          max={50}
          step={1}
          value={maxSteps}
          onChange={(e) => setMaxSteps(Number(e.target.value))}
          style={styles.slider}
        />
        <div style={styles.sliderLimits}>
          <span>5 Steps</span>
          <span>50 Steps</span>
        </div>
      </div>

      {/* Gateway Port */}
      <div style={styles.sectionCard}>
        <div style={styles.cardTitle}>Backend Gateway Port</div>
        <input
          type="text"
          value={gatewayPort}
          onChange={(e) => setGatewayPort(e.target.value)}
          style={styles.input}
        />
        <span style={styles.helperText}>Default ORBIT WebSocket port is 8765</span>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflowY: 'auto',
    padding: '10px 18px 24px 18px',
    gap: '12px',
    userSelect: 'none',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingBottom: '8px',
    borderBottom: '1px solid var(--border-subtle)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
  },
  title: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  saveBtn: {
    padding: '4px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-primary)',
    color: '#ffffff',
    border: 'none',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  toast: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 10px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--accent-green-subtle)',
    color: 'var(--accent-green)',
    fontSize: '11px',
    fontWeight: 600,
  },
  sectionCard: {
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-lg)',
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    boxShadow: 'var(--shadow-card)',
  },
  cardTitle: {
    fontSize: '12px',
    fontWeight: 700,
    color: 'var(--text-primary)',
  },
  modeToggleGroup: {
    display: 'flex',
    backgroundColor: 'var(--bg-subtle)',
    borderRadius: 'var(--radius-md)',
    padding: '3px',
  },
  modeBtn: {
    flex: 1,
    padding: '6px 8px',
    borderRadius: 'calc(var(--radius-md) - 2px)',
    border: 'none',
    fontSize: '11px',
    fontWeight: 600,
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  helperText: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    lineHeight: 1.35,
  },
  toggleRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  toggleLabelWrap: {
    display: 'flex',
    flexDirection: 'column',
  },
  switchTrack: {
    width: 36,
    height: 20,
    borderRadius: 'var(--radius-full)',
    border: 'none',
    cursor: 'pointer',
    position: 'relative',
    display: 'flex',
    alignItems: 'center',
    transition: 'background-color 0.2s ease',
  },
  switchThumb: {
    width: 16,
    height: 16,
    borderRadius: '50%',
    backgroundColor: '#ffffff',
    boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
    transition: 'transform 0.2s ease',
  },
  slider: {
    width: '100%',
    accentColor: 'var(--accent-primary)',
    cursor: 'pointer',
  },
  sliderLimits: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    fontSize: '10px',
    color: 'var(--text-muted)',
  },
  input: {
    padding: '6px 10px',
    borderRadius: 'var(--radius-md)',
    border: '1px solid var(--border-default)',
    backgroundColor: 'var(--bg-app)',
    color: 'var(--text-primary)',
    fontSize: '12px',
    outline: 'none',
  },
};
