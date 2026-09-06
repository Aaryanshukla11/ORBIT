import React, { useState } from 'react';
import { OrbitProvider } from './context/OrbitContext';
import { ModelManagerProvider } from './context/ModelManagerContext';
import { SystemProvider } from './context/SystemContext';
import { SecurityProvider } from './context/SecurityContext';
import { TaskConsoleProvider } from './context/TaskConsoleContext';
import { ActivityHistoryProvider } from './context/ActivityHistoryContext';
import { SystemOverviewProvider } from './context/SystemOverviewContext';
import { DiagnosticsProvider } from './context/DiagnosticsContext';
import { Header } from './components/layout/Header';
import { StatusArea } from './components/status/StatusArea';
import { HorizontalNav, TabId } from './components/navigation/HorizontalNav';
import { SystemOverviewView } from './components/overview/SystemOverviewView';
import { ConversationView } from './components/chat/ConversationView';
import { MessageInputArea } from './components/input/MessageInputArea';
import { ModelManagerView } from './components/models/ModelManagerView';
import { DiagnosticsView } from './components/diagnostics/DiagnosticsView';
import { SystemDisplaysView } from './components/system/SystemDisplaysView';
import { SecuritySafetyView } from './components/security/SecuritySafetyView';
import { TasksView } from './components/tasks/TasksView';
import { ActivityView } from './components/activity/ActivityView';
import { AppsView } from './components/apps/AppsView';
import { SettingsView } from './components/settings/SettingsView';

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('chat');

  const renderActiveView = () => {
    switch (activeTab) {
      case 'overview':
        return <SystemOverviewView onNavigateTab={(tab) => setActiveTab(tab)} />;
      case 'chat':
        return (
          <>
            <ConversationView />
            <MessageInputArea />
          </>
        );
      case 'models':
        return <ModelManagerView onBack={() => setActiveTab('chat')} />;
      case 'health':
        return <DiagnosticsView onNavigateTab={(tab) => setActiveTab(tab as TabId)} />;
      case 'system':
        return <SystemDisplaysView />;
      case 'security':
        return <SecuritySafetyView />;
      case 'tasks':
        return <TasksView />;
      case 'activity':
        return <ActivityView />;
      case 'apps':
        return <AppsView />;
      case 'settings':
        return <SettingsView />;
      default:
        return <ConversationView />;
    }
  };

  return (
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
                      <Header />

                      {/* 2. Status Area (Online -> Health / Diagnostics, Model -> Model Manager) */}
                      <StatusArea
                        onOpenSystem={() => setActiveTab('health')}
                        onOpenModelManager={() => setActiveTab('models')}
                      />

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
  mainContent: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    minHeight: 0,
  },
};

export default App;
