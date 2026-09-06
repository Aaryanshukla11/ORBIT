export type DiagnosticStatus = 'HEALTHY' | 'DEGRADED' | 'FAILED' | 'UNAVAILABLE' | 'UNKNOWN';

export type IssueSeverity = 'CRITICAL' | 'WARNING' | 'INFO';

export interface StructuredIssue {
  issue_id: string;
  severity: IssueSeverity;
  title: string;
  description: string;
  subsystem: string;
  timestamp: string;
  remediation?: string;
  technical_details?: string;
}

export interface SubsystemDiagnosticReport {
  subsystem_id: string;
  name: string;
  status: DiagnosticStatus;
  summary: string;
  latency_ms?: number;
  details: Record<string, any>;
  last_checked: string;
}

export interface SystemDiagnosticReport {
  overall_status: DiagnosticStatus;
  timestamp: string;
  subsystems: SubsystemDiagnosticReport[];
  issues: StructuredIssue[];
  metrics: {
    total_subsystems: number;
    healthy_count: number;
    degraded_count: number;
    failed_count: number;
    unavailable_count: number;
    elapsed_ms: number;
  };
  summary_text: string;
}

export interface ElectronDiagnostics {
  appVersion: string;
  platform: string;
  release: string;
  arch: string;
  cpuModel: string;
  cpuCores: number;
  totalMemory: string;
  freeMemory: string;
  electronVersion: string;
  chromeVersion: string;
  nodeVersion: string;
  displaysCount: number;
  primaryResolution: string;
  isPinned: boolean;
}
