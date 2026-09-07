/**
 * ORBIT Desktop Development Runner
 * 
 * Programmatically initializes Vite development server and launches Electron BrowserWindow
 * seamlessly without opening any external browser window.
 */

const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const BACKEND_PORT = 8765;
const BACKEND_URL = `http://127.0.0.1:${BACKEND_PORT}/health`;
const VITE_PORT = 5173;
const VITE_URL = `http://127.0.0.1:${VITE_PORT}`;

function checkUrlReady(url, retries = 60, interval = 300) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const tryConnect = () => {
      attempts++;
      const req = http.get(url, (res) => {
        if (res.statusCode === 200 || res.statusCode === 304) {
          resolve(true);
        } else {
          retry();
        }
      });

      req.on('error', () => {
        retry();
      });

      req.end();
    };

    const retry = () => {
      if (attempts >= retries) {
        reject(new Error(`Timed out waiting for server at ${url}`));
      } else {
        setTimeout(tryConnect, interval);
      }
    };

    tryConnect();
  });
}

async function start() {
  const repoRoot = path.resolve(__dirname, '../..');
  let backendProcess = null;

  // 1. Check if Python ORBIT backend gateway is already running on port 8765
  let backendAlreadyRunning = false;
  try {
    await checkUrlReady(BACKEND_URL, 3, 200);
    console.log('[ORBIT Desktop] Python backend is already running on port ' + BACKEND_PORT);
    backendAlreadyRunning = true;
  } catch {
    backendAlreadyRunning = false;
  }

  if (!backendAlreadyRunning) {
    console.log('[ORBIT Desktop] Starting Python ORBIT Gateway backend on port ' + BACKEND_PORT + '...');
    const pythonCmd = process.env.PYTHON || 'python';
    backendProcess = spawn(
      pythonCmd,
      ['-m', 'orbit', '--port', String(BACKEND_PORT)],
      {
        cwd: repoRoot,
        stdio: 'inherit',
        shell: true,
        env: {
          ...process.env,
          PYTHONPATH: path.join(repoRoot, 'src'),
          ORBIT_ADAPTER_MODE: 'PRODUCTION',
        },
      }
    );

    backendProcess.on('error', (err) => {
      console.error('[ORBIT Desktop] Failed to start Python backend:', err);
    });

    try {
      console.log(`[ORBIT Desktop] Waiting for Python backend at ${BACKEND_URL}...`);
      await checkUrlReady(BACKEND_URL, 60, 300);
      console.log('[ORBIT Desktop] Python backend gateway is ready!');
    } catch (err) {
      console.warn('[ORBIT Desktop] Warning: Python backend startup timeout:', err.message);
    }
  }

  // 2. Check if Vite dev server is already running on port 5173
  let viteAlreadyRunning = false;
  let viteProcess = null;
  try {
    await checkUrlReady(VITE_URL, 2, 150);
    console.log('[ORBIT Desktop] Vite dev server is already running on port ' + VITE_PORT);
    viteAlreadyRunning = true;
  } catch {
    viteAlreadyRunning = false;
  }

  if (!viteAlreadyRunning) {
    console.log('[ORBIT Desktop] Starting Vite development server...');
    viteProcess = spawn(
      process.platform === 'win32' ? 'npx.cmd' : 'npx',
      ['vite', '--host', '127.0.0.1', '--port', String(VITE_PORT), '--strictPort', '--no-open'],
      {
        cwd: path.resolve(__dirname, '..'),
        stdio: 'inherit',
        shell: true,
        env: { ...process.env, BROWSER: 'none' },
      }
    );

    viteProcess.on('error', (err) => {
      console.error('[ORBIT Desktop] Failed to start Vite:', err);
      if (backendProcess) backendProcess.kill();
      process.exit(1);
    });
  }

  try {
    console.log(`[ORBIT Desktop] Waiting for Vite server at ${VITE_URL}...`);
    await checkUrlReady(VITE_URL);
    console.log('[ORBIT Desktop] Vite server is ready. Launching Electron desktop application...');

    const fs = require('fs');
    const localElectronWin = path.resolve(__dirname, '../node_modules/electron/dist/electron.exe');
    let electronCmd = 'npx';
    let electronArgs = ['electron', path.resolve(__dirname, 'main.cjs')];
    let useShell = true;

    if (process.platform === 'win32' && fs.existsSync(localElectronWin)) {
      electronCmd = localElectronWin;
      electronArgs = [path.resolve(__dirname, 'main.cjs')];
      useShell = false;
    } else if (process.platform === 'win32') {
      electronCmd = 'npx.cmd';
    }

    const electronProcess = spawn(
      electronCmd,
      electronArgs,
      {
        cwd: path.resolve(__dirname, '..'),
        stdio: 'inherit',
        shell: useShell,
        env: { ...process.env, NODE_ENV: 'development' },
      }
    );

    electronProcess.on('close', (code) => {
      console.log(`[ORBIT Desktop] Electron application closed (code ${code}).`);
      if (viteProcess) viteProcess.kill();
      if (backendProcess) {
        console.log('[ORBIT Desktop] Stopping spawned Python backend...');
        backendProcess.kill();
      }
      process.exit(code || 0);
    });

    electronProcess.on('error', (err) => {
      console.error('[ORBIT Desktop] Failed to start Electron:', err);
      if (viteProcess) viteProcess.kill();
      if (backendProcess) backendProcess.kill();
      process.exit(1);
    });

  } catch (err) {
    console.error('[ORBIT Desktop] Startup error:', err.message);
    if (viteProcess) viteProcess.kill();
    if (backendProcess) backendProcess.kill();
    process.exit(1);
  }
}

start();
