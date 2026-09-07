import React, { useState } from 'react';
import {
  SettingsTabIcon,
  ShieldIcon,
  ServerIcon,
  CheckCircleIcon,
  ModelsIcon,
  CpuChipIcon,
} from '../icons/Icons';
import { ActiveModelCard } from '../models/ActiveModelCard';
import { SourceSwitcher } from '../models/SourceSwitcher';
import { LocalModelsList } from '../models/LocalModelsList';
import { CloudModelsList } from '../models/CloudModelsList';
import { SystemModelStatus } from '../models/SystemModelStatus';
import { useModelManager } from '../../context/ModelManagerContext';

export type SettingsSection = 'models' | 'agent' | 'network';

export const SettingsView: React.FC = () => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('models');
  const [autonomyMode, setAutonomyMode] = useState<'supervised' | 'autonomous'>('supervised');
  const [safetyGates, setSafetyGates] = useState<boolean>(true);
  const [maxSteps, setMaxSteps] = useState<number>(15);
  const [gatewayPort, setGatewayPort] = useState<string>('8765');
  const [savedToast, setSavedToast] = useState<boolean>(false);

  const { sourceTab } = useModelManager();

  const handleSave = () => {
    setSavedToast(true);
    setTimeout(() => {
      setSavedToast(false);
    }, 2000);
  };

  return (
    <div style={styles.container}>
      {/* 1. Settings Header */}
      <div style={styles.headerRow}>
        <div style={styles.titleWrap}>
          <SettingsTabIcon size={16} color="var(--accent-primary)" />
          <div>
            <h1 style={styles.title}>Settings & Configuration</h1>
            <p style={styles.subtitle}>LLM providers, agent autonomy, and system runtime preferences</p>
          </div>
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

      {/* 2. Segmented Section Selector */}
      <div style={styles.sectionNav}>
        <button
          type="button"
          style={{
            ...styles.navBtn,
            backgroundColor: activeSection === 'models' ? 'var(--bg-surface)' : 'transparent',
            color: activeSection === 'models' ? 'var(--accent-primary)' : 'var(--text-muted)',
            fontWeight: activeSection === 'models' ? 700 : 500,
            boxShadow: activeSection === 'models' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
          }}
          onClick={() => setActiveSection('models')}
        >
          <ModelsIcon size={14} color={activeSection === 'models' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <span>AI Models & Providers</span>
        </button>

        <button
          type="button"
          style={{
            ...styles.navBtn,
            backgroundColor: activeSection === 'agent' ? 'var(--bg-surface)' : 'transparent',
            color: activeSection === 'agent' ? 'var(--accent-primary)' : 'var(--text-muted)',
            fontWeight: activeSection === 'agent' ? 700 : 500,
            boxShadow: activeSection === 'agent' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
          }}
          onClick={() => setActiveSection('agent')}
        >
          <ShieldIcon size={14} color={activeSection === 'agent' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <span>Agent & Autonomy</span>
        </button>

        <button
          type="button"
          style={{
            ...styles.navBtn,
            backgroundColor: activeSection === 'network' ? 'var(--bg-surface)' : 'transparent',
            color: activeSection === 'network' ? 'var(--accent-primary)' : 'var(--text-muted)',
            fontWeight: activeSection === 'network' ? 700 : 500,
            boxShadow: activeSection === 'network' ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
          }}
          onClick={() => setActiveSection('network')}
        >
          <ServerIcon size={14} color={activeSection === 'network' ? 'var(--accent-primary)' : 'var(--text-muted)'} />
          <span>Gateway & System</span>
        </button>
      </div>

      {/* 3. Section Content Body */}
      <div style={styles.scrollBody}>
        {/* SECTION A: AI Models & Providers */}
        {activeSection === 'models' && (
          <div style={styles.tabContent}>
            {/* Active Model Hero Card */}
            <ActiveModelCard />

            {/* Source Switcher (Local | Cloud) */}
            <SourceSwitcher />

            {/* Dynamic Model List */}
            {sourceTab === 'local' ? <LocalModelsList /> : <CloudModelsList />}

            {/* System Model Runtime State Strip */}
            <SystemModelStatus />
          </div>
        )}

        {/* SECTION B: Agent Preferences */}
        {activeSection === 'agent' && (
          <div style={styles.tabContent}>
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
          </div>
        )}

        {/* SECTION C: Gateway & System */}
        {activeSection === 'network' && (
          <div style={styles.tabContent}>
            {/* Gateway Port */}
            <div style={styles.sectionCard}>
              <div style={styles.cardTitle}>Backend Gateway WebSocket Port</div>
              <input
                type="text"
                value={gatewayPort}
                onChange={(e) => setGatewayPort(e.target.value)}
                style={styles.input}
              />
              <span style={styles.helperText}>
                Default ORBIT Python Gateway connects on ws://127.0.0.1:{gatewayPort}
              </span>
            </div>

            {/* Runtime IPC Bridge */}
            <div style={styles.sectionCard}>
              <div style={styles.cardTitle}>Desktop Companion Bridge</div>
              <div style={styles.bridgeInfoRow}>
                <CpuChipIcon size={14} color="var(--accent-primary)" />
                <span style={styles.bridgeInfoText}>
                  {typeof window !== 'undefined' && window.orbitDesktop
                    ? `Electron Companion v${window.orbitDesktop.platform || 'win32'} Active`
                    : 'Web Browser Renderer (Desktop companion hooks disabled)'}
                </span>
              </div>
              <span style={styles.helperText}>
                Enables native Win32 window management, display discovery, process launching, and always-on-top pinning.
              </span>
            </div>
          </div>
        )}
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
    width: '100%',
    height: '100%',
  },
  headerRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 18px 8px 18px',
    borderBottom: '1px solid var(--border-subtle)',
    backgroundColor: 'var(--bg-surface)',
  },
  titleWrap: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  title: {
    fontSize: '13px',
    fontWeight: 700,
    color: 'var(--text-primary)',
    margin: 0,
    lineHeight: 1.2,
  },
  subtitle: {
    fontSize: '10.5px',
    color: 'var(--text-muted)',
    margin: 0,
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
    margin: '8px 18px 0 18px',
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
  sectionNav: {
    display: 'flex',
    alignItems: 'center',
    margin: '8px 18px 0 18px',
    padding: '3px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-subtle)',
    gap: '4px',
    userSelect: 'none',
  },
  navBtn: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '6px',
    padding: '6px 10px',
    borderRadius: 'calc(var(--radius-md) - 2px)',
    border: 'none',
    fontSize: '11px',
    cursor: 'pointer',
    transition: 'all var(--transition-fast)',
  },
  scrollBody: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 18px 24px 18px',
  },
  tabContent: {
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
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
  bridgeInfoRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 8px',
    borderRadius: 'var(--radius-md)',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-subtle)',
  },
  bridgeInfoText: {
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--text-primary)',
  },
};
