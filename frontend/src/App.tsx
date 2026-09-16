import React, { useState } from 'react';
import { SettingsProvider } from './context/SettingsContext';
import { OrbitProvider } from './context/OrbitContext';
import { ModelManagerProvider } from './context/ModelManagerContext';
import { SystemProvider } from './context/SystemContext';
import { SecurityProvider } from './context/SecurityContext';
import { TaskConsoleProvider } from './context/TaskConsoleContext';
import { ActivityHistoryProvider } from './context/ActivityHistoryContext';
import { SystemOverviewProvider } from './context/SystemOverviewContext';
import { DiagnosticsProvider } from './context/DiagnosticsContext';
import { Header } from './components/layout/Header';
import { ModeSwitch } from './components/layout/ModeSwitch';
import { HorizontalNav, TabId } from './components/navigation/HorizontalNav';
import { ConversationView } from './components/chat/ConversationView';
import { MessageInputArea } from './components/input/MessageInputArea';
import { SystemDisplaysView } from './components/system/SystemDisplaysView';
import { SecuritySafetyView } from './components/security/SecuritySafetyView';
import { TasksView } from './components/tasks/TasksView';
import { AppsView } from './components/apps/AppsView';
import { SettingsView } from './components/settings/SettingsView';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('chat');

  const renderActiveView = () => {
    switch (activeTab) {
      case 'chat':
        return (
          <>
            <ConversationView />
            <MessageInputArea />
          </>
        );
      case 'system':
        return <SystemDisplaysView onNavigateTab={(tab) => setActiveTab(tab as TabId)} />;
      case 'security':
        return <SecuritySafetyView />;
      case 'tasks':
        return <TasksView />;
      case 'apps':
        return <AppsView />;
      case 'settings':
        return <SettingsView />;
      default:
        return (
          <>
            <ConversationView />
            <MessageInputArea />
          </>
        );
    }
  };

  return (
    <SettingsProvider>
      <OrbitProvider>
        <ModelManagerProvider>
          <SystemProvider>
            <SecurityProvider>
              <TaskConsoleProvider>
                <ActivityHistoryProvider>
                  <SystemOverviewProvider>
                    <DiagnosticsProvider>
                      <div style={styles.appContainer}>
                        {/* 1. Header (Brand + Window Controls) */}
                        <Header onNavigateToChat={() => setActiveTab('chat')} />

                        {/* 2. Mode Switch (Chatbot vs Assistant) */}
                        <div style={styles.modeSwitchBar}>
                          <ModeSwitch />
                        </div>

                        {/* 3. Horizontal Navigation Tabs (Overview | Chat | Models | Health | System | Security | Activity | Apps | Settings) */}
                        <HorizontalNav activeTab={activeTab} onSelectTab={setActiveTab} />

                        {/* 4. Active View Content Area */}
                        <main style={styles.mainContent}>
                          {renderActiveView()}
                        </main>
                      </div>
                    </DiagnosticsProvider>
                  </SystemOverviewProvider>
                </ActivityHistoryProvider>
              </TaskConsoleProvider>
            </SecurityProvider>
          </SystemProvider>
        </ModelManagerProvider>
      </OrbitProvider>
    </SettingsProvider>
  );
};

const styles: Record<string, React.CSSProperties> = {
  appContainer: {
    width: '100vw',
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    backgroundColor: 'var(--bg-app)',
    overflow: 'hidden',
    position: 'relative',
  },
  modeSwitchBar: {
    padding: '0 18px 8px 18px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    userSelect: 'none',
  },
  mainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    minHeight: 0,
  },
};

export default App;
