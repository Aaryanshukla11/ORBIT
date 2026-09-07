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
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  mainWindow.webContents.on('did-finish-load', () => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
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

const appIconCache = new Map();

ipcMain.handle('get-installed-apps', async () => {
  const fs = require('fs');
  const path = require('path');
  const { exec } = require('child_process');
  const util = require('util');
  const execAsync = util.promisify(exec);

  // 1. Query running processes in Windows
  const runningProcesses = new Set();
  try {
    const { stdout } = await execAsync('tasklist /fo csv /nh', { timeout: 3000, windowsHide: true });
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
  const progFiles = process.env['ProgramFiles'] || 'C:\\Program Files';
  const progFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
  const winDir = process.env.WINDIR || 'C:\\Windows';

  // 2. Comprehensive catalog of core Windows OS tools and popular software
  const baseCatalog = [
    // --- System & OS Core ---
    {
      id: 'explorer',
      name: 'File Explorer',
      publisher: 'Microsoft Windows',
      processName: 'explorer.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'explorer.exe'),
      launchCommand: 'explorer.exe',
    },
    {
      id: 'taskmgr',
      name: 'Task Manager',
      publisher: 'Microsoft Windows',
      processName: 'Taskmgr.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'Taskmgr.exe'),
      launchCommand: 'taskmgr.exe',
    },
    {
      id: 'terminal',
      name: 'Windows Terminal',
      publisher: 'Microsoft Corporation',
      processName: 'wt.exe',
      iconType: 'terminal',
      category: 'System & OS',
      executablePath: path.join(localAppData, 'Microsoft', 'WindowsApps', 'wt.exe'),
      launchCommand: 'wt.exe',
    },
    {
      id: 'powershell',
      name: 'Windows PowerShell',
      publisher: 'Microsoft Windows',
      processName: 'powershell.exe',
      iconType: 'terminal',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe'),
      launchCommand: 'powershell.exe',
    },
    {
      id: 'cmd',
      name: 'Command Prompt',
      publisher: 'Microsoft Windows',
      processName: 'cmd.exe',
      iconType: 'terminal',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'cmd.exe'),
      launchCommand: 'cmd.exe',
    },
    {
      id: 'regedit',
      name: 'Registry Editor',
      publisher: 'Microsoft Windows',
      processName: 'regedit.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'regedit.exe'),
      launchCommand: 'regedit.exe',
    },
    {
      id: 'control',
      name: 'Control Panel',
      publisher: 'Microsoft Windows',
      processName: 'control.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'control.exe'),
      launchCommand: 'control.exe',
    },
    {
      id: 'services',
      name: 'Services Manager',
      publisher: 'Microsoft Windows',
      processName: 'mmc.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'services.msc'),
      launchCommand: 'services.msc',
    },
    {
      id: 'devmgmt',
      name: 'Device Manager',
      publisher: 'Microsoft Windows',
      processName: 'mmc.exe',
      iconType: 'system',
      category: 'System & OS',
      executablePath: path.join(winDir, 'System32', 'devmgmt.msc'),
      launchCommand: 'devmgmt.msc',
    },
    // --- Utilities & Accessories ---
    {
      id: 'notepad',
      name: 'Notepad',
      publisher: 'Microsoft Windows',
      processName: 'notepad.exe',
      iconType: 'editor',
      category: 'Utilities',
      executablePath: path.join(winDir, 'System32', 'notepad.exe'),
      launchCommand: 'notepad.exe',
    },
    {
      id: 'paint',
      name: 'Paint',
      publisher: 'Microsoft Windows',
      processName: 'mspaint.exe',
      iconType: 'editor',
      category: 'Utilities',
      executablePath: path.join(winDir, 'System32', 'mspaint.exe'),
      launchCommand: 'mspaint.exe',
    },
    {
      id: 'calculator',
      name: 'Windows Calculator',
      publisher: 'Microsoft Windows',
      processName: 'CalculatorApp.exe',
      iconType: 'utility',
      category: 'Utilities',
      executablePath: path.join(winDir, 'System32', 'calc.exe'),
      launchCommand: 'calc.exe',
    },
    {
      id: 'snippingtool',
      name: 'Snipping Tool',
      publisher: 'Microsoft Windows',
      processName: 'SnippingTool.exe',
      iconType: 'utility',
      category: 'Utilities',
      executablePath: path.join(winDir, 'System32', 'SnippingTool.exe'),
      launchCommand: 'SnippingTool.exe',
    },
    // --- Web Browsers ---
    {
      id: 'edge',
      name: 'Microsoft Edge',
      publisher: 'Microsoft Corporation',
      processName: 'msedge.exe',
      iconType: 'browser',
      category: 'Browsers',
      executablePath: path.join(progFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      launchCommand: 'msedge.exe',
    },
    {
      id: 'chrome',
      name: 'Google Chrome',
      publisher: 'Google LLC',
      processName: 'chrome.exe',
      iconType: 'browser',
      category: 'Browsers',
      executablePath: path.join(progFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      launchCommand: 'chrome.exe',
    },
    {
      id: 'brave',
      name: 'Brave Browser',
      publisher: 'Brave Software Inc.',
      processName: 'brave.exe',
      iconType: 'browser',
      category: 'Browsers',
      executablePath: path.join(progFiles, 'BraveSoftware', 'Brave-Browser', 'Application', 'brave.exe'),
      launchCommand: 'brave.exe',
    },
    {
      id: 'firefox',
      name: 'Mozilla Firefox',
      publisher: 'Mozilla Corporation',
      processName: 'firefox.exe',
      iconType: 'browser',
      category: 'Browsers',
      executablePath: path.join(progFiles, 'Mozilla Firefox', 'firefox.exe'),
      launchCommand: 'firefox.exe',
    },
    // --- Development & Engineering ---
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
      id: 'git',
      name: 'Git for Windows',
      publisher: 'Git Development Community',
      processName: 'git.exe',
      iconType: 'terminal',
      category: 'Development',
      executablePath: path.join(progFiles, 'Git', 'cmd', 'git.exe'),
      launchCommand: 'git.exe',
    },
    {
      id: 'docker',
      name: 'Docker Desktop',
      publisher: 'Docker Inc.',
      processName: 'Docker Desktop.exe',
      iconType: 'system',
      category: 'Development',
      executablePath: path.join(progFiles, 'Docker', 'Docker', 'Docker Desktop.exe'),
      launchCommand: 'Docker Desktop.exe',
    },
    {
      id: 'android_studio',
      name: 'Android Studio',
      publisher: 'Google LLC',
      processName: 'studio64.exe',
      iconType: 'code',
      category: 'Development',
      executablePath: path.join(progFiles, 'Android', 'Android Studio', 'bin', 'studio64.exe'),
      launchCommand: 'studio64.exe',
    },
    // --- AI & Inference ---
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
      id: 'orbit_gateway',
      name: 'ORBIT Python Gateway',
      publisher: 'ORBIT Core Engine',
      processName: 'python.exe',
      iconType: 'ai',
      category: 'AI & Inference',
      executablePath: 'python.exe',
      launchCommand: 'python.exe -m orbit',
    },
    // --- Communication & Productivity ---
    {
      id: 'slack',
      name: 'Slack',
      publisher: 'Slack Technologies',
      processName: 'slack.exe',
      iconType: 'system',
      category: 'Communication',
      executablePath: path.join(localAppData, 'slack', 'slack.exe'),
      launchCommand: 'slack.exe',
    },
    {
      id: 'discord',
      name: 'Discord',
      publisher: 'Discord Inc.',
      processName: 'Discord.exe',
      iconType: 'system',
      category: 'Communication',
      executablePath: path.join(localAppData, 'Discord', 'Update.exe'),
      launchCommand: 'Discord.exe',
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      publisher: 'Microsoft Corporation',
      processName: 'ms-teams.exe',
      iconType: 'system',
      category: 'Communication',
      executablePath: path.join(progFiles, 'WindowsApps', 'ms-teams.exe'),
      launchCommand: 'ms-teams.exe',
    },
    {
      id: 'word',
      name: 'Microsoft Word',
      publisher: 'Microsoft Corporation',
      processName: 'WINWORD.EXE',
      iconType: 'editor',
      category: 'Productivity',
      executablePath: path.join(progFiles, 'Microsoft Office', 'root', 'Office16', 'WINWORD.EXE'),
      launchCommand: 'winword.exe',
    },
    {
      id: 'excel',
      name: 'Microsoft Excel',
      publisher: 'Microsoft Corporation',
      processName: 'EXCEL.EXE',
      iconType: 'system',
      category: 'Productivity',
      executablePath: path.join(progFiles, 'Microsoft Office', 'root', 'Office16', 'EXCEL.EXE'),
      launchCommand: 'excel.exe',
    },
    {
      id: 'blender',
      name: 'Blender 3D Suite',
      publisher: 'Blender Foundation',
      processName: 'blender.exe',
      iconType: 'code',
      category: 'Media & Design',
      executablePath: path.join(progFiles, 'Blender Foundation', 'blender.exe'),
      launchCommand: 'blender.exe',
    },
    {
      id: 'spotify',
      name: 'Spotify Music',
      publisher: 'Spotify AB',
      processName: 'Spotify.exe',
      iconType: 'system',
      category: 'Media & Design',
      executablePath: path.join(localAppData, 'Microsoft', 'WindowsApps', 'Spotify.exe'),
      launchCommand: 'Spotify.exe',
    },
  ];

  // 3. Dynamic StartApps Discovery via PowerShell
  const discoveredMap = new Map();
  baseCatalog.forEach((app) => {
    discoveredMap.set(app.id, app);
  });

  try {
    const { stdout } = await execAsync('powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-StartApps | ConvertTo-Json -Compress"', {
      timeout: 5000,
      windowsHide: true,
    });
    if (stdout && stdout.trim()) {
      const parsed = JSON.parse(stdout.trim());
      const startAppsList = Array.isArray(parsed) ? parsed : [parsed];

      for (const sa of startAppsList) {
        if (!sa || !sa.Name || !sa.AppID) continue;
        const lowerId = sa.AppID.toLowerCase();
        if (lowerId.startsWith('http://') || lowerId.startsWith('https://')) continue;
        if (lowerId.endsWith('.pdf') || lowerId.endsWith('.chm') || lowerId.endsWith('.url') || lowerId.endsWith('.txt')) continue;

        const rawId = sa.Name.toLowerCase().replace(/[^a-z0-9]/g, '_');
        const existing = discoveredMap.get(rawId);
        if (!existing) {
          // Infer category
          let category = 'Utilities';
          const n = sa.Name.toLowerCase();
          if (n.includes('chrome') || n.includes('edge') || n.includes('firefox') || n.includes('browser') || n.includes('brave') || n.includes('opera') || n.includes('arc') || n.includes('vivaldi')) category = 'Browsers';
          else if (n.includes('studio') || n.includes('code') || n.includes('git') || n.includes('develop') || n.includes('terminal') || n.includes('compiler') || n.includes('python') || n.includes('clion') || n.includes('intellij') || n.includes('pycharm')) category = 'Development';
          else if (n.includes('office') || n.includes('word') || n.includes('excel') || n.includes('powerpoint') || n.includes('onenote') || n.includes('pdf') || n.includes('document') || n.includes('notepad') || n.includes('calendar')) category = 'Productivity';
          else if (n.includes('windows') || n.includes('system') || n.includes('control') || n.includes('setting') || n.includes('security') || n.includes('acer') || n.includes('driver') || n.includes('service') || n.includes('management')) category = 'System & OS';
          else if (n.includes('teams') || n.includes('slack') || n.includes('discord') || n.includes('zoom') || n.includes('skype') || n.includes('telegram') || n.includes('mail') || n.includes('whatsapp')) category = 'Communication';
          else if (n.includes('photo') || n.includes('video') || n.includes('music') || n.includes('media') || n.includes('audio') || n.includes('player') || n.includes('blender') || n.includes('adobe') || n.includes('camera') || n.includes('voice')) category = 'Media & Design';

          const procName = sa.AppID.includes('\\') ? path.basename(sa.AppID) : `${rawId}.exe`;

          discoveredMap.set(rawId, {
            id: rawId,
            name: sa.Name,
            publisher: sa.AppID.includes('Microsoft.') || sa.AppID.includes('windows') ? 'Microsoft Windows' : 'Installed Software',
            processName: procName,
            iconType: category === 'Browsers' ? 'browser' : category === 'Development' ? 'code' : 'system',
            category: category,
            executablePath: sa.AppID,
            launchCommand: sa.AppID,
          });
        }
      }
    }
  } catch (err) {
    console.warn('[Electron] Get-StartApps fallback notice:', err.message);
  }

  // 4. Transform with runtime status & native icon extraction
  const appList = Array.from(discoveredMap.values());

  const results = await Promise.all(
    appList.map(async (item) => {
      const procBase = (item.processName || '').toLowerCase().replace(/\.exe$/, '');
      const isRunning =
        runningProcesses.has((item.processName || '').toLowerCase()) ||
        runningProcesses.has(procBase) ||
        runningProcesses.has(`${procBase}.exe`);

      let iconDataUrl = null;
      if (item.executablePath && typeof item.executablePath === 'string' && !item.executablePath.includes('!')) {
        if (appIconCache.has(item.executablePath)) {
          iconDataUrl = appIconCache.get(item.executablePath);
        } else {
          try {
            if (fs.existsSync(item.executablePath)) {
              const nativeIcon = await app.getFileIcon(item.executablePath, { size: 'normal' });
              if (nativeIcon && !nativeIcon.isEmpty()) {
                iconDataUrl = nativeIcon.toDataURL();
                appIconCache.set(item.executablePath, iconDataUrl);
              }
            }
          } catch {
            // ignore icon extraction errors
          }
        }
      }

      return {
        ...item,
        installed: true,
        isRunning: isRunning,
        iconDataUrl: iconDataUrl || undefined,
        state: isRunning ? 'Running (Active Process)' : 'Installed & Ready',
        windowTitle: isRunning ? `${item.name} • Active Process` : 'Ready to Launch',
      };
    })
  );

  return results;
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

