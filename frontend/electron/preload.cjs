const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('orbitDesktop', {
  platform: process.platform,
  minimize: () => ipcRenderer.send('window-minimize'),
  maximize: () => ipcRenderer.send('window-maximize'),
  close: () => ipcRenderer.send('window-close'),
  togglePin: () => ipcRenderer.invoke('window-toggle-pin'),
  isPinned: () => ipcRenderer.invoke('window-is-pinned'),
  isMaximized: () => ipcRenderer.invoke('window-is-maximized'),
  getAppVersion: () => ipcRenderer.invoke('get-app-version'),
  getSystemDisplays: () => ipcRenderer.invoke('get-system-displays'),
  getSystemInfo: () => ipcRenderer.invoke('get-system-info'),
  getInstalledApps: () => ipcRenderer.invoke('get-installed-apps'),
  onDisplayChanged: (callback) => {
    const handler = () => callback();
    ipcRenderer.on('display-changed', handler);
    return () => ipcRenderer.removeListener('display-changed', handler);
  },
});


