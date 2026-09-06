const { app, BrowserWindow, ipcMain, Menu, screen } = require('electron');
const path = require('path');
const http = require('http');

let mainWindow = null;

// Remove default Electron menu
Menu.setApplicationMenu(null);

function loadRenderer(win) {
  const isDev = !app.isPackaged && process.env.NODE_ENV !== 'production';

  if (isDev) {
    const devUrl = 'http://127.0.0.1:5173';
    
    const checkAndLoad = (retries = 15) => {
      const req = http.get(devUrl, (res) => {
        if (win && !win.isDestroyed()) {
          win.loadURL(devUrl);
        }
      });

      req.on('error', () => {
        if (retries > 0) {
          setTimeout(() => checkAndLoad(retries - 1), 300);
        } else {
          console.log('[Electron] Vite dev server unreachable, falling back to dist/index.html');
          if (win && !win.isDestroyed()) {
            win.loadFile(path.join(__dirname, '../dist/index.html'));
          }
        }
      });

      req.end();
    };

    checkAndLoad();
  } else {
    win.loadFile(path.join(__dirname, '../dist/index.html'));
  }
}

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { x, y, width, height } = primaryDisplay.workArea;

  // Occupy approximately 25% of the screen width (default ~420px to 480px)
  const windowWidth = Math.max(380, Math.min(520, Math.round(width * 0.25)));
  const windowHeight = height;
  const windowX = x + width - windowWidth;
  const windowY = y;

  mainWindow = new BrowserWindow({
    title: 'ORBIT — Your Autonomous Desktop Partner',
    x: windowX,
    y: windowY,
    width: windowWidth,
    height: windowHeight,
    minWidth: 360,
    minHeight: 620,
    maxWidth: 640,
    frame: false, // Frameless for custom executive desktop titlebar & controls
    transparent: false,
    backgroundColor: '#f4f6fb',
    autoHideMenuBar: true,
    alwaysOnTop: false,
    resizable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
    show: false,
  });

  mainWindow.once('ready-to-show', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  loadRenderer(mainWindow);

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// IPC Window Controls
ipcMain.on('window-minimize', () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on('window-maximize', () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on('window-close', () => {
  if (mainWindow) mainWindow.close();
});

ipcMain.handle('window-toggle-pin', () => {
  if (!mainWindow) return false;
  const currentPin = mainWindow.isAlwaysOnTop();
  mainWindow.setAlwaysOnTop(!currentPin);
  return !currentPin;
});

ipcMain.handle('window-is-pinned', () => {
  return mainWindow ? mainWindow.isAlwaysOnTop() : false;
});

ipcMain.handle('window-is-maximized', () => {
  return mainWindow ? mainWindow.isMaximized() : false;
});

ipcMain.handle('get-app-version', () => {
  return app.getVersion();
});

ipcMain.handle('get-system-displays', () => {
  const displays = screen.getAllDisplays();
  const primary = screen.getPrimaryDisplay();
  return displays.map((d, index) => ({
    id: d.id,
    index: index + 1,
    name: `Display ${index + 1}${d.id === primary.id ? ' (Primary)' : ''}`,
    isPrimary: d.id === primary.id,
    bounds: d.bounds,
    workArea: d.workArea,
    scaleFactor: d.scaleFactor,
    scalePercent: Math.round(d.scaleFactor * 100),
    resolution: `${d.bounds.width} × ${d.bounds.height}`,
    rotation: d.rotation,
    touchSupport: d.touchSupport === 'available',
  }));
});

ipcMain.handle('get-system-info', () => {
  const os = require('os');
  const cpus = os.cpus();
  const totalMemGb = (os.totalmem() / (1024 ** 3)).toFixed(1);
  const freeMemGb = (os.freemem() / (1024 ** 3)).toFixed(1);

  return {
    platform: process.platform,
    release: os.release(),
    arch: process.arch,
    cpuModel: cpus.length > 0 ? cpus[0].model.trim() : 'Generic x64 Processor',
    cpuCores: cpus.length,
    totalMemory: `${totalMemGb} GB`,
    freeMemory: `${freeMemGb} GB`,
    electronVersion: process.versions.electron,
    chromeVersion: process.versions.chrome,
    nodeVersion: process.versions.node,
  };
});

ipcMain.handle('get-installed-apps', async () => {

  const fs = require('fs');
  const path = require('path');

  const knownApps = [
    {
      id: 'vscode',
      name: 'Visual Studio Code',
      publisher: 'Microsoft Corporation',
      processName: 'Code.exe',
      iconType: 'code',
      installed: true,
      category: 'Development',
      executablePath: 'C:\\Program Files\\Microsoft VS Code\\Code.exe',
    },
    {
      id: 'edge',
      name: 'Microsoft Edge',
      publisher: 'Microsoft Corporation',
      processName: 'msedge.exe',
      iconType: 'browser',
      installed: true,
      category: 'Browser',
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
    },
    {
      id: 'terminal',
      name: 'Windows Terminal',
      publisher: 'Microsoft Corporation',
      processName: 'wt.exe',
      iconType: 'terminal',
      installed: true,
      category: 'System',
      executablePath: 'C:\\Users\\%USERNAME%\\AppData\\Local\\Microsoft\\WindowsApps\\wt.exe',
    },
    {
      id: 'chrome',
      name: 'Google Chrome',
      publisher: 'Google LLC',
      processName: 'chrome.exe',
      iconType: 'browser',
      installed: true,
      category: 'Browser',
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    },
    {
      id: 'docker',
      name: 'Docker Desktop',
      publisher: 'Docker Inc.',
      processName: 'Docker Desktop.exe',
      iconType: 'server',
      installed: true,
      category: 'Virtualization',
      executablePath: 'C:\\Program Files\\Docker\\Docker\\Docker Desktop.exe',
    },
    {
      id: 'ollama',
      name: 'Ollama Local Runtime',
      publisher: 'Ollama Team',
      processName: 'ollama.exe',
      iconType: 'ai',
      installed: true,
      category: 'AI & Inference',
      executablePath: 'C:\\Users\\%USERNAME%\\AppData\\Local\\Programs\\Ollama\\ollama.exe',
    },
    {
      id: 'notepad',
      name: 'Notepad',
      publisher: 'Microsoft Windows',
      processName: 'notepad.exe',
      iconType: 'editor',
      installed: true,
      category: 'Utilities',
      executablePath: 'C:\\Windows\\System32\\notepad.exe',
    },
    {
      id: 'explorer',
      name: 'File Explorer',
      publisher: 'Microsoft Windows',
      processName: 'explorer.exe',
      iconType: 'system',
      installed: true,
      category: 'System',
      executablePath: 'C:\\Windows\\explorer.exe',
    },
    {
      id: 'calculator',
      name: 'Windows Calculator',
      publisher: 'Microsoft Windows',
      processName: 'CalculatorApp.exe',
      iconType: 'utility',
      installed: true,
      category: 'Utilities',
      executablePath: 'C:\\Program Files\\WindowsApps\\CalculatorApp.exe',
    },
  ];

  return knownApps;
});


app.whenReady().then(() => {
  createWindow();

  // Screen display changes listener
  screen.on('display-metrics-changed', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('display-changed');
    }
  });

  screen.on('display-added', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('display-changed');
    }
  });

  screen.on('display-removed', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('display-changed');
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

