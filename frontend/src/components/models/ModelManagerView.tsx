import React from 'react';
import { ModelHeader } from './ModelHeader';
import { ActiveModelCard } from './ActiveModelCard';
import { SourceSwitcher } from './SourceSwitcher';
import { LocalModelsList } from './LocalModelsList';
import { CloudModelsList } from './CloudModelsList';
import { SystemModelStatus } from './SystemModelStatus';
import { useModelManager } from '../../context/ModelManagerContext';

interface ModelManagerViewProps {
  onBack?: () => void;
}

export const ModelManagerView: React.FC<ModelManagerViewProps> = ({ onBack }) => {
  const { sourceTab } = useModelManager();

  return (
    <div style={styles.container}>
      {/* 1. Header with back button & status */}
      <div style={styles.headerWrapper}>
        <ModelHeader onBack={onBack} />
      </div>

      {/* 2. Scrollable content body */}
      <div style={styles.scrollArea}>
        {/* Active Hero Card */}
        <ActiveModelCard />

        {/* Source Switcher (Local | Cloud) */}
        <SourceSwitcher />

        {/* Dynamic Model List */}
        {sourceTab === 'local' ? <LocalModelsList /> : <CloudModelsList />}

        {/* System Model Runtime State Strip */}
        <SystemModelStatus />
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
  },
  headerWrapper: {
    padding: '0 18px',
  },
  scrollArea: {
    flex: 1,
    overflowY: 'auto',
    overflowX: 'hidden',
    padding: '12px 18px 24px 18px',
    display: 'flex',
    flexDirection: 'column',
    gap: '12px',
  },
};
