/**
 * Domain types for ORBIT Security & Safety Subsystem
 */

export type PolicyLevel = 'ALLOW' | 'ASK' | 'DENY';

export interface SystemCapabilityPolicy {
  id: string;
  name: string;
  description: string;
  level: PolicyLevel;
  category: 'input' | 'system' | 'storage' | 'network';
  isRealEnforced: boolean;
}

export interface AppGranularPermissions {
  windowFocus: PolicyLevel;
  keyboardInput: PolicyLevel;
  mouseInteraction: PolicyLevel;
  textReading: PolicyLevel;
  screenObservation: PolicyLevel;
}

export interface ApplicationPolicyItem {
  id: string;
  name: string;
  publisher: string;
  processName: string;
  category: string;
  accessLevel: PolicyLevel;
  permissions: AppGranularPermissions;
  lastAccessed?: string;
  installed?: boolean;
}

export interface SecurityAuditEvent {
  id: string;
  timestamp: string;
  action: string;
  target: string;
  result: 'ALLOWED' | 'BLOCKED' | 'PREEMPTED' | 'AUTHORIZED' | 'DENIED';
  tier: number;
  details?: string;
}

export interface HumanTakeoverSafetyState {
  guardStatus: 'READY' | 'ACTIVE' | 'DEGRADED';
  emergencyStopAvailable: boolean;
  autonomousPolicy: 'SUPERVISED' | 'AUTONOMOUS' | 'RESTRICTED';
  watchdogArmed: boolean;
  activeTakeoverPreempting: boolean;
}
