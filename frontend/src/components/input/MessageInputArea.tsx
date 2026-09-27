import React, { useState, useRef, useEffect, useCallback } from 'react';
import {
  ExpandScanIcon,
  SendNavigationArrowIcon,
  PaperclipIcon,
  MicIcon,
  ChevronDownIcon,
  CheckIcon,
  CloseIcon,
  GptHexagonIcon,
  HardDriveIcon,
} from '../icons/Icons';
import { useTaskConsole } from '../../context/TaskConsoleContext';
import { useModelManager, isSameModel } from '../../context/ModelManagerContext';

interface MessageInputAreaProps {
  onSendMessage?: (text: string) => void;
}

export const MessageInputArea: React.FC<MessageInputAreaProps> = ({ onSendMessage }) => {
  const [text, setText] = useState('');
  const [isModelDropdownOpen, setIsModelDropdownOpen] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [attachedFiles, setAttachedFiles] = useState<File[]>([]);
  const [scanNotice, setScanNotice] = useState<string | null>(null);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const modelDropdownRef = useRef<HTMLDivElement>(null);
  const recognitionRef = useRef<any>(null);

  const { inputMode, sendUserMessage, isProcessing } = useTaskConsole();
  const { models, cloudProviders, activeModelId, activeModel, switchModel, switchingModelId } = useModelManager();

  const isAssistant = inputMode === 'task';

  // Auto-resize textarea as text grows
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(Math.max(textareaRef.current.scrollHeight, 28), 120)}px`;
    }
  }, [text]);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (modelDropdownRef.current && !modelDropdownRef.current.contains(e.target as Node)) {
        setIsModelDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Web Speech API for voice dictation
  const toggleSpeechRecognition = useCallback(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert('Voice dictation is not supported in this environment.');
      return;
    }

    if (isListening) {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
      };

      recognition.onresult = (event: any) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; i++) {
          transcript += event.results[i][0].transcript;
        }
        if (transcript) {
          setText((prev) => (prev ? `${prev} ${transcript.trim()}` : transcript.trim()));
        }
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
      recognitionRef.current = recognition;
    } catch (err) {
      console.warn('Speech recognition error:', err);
      setIsListening(false);
    }
  }, [isListening]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleSend = () => {
    if (!text.trim() && attachedFiles.length === 0) return;

    let fullPrompt = text.trim();
    if (attachedFiles.length > 0) {
      const fileNames = attachedFiles.map((f) => f.name).join(', ');
      fullPrompt += ` [Attached Files: ${fileNames}]`;
    }

    if (onSendMessage) {
      onSendMessage(fullPrompt);
    } else {
      sendUserMessage(fullPrompt, inputMode);
    }

    setText('');
    setAttachedFiles([]);
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setAttachedFiles((prev) => [...prev, ...Array.from(e.target.files || [])]);
    }
  };

  const handleTriggerScreenScan = () => {
    setScanNotice('Desktop perception snapshot attached to task.');
    setTimeout(() => setScanNotice(null), 3000);
  };

  // Resolve current active model display name (e.g. GPT-4o, Qwen2.5 7.6B, etc.)
  const currentModelDisplayName =
    activeModel?.name ||
    (activeModelId ? activeModelId.replace(/^cloud:openai:|^ollama:/i, '').toUpperCase() : 'AI model name');

  return (
    <div style={styles.outerWrapper}>
      <div style={styles.cardContainer}>
        {/* Top Input Row */}
        <div style={styles.topRow}>
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isAssistant
                ? 'Ask ORBIT to automate your desktop (e.g. Open Notepad, calculate)...'
                : 'Chat with ORBIT AI (conversations, coding, questions)...'
            }
            rows={1}
            style={styles.textarea}
          />

          <div style={styles.topRightActions}>
            {/* Screen Region / Focus Button */}
            <button
              type="button"
              style={styles.scanBtn}
              onClick={handleTriggerScreenScan}
              title="Capture active screen context for grounding"
            >
              <ExpandScanIcon size={18} color="#94a3b8" />
            </button>

            {/* Send Button */}
            <button
              type="button"
              style={{
                ...styles.sendBtn,
                opacity: text.trim() || attachedFiles.length > 0 ? 1 : 0.85,
                transform: text.trim() ? 'scale(1.02)' : 'none',
              }}
              onClick={handleSend}
              disabled={isProcessing}
              title="Send Goal / Instruction (Enter)"
            >
              <SendNavigationArrowIcon size={18} color="#0f172a" />
            </button>
          </div>
        </div>

        {/* Attached Files Strip (if any) */}
        {attachedFiles.length > 0 && (
          <div style={styles.attachedFilesStrip}>
            {attachedFiles.map((file, idx) => (
              <div key={idx} style={styles.fileChip}>
                <PaperclipIcon size={11} color="var(--accent-primary)" />
                <span style={styles.fileChipText}>{file.name}</span>
                <button
                  type="button"
                  onClick={() => setAttachedFiles((prev) => prev.filter((_, i) => i !== idx))}
                  style={styles.fileChipClose}
                >
                  <CloseIcon size={10} color="#64748b" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Temporary Scan Notice */}
        {scanNotice && (
          <div style={styles.scanNoticeBanner}>
            <span>{scanNotice}</span>
          </div>
        )}

        {/* Bottom Actions Row: [AI Model Pill] ... [Attachment] [Mic] */}
        <div style={styles.bottomRow}>
          <div style={styles.leftPillsGroup}>
            {/* AI Model Switcher Pill */}
            <div ref={modelDropdownRef} style={{ position: 'relative' }}>
              <button
                type="button"
                style={{
                  ...styles.modelPill,
                  borderColor: isModelDropdownOpen ? 'var(--accent-primary)' : '#bfdbfe',
                }}
                onClick={() => {
                  setIsModelDropdownOpen(!isModelDropdownOpen);
                }}
                title="Select active AI model"
              >
                <span style={styles.modelPillText}>{currentModelDisplayName}</span>
                <ChevronDownIcon size={12} color="#64748b" />
              </button>

              {/* Model Dropdown Menu */}
              {isModelDropdownOpen && (
                <div style={styles.floatingMenu}>
                  <div style={styles.menuHeader}>
                    <span>Select Model</span>
                  </div>

                  {/* Cloud Models Category */}
                  <div style={styles.categoryTitle}>Cloud Models</div>
                  {cloudProviders.flatMap((p) => p.models).map((mName) => {
                    const fullId = `cloud:openai:${mName}`;
                    const isActive = isSameModel(activeModelId, fullId) || isSameModel(activeModelId, mName);
                    const isSwitching = switchingModelId === fullId || switchingModelId === mName;

                    return (
                      <button
                        key={mName}
                        type="button"
                        style={{
                          ...styles.menuItem,
                          backgroundColor: isActive ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
                        }}
                        onClick={() => {
                          switchModel(fullId);
                          setIsModelDropdownOpen(false);
                        }}
                      >
                        <div style={styles.menuItemLeft}>
                          <GptHexagonIcon size={14} color={isActive ? 'var(--accent-primary)' : '#64748b'} />
                          <span style={{ ...styles.menuItemText, fontWeight: isActive ? 700 : 500 }}>
                            {mName}
                          </span>
                        </div>
                        {isActive && <CheckIcon size={13} color="var(--accent-primary)" />}
                        {isSwitching && <span style={styles.switchingBadge}>Switching...</span>}
                      </button>
                    );
                  })}

                  {/* Local Models Category */}
                  <div style={styles.categoryTitle}>Local Models</div>
                  {models.map((m) => {
                    const isActive = isSameModel(activeModelId, m.id);
                    const isSwitching = switchingModelId === m.id;

                    return (
                      <button
                        key={m.id}
                        type="button"
                        style={{
                          ...styles.menuItem,
                          backgroundColor: isActive ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
                        }}
                        onClick={() => {
                          switchModel(m.id);
                          setIsModelDropdownOpen(false);
                        }}
                      >
                        <div style={styles.menuItemLeft}>
                          <HardDriveIcon size={14} color={isActive ? 'var(--accent-primary)' : '#64748b'} />
                          <span style={{ ...styles.menuItemText, fontWeight: isActive ? 700 : 500 }}>
                            {m.name || m.id}
                          </span>
                        </div>
                        {isActive && <CheckIcon size={13} color="var(--accent-primary)" />}
                        {isSwitching && <span style={styles.switchingBadge}>Switching...</span>}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Right Action Icons (Attachment & Microphone) */}
          <div style={styles.rightActionsGroup}>
            {/* Hidden File Input */}
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              style={{ display: 'none' }}
              multiple
            />

            {/* Attachment Button */}
            <button
              type="button"
              style={styles.roundActionBtn}
              onClick={() => fileInputRef.current?.click()}
              title="Attach screenshot or file"
            >
              <PaperclipIcon size={16} color="#475569" />
            </button>

            {/* Microphone Voice Button */}
            <button
              type="button"
              style={{
                ...styles.roundActionBtn,
                backgroundColor: isListening ? '#fee2e2' : '#f1f5f9',
                borderColor: isListening ? '#ef4444' : 'transparent',
              }}
              onClick={toggleSpeechRecognition}
              title={isListening ? 'Stop listening' : 'Start voice dictation'}
            >
              <MicIcon size={16} color={isListening ? '#dc2626' : '#475569'} />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  outerWrapper: {
    padding: '0 20px 20px 20px',
    backgroundColor: 'var(--bg-app)',
    flexShrink: 0,
  },
  cardContainer: {
    backgroundColor: '#ffffff',
    border: '1.5px solid #e2e8f0',
    borderRadius: '26px',
    padding: '16px 18px 12px 18px',
    boxShadow: '0 8px 30px rgba(0, 0, 0, 0.06)',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
    transition: 'border-color 0.2s ease, box-shadow 0.2s ease',
  },
  topRow: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '12px',
  },
  textarea: {
    flex: 1,
    backgroundColor: 'transparent',
    border: 'none',
    color: '#1e293b',
    fontFamily: 'var(--font-sans)',
    fontSize: '15px',
    lineHeight: 1.5,
    resize: 'none',
    outline: 'none',
    padding: '4px 0',
    minHeight: '28px',
  },
  topRightActions: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    flexShrink: 0,
  },
  scanBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 36,
    height: 36,
    borderRadius: '10px',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  sendBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 44,
    height: 44,
    borderRadius: '16px',
    border: 'none',
    backgroundColor: '#2563eb',
    cursor: 'pointer',
    transition: 'all 0.2s ease',
    boxShadow: '0 4px 14px rgba(37, 99, 235, 0.35)',
  },
  bottomRow: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingTop: '2px',
  },
  leftPillsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  rightActionsGroup: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  modelPill: {
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    padding: '6px 14px',
    borderRadius: '9999px',
    backgroundColor: '#eff6ff',
    border: '1.5px solid #bfdbfe',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  modelPillText: {
    fontSize: '13px',
    fontWeight: 700,
    color: '#1e293b',
    letterSpacing: '-0.01em',
  },
  roundActionBtn: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    width: 36,
    height: 36,
    borderRadius: '50%',
    backgroundColor: '#f1f5f9',
    border: '1px solid transparent',
    cursor: 'pointer',
    transition: 'all 0.15s ease',
  },
  floatingMenu: {
    position: 'absolute',
    bottom: 'calc(100% + 8px)',
    left: 0,
    backgroundColor: '#ffffff',
    border: '1px solid #e2e8f0',
    borderRadius: '16px',
    boxShadow: '0 12px 32px rgba(0, 0, 0, 0.12)',
    padding: '6px',
    minWidth: '220px',
    zIndex: 1000,
    display: 'flex',
    flexDirection: 'column',
    gap: '2px',
  },
  menuHeader: {
    padding: '6px 10px 4px 10px',
    fontSize: '11px',
    fontWeight: 700,
    textTransform: 'uppercase',
    color: '#94a3b8',
    letterSpacing: '0.05em',
  },
  categoryTitle: {
    padding: '6px 10px 2px 10px',
    fontSize: '11px',
    fontWeight: 700,
    color: '#64748b',
  },
  menuItem: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '8px 10px',
    borderRadius: '10px',
    border: 'none',
    backgroundColor: 'transparent',
    cursor: 'pointer',
    textAlign: 'left',
    width: '100%',
    transition: 'background-color 0.15s ease',
  },
  menuItemLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
  },
  menuItemText: {
    fontSize: '13px',
    color: '#1e293b',
  },
  switchingBadge: {
    fontSize: '11px',
    color: 'var(--accent-primary)',
    fontWeight: 600,
  },
  attachedFilesStrip: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '6px',
    paddingBottom: '2px',
  },
  fileChip: {
    display: 'flex',
    alignItems: 'center',
    gap: '5px',
    backgroundColor: '#f1f5f9',
    borderRadius: '8px',
    padding: '3px 8px',
    border: '1px solid #e2e8f0',
  },
  fileChipText: {
    fontSize: '12px',
    color: '#334155',
    maxWidth: '160px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  fileChipClose: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    padding: 0,
  },
  scanNoticeBanner: {
    backgroundColor: '#eff6ff',
    border: '1px solid #bfdbfe',
    borderRadius: '8px',
    padding: '4px 10px',
    fontSize: '12px',
    color: '#1e40af',
  },
};
