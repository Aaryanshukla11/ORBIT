import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { SystemDiagnosticReport, ElectronDiagnostics, DiagnosticStatus } from '../types/diagnostics';
import { useOrbit } from './OrbitContext';

interface DiagnosticsContextValue {
  report: SystemDiagnosticReport | null;
  electronDiagnostics: ElectronDiagnostics | null;
  isLoading: boolean;
  isProbing: boolean;
  lastProbedAt: Date | null;
  selectedSubsystemId: string | null;
  copiedToast: boolean;
  setSelectedSubsystemId: (id: string | null) => void;
  runDiagnostics: () => Promise<void>;
  copyDiagnosticSummary: () => Promise<boolean>;
}

const DiagnosticsContext = createContext<DiagnosticsContextValue | undefined>(undefined);

export const DiagnosticsProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { connectionState } = useOrbit();
  const [report, setReport] = useState<SystemDiagnosticReport | null>(null);
  const [electronDiagnostics, setElectronDiagnostics] = useState<ElectronDiagnostics | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isProbing, setIsProbing] = useState<boolean>(false);
  const [lastProbedAt, setLastProbedAt] = useState<Date | null>(null);
  const [selectedSubsystemId, setSelectedSubsystemId] = useState<string | null>(null);
  const [copiedToast, setCopiedToast] = useState<boolean>(false);

  // Fetch native Electron platform diagnostics
  const fetchElectronDiagnostics = useCallback(async () => {
    if (typeof window !== 'undefined' && window.orbitDesktop) {
      try {
        const [sysInfo, displays, isPinned, appVer] = await Promise.all([
          window.orbitDesktop.getSystemInfo ? window.orbitDesktop.getSystemInfo() : null,
          window.orbitDesktop.getSystemDisplays ? window.orbitDesktop.getSystemDisplays() : [],
          window.orbitDesktop.isPinned ? window.orbitDesktop.isPinned() : false,
          window.orbitDesktop.getAppVersion ? window.orbitDesktop.getAppVersion() : '1.0.0',
        ]);

        const primaryDisplay = displays.find((d: any) => d.isPrimary) || displays[0];

        setElectronDiagnostics({
          appVersion: appVer || '1.0.0',
          platform: sysInfo?.platform || 'win32',
          release: sysInfo?.release || 'Windows 11',
          arch: sysInfo?.arch || 'x64',
          cpuModel: sysInfo?.cpuModel || 'Generic Processor',
          cpuCores: sysInfo?.cpuCores || 8,
          totalMemory: sysInfo?.totalMemory || '16.0 GB',
          freeMemory: sysInfo?.freeMemory || '8.0 GB',
          electronVersion: sysInfo?.electronVersion || '33.0.0',
          chromeVersion: sysInfo?.chromeVersion || '130.0.0',
          nodeVersion: sysInfo?.nodeVersion || '20.0.0',
          displaysCount: displays.length || 1,
          primaryResolution: primaryDisplay ? primaryDisplay.resolution : '1920 × 1080',
          isPinned: !!isPinned,
        });
      } catch (err) {
        console.warn('[Diagnostics] Failed to query Electron diagnostics:', err);
      }
    }
  }, []);

  // Fetch initial / cached diagnostics from backend
  const fetchBackendDiagnostics = useCallback(async () => {
    try {
      const resp = await fetch('http://127.0.0.1:8765/api/diagnostics');
      if (resp.ok) {
        const data: SystemDiagnosticReport = await resp.json();
        setReport(data);
        setLastProbedAt(new Date());
      }
    } catch (err) {
      console.warn('[Diagnostics] Backend unreachable:', err);
      // Construct fallback disconnected report
      setReport({
        overall_status: 'FAILED',
        timestamp: new Date().toISOString(),
        subsystems: [
          {
            subsystem_id: 'backend',
            name: 'ORBIT Backend Gateway',
            status: 'FAILED',
            summary: 'Backend daemon unreachable at 127.0.0.1:8765',
            details: { host: '127.0.0.1', port: 8765 },
            last_checked: new Date().toISOString(),
          },
          {
            subsystem_id: 'websocket',
            name: 'Gateway & WebSocket Stream',
            status: 'FAILED',
            summary: 'WebSocket channel disconnected',
            details: {},
            last_checked: new Date().toISOString(),
          },
        ],
        issues: [
          {
            issue_id: 'issue_backend_offline',
            severity: 'CRITICAL',
            title: 'Backend Gateway Offline',
            description: 'The ORBIT Python runtime at 127.0.0.1:8765 is not accepting HTTP or WebSocket connections.',
            subsystem: 'backend',
            timestamp: new Date().toISOString(),
            remediation: 'Ensure the ORBIT backend daemon is running ($env:PYTHONPATH="src"; python -m orbit).',
          },
        ],
        metrics: {
          total_subsystems: 2,
          healthy_count: 0,
          degraded_count: 0,
          failed_count: 2,
          unavailable_count: 0,
          elapsed_ms: 0,
        },
        summary_text: 'ORBIT Backend Offline — Connection to 127.0.0.1:8765 failed.',
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Run deep live diagnostic scan across all subsystems
  const runDiagnostics = useCallback(async () => {
    setIsProbing(true);
    try {
      await fetchElectronDiagnostics();
      const resp = await fetch('http://127.0.0.1:8765/api/diagnostics/run', {
        method: 'POST',
      });
      if (resp.ok) {
        const data: SystemDiagnosticReport = await resp.json();
        setReport(data);
        setLastProbedAt(new Date());
      } else {
        await fetchBackendDiagnostics();
      }
    } catch (err) {
      console.warn('[Diagnostics] Error running diagnostics probe:', err);
      await fetchBackendDiagnostics();
    } finally {
      setIsProbing(false);
    }
  }, [fetchBackendDiagnostics, fetchElectronDiagnostics]);

  // Copy sanitized diagnostic summary
  const copyDiagnosticSummary = useCallback(async (): Promise<boolean> => {
    if (!report) return false;

    const lines: string[] = [
      `==================================================`,
      `ORBIT DESKTOP SYSTEM DIAGNOSTIC REPORT`,
      `Generated: ${new Date().toISOString()}`,
      `Overall Status: ${report.overall_status}`,
      `Summary: ${report.summary_text}`,
      `==================================================`,
      ``,
      `--- SUBSYSTEM HEALTH ---`,
    ];

    for (const sub of report.subsystems) {
      lines.push(`• [${sub.status}] ${sub.name}: ${sub.summary} (${sub.latency_ms ?? 0}ms)`);
    }

    if (electronDiagnostics) {
      lines.push(``);
      lines.push(`--- DESKTOP ENVIRONMENT ---`);
      lines.push(`• Platform: ${electronDiagnostics.platform} (${electronDiagnostics.arch})`);
      lines.push(`• OS Release: ${electronDiagnostics.release}`);
      lines.push(`• CPU: ${electronDiagnostics.cpuModel} (${electronDiagnostics.cpuCores} cores)`);
      lines.push(`• Memory: ${electronDiagnostics.freeMemory} free / ${electronDiagnostics.totalMemory} total`);
      lines.push(`• Displays: ${electronDiagnostics.displaysCount} monitor(s) (Primary: ${electronDiagnostics.primaryResolution})`);
      lines.push(`• Electron: v${electronDiagnostics.electronVersion} | Chrome: v${electronDiagnostics.chromeVersion}`);
    }

    if (report.issues.length > 0) {
      lines.push(``);
      lines.push(`--- ACTIVE ISSUES (${report.issues.length}) ---`);
      for (const iss of report.issues) {
        lines.push(`[${iss.severity}] ${iss.title} (${iss.subsystem})`);
        lines.push(`  Details: ${iss.description}`);
        if (iss.remediation) {
          lines.push(`  Remediation: ${iss.remediation}`);
        }
      }
    }

    const textToCopy = lines.join('\n');

    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedToast(true);
      setTimeout(() => setCopiedToast(false), 2500);
      return true;
    } catch (e) {
      console.warn('Clipboard write failed:', e);
      return false;
    }
  }, [report, electronDiagnostics]);

  // Initial load and connection state observer
  useEffect(() => {
    fetchElectronDiagnostics();
    fetchBackendDiagnostics();
  }, [fetchBackendDiagnostics, fetchElectronDiagnostics]);

  useEffect(() => {
    if (connectionState === 'CONNECTED') {
      fetchBackendDiagnostics();
    }
  }, [connectionState, fetchBackendDiagnostics]);

  return (
    <DiagnosticsContext.Provider
      value={{
        report,
        electronDiagnostics,
        isLoading,
        isProbing,
        lastProbedAt,
        selectedSubsystemId,
        copiedToast,
        setSelectedSubsystemId,
        runDiagnostics,
        copyDiagnosticSummary,
      }}
    >
      {children}
    </DiagnosticsContext.Provider>
  );
};

export const useDiagnostics = (): DiagnosticsContextValue => {
  const context = useContext(DiagnosticsContext);
  if (!context) {
    throw new Error('useDiagnostics must be used within a DiagnosticsProvider');
  }
  return context;
};
