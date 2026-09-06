/**
 * ORBIT Desktop Development Runner
 * 
 * Programmatically initializes Vite development server and launches Electron BrowserWindow
 * seamlessly without opening any external browser window.
 */

const { spawn } = require('child_process');
const http = require('http');
const path = require('path');

const VITE_PORT = 5173;
const VITE_URL = `http://127.0.0.1:${VITE_PORT}`;

function checkViteReady(retries = 60, interval = 300) {
  return new Promise((resolve, reject) => {
    let attempts = 0;

    const tryConnect = () => {
      attempts++;
      const req = http.get(VITE_URL, (res) => {
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
        reject(new Error(`Timed out waiting for Vite server at ${VITE_URL}`));
      } else {
        setTimeout(tryConnect, interval);
      }
    };

    tryConnect();
  });
}

async function start() {
  console.log('[ORBIT Desktop] Starting Vite development server...');

  // Start Vite process (prevent opening browser)
  const viteProcess = spawn(
    process.platform === 'win32' ? 'npx.cmd' : 'npx',
    ['vite', '--host', '127.0.0.1', '--port', String(VITE_PORT), '--strictPort'],
    {
      cwd: path.resolve(__dirname, '..'),
      stdio: 'inherit',
      shell: true,
      env: { ...process.env, BROWSER: 'none' },
    }
  );

  viteProcess.on('error', (err) => {
    console.error('[ORBIT Desktop] Failed to start Vite:', err);
    process.exit(1);
  });

  try {
    console.log(`[ORBIT Desktop] Waiting for Vite server at ${VITE_URL}...`);
    await checkViteReady();
    console.log('[ORBIT Desktop] Vite server is ready. Launching Electron desktop application...');

    const electronProcess = spawn(
      process.platform === 'win32' ? 'npx.cmd' : 'npx',
      ['electron', path.resolve(__dirname, 'main.cjs')],
      {
        cwd: path.resolve(__dirname, '..'),
        stdio: 'inherit',
        shell: true,
        env: { ...process.env, NODE_ENV: 'development' },
      }
    );

    electronProcess.on('close', (code) => {
      console.log(`[ORBIT Desktop] Electron application closed (code ${code}).`);
      viteProcess.kill();
      process.exit(code || 0);
    });

    electronProcess.on('error', (err) => {
      console.error('[ORBIT Desktop] Failed to start Electron:', err);
      viteProcess.kill();
      process.exit(1);
    });

  } catch (err) {
    console.error('[ORBIT Desktop] Startup error:', err.message);
    viteProcess.kill();
    process.exit(1);
  }
}

start();
