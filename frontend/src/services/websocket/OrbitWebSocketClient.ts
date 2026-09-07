/**
 * ORBIT WebSocket Gateway Client
 * 
 * Clean communication boundary with the existing ORBIT Python WebSocket Gateway.
 * Supports typed command dispatching, event streaming, automatic backoff reconnects,
 * and robust connection lifecycle monitoring.
 */

import { ConnectionState, BaseCommand, EventEnvelope } from '../../types';

export type EventCallback = (event: EventEnvelope) => void;
export type StateChangeCallback = (state: ConnectionState, url: string, error?: string) => void;

export class OrbitWebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private sessionId: string | null = null;
  private state: ConnectionState = 'DISCONNECTED';
  private reconnectTimer: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1500;
  private autoReconnect = true;

  private eventListeners: Map<string, Set<EventCallback>> = new Map();
  private allEventListeners: Set<EventCallback> = new Set();
  private stateChangeListeners: Set<StateChangeCallback> = new Set();

  constructor(url = 'ws://127.0.0.1:8765/ws') {
    this.url = url;
  }

  public getUrl(): string {
    return this.url;
  }

  public getState(): ConnectionState {
    return this.state;
  }

  public getSessionId(): string | null {
    return this.sessionId;
  }

  public connect(customUrl?: string, sessionId?: string): void {
    if (customUrl) {
      this.url = customUrl;
    }
    if (sessionId) {
      this.sessionId = sessionId;
    }

    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.clearReconnectTimer();
    this.setState('CONNECTING');

    const fullUrl = this.sessionId ? `${this.url.replace(/\/$/, '')}/${this.sessionId}` : this.url;

    try {
      this.ws = new WebSocket(fullUrl);
      this.setupSocketHandlers();
    } catch (err: any) {
      this.setState('ERROR', err.message || 'Failed to initialize WebSocket');
      this.scheduleReconnect();
    }
  }

  public disconnect(reason = 'User initiated disconnect'): void {
    this.autoReconnect = false;
    this.clearReconnectTimer();

    if (this.ws) {
      this.ws.close(1000, reason);
      this.ws = null;
    }
    this.setState('DISCONNECTED');
  }

  public sendCommand(commandType: string, payload: Record<string, any> = {}, correlationId?: string): boolean {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn(`[OrbitWS] Cannot send command ${commandType}: WebSocket not OPEN.`);
      return false;
    }

    const command: BaseCommand = {
      command_id: this.generateUuid(),
      command_type: commandType,
      session_id: this.sessionId || 'default',
      timestamp: new Date().toISOString(),
      payload: {
        ...payload,
        ...(correlationId ? { correlation_id: correlationId } : {}),
      },
    };

    try {
      this.ws.send(JSON.stringify(command));
      return true;
    } catch (err) {
      console.error(`[OrbitWS] Error sending command ${commandType}:`, err);
      return false;
    }
  }

  public onEvent(eventType: string, callback: EventCallback): () => void {
    if (!this.eventListeners.has(eventType)) {
      this.eventListeners.set(eventType, new Set());
    }
    this.eventListeners.get(eventType)!.add(callback);

    return () => {
      this.eventListeners.get(eventType)?.delete(callback);
    };
  }

  public onAnyEvent(callback: EventCallback): () => void {
    this.allEventListeners.add(callback);
    return () => {
      this.allEventListeners.delete(callback);
    };
  }

  public onStateChange(callback: StateChangeCallback): () => void {
    this.stateChangeListeners.add(callback);
    callback(this.state, this.url);
    return () => {
      this.stateChangeListeners.delete(callback);
    };
  }

  private setupSocketHandlers(): void {
    if (!this.ws) return;

    this.ws.onopen = () => {
      this.reconnectAttempts = 0;
      this.setState('CONNECTED');
    };

    this.ws.onmessage = (messageEvent: MessageEvent) => {
      try {
        const rawData = typeof messageEvent.data === 'string' ? messageEvent.data : new TextDecoder().decode(messageEvent.data);
        const eventEnvelope = JSON.parse(rawData) as EventEnvelope;

        // Synchronize active session ID from gateway
        if (eventEnvelope.session_id && eventEnvelope.session_id !== 'system' && eventEnvelope.session_id !== 'broadcast') {
          this.sessionId = eventEnvelope.session_id;
        } else if (eventEnvelope.payload?.session_id) {
          this.sessionId = eventEnvelope.payload.session_id;
        }

        // Dispatch to all-event listeners
        this.allEventListeners.forEach(cb => {
          try { cb(eventEnvelope); } catch (e) { console.error('[OrbitWS] Event listener error:', e); }
        });

        // Dispatch to specific event listeners
        const listeners = this.eventListeners.get(eventEnvelope.event_type);
        if (listeners) {
          listeners.forEach(cb => {
            try { cb(eventEnvelope); } catch (e) { console.error(`[OrbitWS] Listener error for ${eventEnvelope.event_type}:`, e); }
          });
        }
      } catch (err) {
        console.warn('[OrbitWS] Failed to parse incoming WebSocket message:', err);
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      if (this.state !== 'DISCONNECTED') {
        this.setState(this.autoReconnect ? 'RECONNECTING' : 'DISCONNECTED', `Socket closed (${event.code}): ${event.reason || 'Normal'}`);
        if (this.autoReconnect) {
          this.scheduleReconnect();
        }
      }
    };

    this.ws.onerror = (event: Event) => {
      this.setState('ERROR', 'WebSocket connection error');
    };
  }

  private setState(newState: ConnectionState, errorMsg?: string): void {
    this.state = newState;
    this.stateChangeListeners.forEach(cb => {
      try { cb(newState, this.url, errorMsg); } catch (e) { console.error('[OrbitWS] State listener error:', e); }
    });
  }

  private scheduleReconnect(): void {
    if (!this.autoReconnect || this.reconnectAttempts >= this.maxReconnectAttempts) {
      if (this.reconnectAttempts >= this.maxReconnectAttempts) {
        this.setState('ERROR', 'Max reconnection attempts reached. Backend unavailable.');
      }
      return;
    }

    this.clearReconnectTimer();
    const delay = Math.min(this.baseReconnectDelay * Math.pow(1.5, this.reconnectAttempts), 15000);
    this.reconnectAttempts++;

    this.reconnectTimer = window.setTimeout(() => {
      this.connect();
    }, delay);
  }

  private clearReconnectTimer(): void {
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
  }

  private generateUuid(): string {
    return 'cmd_' + Math.random().toString(36).substring(2, 9) + '_' + Date.now().toString(36);
  }
}

// Global Singleton Instance
export const orbitWS = new OrbitWebSocketClient();
