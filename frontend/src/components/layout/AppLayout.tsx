import React from 'react';
import { Sidebar } from './Sidebar';
import { TopBar } from './TopBar';
import { StatusBar } from './StatusBar';

interface AppLayoutProps {
  children: React.ReactNode;
}

export const AppLayout: React.FC<AppLayoutProps> = ({ children }) => {
  return (
    <div style={styles.container}>
      {/* Left Sidebar */}
      <Sidebar />

      {/* Main App Canvas */}
      <div style={styles.mainCanvas}>
        {/* Top Desktop Bar */}
        <TopBar />

        {/* Content Area */}
        <main style={styles.contentArea}>
          {children}
        </main>

        {/* Bottom Status Bar */}
        <StatusBar />
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    width: '100vw',
    height: '100vh',
    display: 'flex',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  mainCanvas: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    height: '100%',
    overflow: 'hidden',
    backgroundColor: 'var(--bg-app)',
  },
  contentArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: 'var(--space-6)',
    position: 'relative',
  },
};
