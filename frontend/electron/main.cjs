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
  const { execSync } = require('child_process');

  // Query running process names
  const runningProcesses = new Set();
  try {
    const stdout = execSync('tasklist /fo csv /nh', { encoding: 'utf-8', timeout: 2500 });
    const lines = stdout.trim().split('\n');
    for (const line of lines) {
      const match = line.match(/^"([^"]+)"/);
      if (match) runningProcesses.add(match[1].toLowerCase());
    }
  } catch (err) {
    console.warn('[Electron] tasklist query notice:', err.message);
  }

  const userProfile = process.env.USERPROFILE || 'C:\\Users\\' + (process.env.USERNAME || 'User');
  const localAppData = process.env.LOCALAPPDATA || path.join(userProfile, 'AppData', 'Local');

  const knownApps = [
    {
      id: 'notepad',
      name: 'Notepad',
      publisher: 'Microsoft Windows',
      processName: 'notepad.exe',
      iconType: 'editor',
      category: 'Utilities',
      executablePath: 'C:\\Windows\\System32\\notepad.exe',
      launchCommand: 'notepad.exe',
    },
    {
      id: 'paint',
      name: 'Paint',
      publisher: 'Microsoft Windows',
      processName: 'mspaint.exe',
      iconType: 'editor',
      category: 'Utilities',
      executablePath: 'C:\\Windows\\System32\\mspaint.exe',
      launchCommand: 'mspaint.exe',
    },
    {
      id: 'vscode',
      name: 'Visual Studio Code',
      publisher: 'Microsoft Corporation',
      processName: 'Code.exe',
      iconType: 'code',
      category: 'Development',
      executablePath: path.join(localAppData, 'Programs', 'Microsoft VS Code', 'Code.exe'),
      launchCommand: 'code',
    },
    {
      id: 'terminal',
      name: 'Windows Terminal',
      publisher: 'Microsoft Corporation',
      processName: 'wt.exe',
      iconType: 'terminal',
      category: 'System',
      executablePath: path.join(localAppData, 'Microsoft', 'WindowsApps', 'wt.exe'),
      launchCommand: 'wt.exe',
    },
    {
      id: 'edge',
      name: 'Microsoft Edge',
      publisher: 'Microsoft Corporation',
      processName: 'msedge.exe',
      iconType: 'browser',
      category: 'Browser',
      executablePath: 'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe',
      launchCommand: 'msedge.exe',
    },
    {
      id: 'chrome',
      name: 'Google Chrome',
      publisher: 'Google LLC',
      processName: 'chrome.exe',
      iconType: 'browser',
      category: 'Browser',
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      launchCommand: 'chrome.exe',
    },
    {
      id: 'brave',
      name: 'Brave Browser',
      publisher: 'Brave Software Inc.',
      processName: 'brave.exe',
      iconType: 'browser',
      category: 'Browser',
      executablePath: 'C:\\Program Files\\BraveSoftware\\Brave-Browser\\Application\\brave.exe',
      launchCommand: 'brave.exe',
    },
    {
      id: 'ollama',
      name: 'Ollama Local Runtime',
      publisher: 'Ollama Team',
      processName: 'ollama.exe',
      iconType: 'ai',
      category: 'AI & Inference',
      executablePath: path.join(localAppData, 'Programs', 'Ollama', 'ollama.exe'),
      launchCommand: 'ollama.exe',
    },
    {
      id: 'explorer',
      name: 'File Explorer',
      publisher: 'Microsoft Windows',
      processName: 'explorer.exe',
      iconType: 'system',
      category: 'System',
      executablePath: 'C:\\Windows\\explorer.exe',
      launchCommand: 'explorer.exe',
    },
    {
      id: 'calculator',
      name: 'Windows Calculator',
      publisher: 'Microsoft Windows',
      processName: 'CalculatorApp.exe',
      iconType: 'utility',
      category: 'Utilities',
      executablePath: 'C:\\Windows\\System32\\calc.exe',
      launchCommand: 'calc.exe',
    },
  ];

  return knownApps.map((app) => {
    let existsOnDisk = false;
    try {
      existsOnDisk = fs.existsSync(app.executablePath);
    } catch {
      existsOnDisk = false;
    }
    const isRunning = runningProcesses.has(app.processName.toLowerCase()) || 
                      (app.id === 'notepad' && runningProcesses.has('notepad.exe')) ||
                      (app.id === 'calculator' && (runningProcesses.has('calculatorapp.exe') || runningProcesses.has('calc.exe')));

    return {
      ...app,
      installed: existsOnDisk || isRunning,
      isRunning: isRunning,
      state: isRunning ? 'Running (Active Process)' : existsOnDisk ? 'Installed (Idle)' : 'Not Installed',
      windowTitle: isRunning ? `${app.name} • Active in OS` : 'Ready to Launch',
    };
  });
});

ipcMain.handle('launch-app', async (_, launchCommand) => {
  const { spawn } = require('child_process');
  try {
    const child = spawn(launchCommand, [], {
      detached: true,
      stdio: 'ignore',
      shell: true,
    });
    child.unref();
    return { success: true, message: `Launched ${launchCommand}` };
  } catch (err) {
    return { success: false, error: err.message };
  }
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

