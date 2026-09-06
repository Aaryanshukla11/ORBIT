import React from 'react';
import { SearchIcon, CloseIcon } from '../icons/Icons';
import { useActivityHistory } from '../../context/ActivityHistoryContext';

export const ActivityFilters: React.FC = () => {
  const { filter, setFilter, searchQuery, setSearchQuery, totalCount, runningCount, completedCount, failedCount, cancelledCount } =
    useActivityHistory();

  const filterOptions: Array<{ id: 'ALL' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED'; label: string; count: number }> = [
    { id: 'ALL', label: 'All', count: totalCount },
    { id: 'RUNNING', label: 'Running', count: runningCount },
    { id: 'COMPLETED', label: 'Completed', count: completedCount },
    { id: 'FAILED', label: 'Failed', count: failedCount },
    { id: 'CANCELLED', label: 'Cancelled', count: cancelledCount },
  ];

  return (
    <div style={styles.container}>
      {/* Search Input */}
      <div style={styles.searchWrapper}>
        <SearchIcon size={13} color="var(--text-muted)" />
        <input
          type="text"
          style={styles.searchInput}
          placeholder="Search tasks, models, apps..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button
            type="button"
            style={styles.clearBtn}
            onClick={() => setSearchQuery('')}
            title="Clear Search"
          >
            <CloseIcon size={12} color="var(--text-muted)" />
          </button>
        )}
      </div>

      {/* Filter Segmented Control */}
      <div style={styles.filterPills}>
        {filterOptions.map((opt) => {
          const isActive = filter === opt.id;
          return (
            <button
              key={opt.id}
              type="button"
              style={{
                ...styles.pillBtn,
                backgroundColor: isActive ? 'var(--bg-surface)' : 'transparent',
                color: isActive ? 'var(--accent-primary)' : 'var(--text-secondary)',
                fontWeight: isActive ? 700 : 500,
                boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.06)' : 'none',
              }}
              onClick={() => setFilter(opt.id)}
            >
              <span>{opt.label}</span>
              <span
                style={{
                  ...styles.countBadge,
                  backgroundColor: isActive ? 'rgba(37, 99, 235, 0.1)' : 'var(--bg-surface)',
                  color: isActive ? 'var(--accent-primary)' : 'var(--text-muted)',
                }}
              >
                {opt.count}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
};

const styles: Record<string, React.CSSProperties> = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
  },
  searchWrapper: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '6px 10px',
    backgroundColor: 'var(--bg-surface)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
  },
  searchInput: {
    flex: 1,
    border: 'none',
    outline: 'none',
    backgroundColor: 'transparent',
    fontSize: '11.5px',
    color: 'var(--text-primary)',
  },
  clearBtn: {
    background: 'none',
    border: 'none',
    padding: 0,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterPills: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    padding: '2px',
    backgroundColor: 'var(--bg-app)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    overflowX: 'auto',
  },
  pillBtn: {
    flex: 1,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '4px',
    padding: '4px 6px',
    borderRadius: '4px',
    border: 'none',
    fontSize: '10.5px',
    cursor: 'pointer',
    whiteSpace: 'nowrap',
    transition: 'all var(--transition-fast)',
  },
  countBadge: {
    fontSize: '9px',
    padding: '1px 4px',
    borderRadius: '8px',
    fontWeight: 700,
  },
};
