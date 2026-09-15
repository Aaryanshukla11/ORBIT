const fs = require('fs');
const path = require('path');

console.log('Testing App path detections...');
const userProfile = process.env.USERPROFILE || 'C:\\Users\\' + (process.env.USERNAME || 'User');
const localAppData = process.env.LOCALAPPDATA || path.join(userProfile, 'AppData', 'Local');
const progFiles = process.env['ProgramFiles'] || 'C:\\Program Files';
const progFilesX86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)';
const winDir = process.env.WINDIR || 'C:\\Windows';

const samplePaths = [
  path.join(winDir, 'explorer.exe'),
  path.join(winDir, 'System32', 'Taskmgr.exe'),
  path.join(winDir, 'System32', 'notepad.exe'),
  path.join(winDir, 'System32', 'cmd.exe'),
  path.join(progFiles, 'Google', 'Chrome', 'Application', 'chrome.exe'),
  path.join(progFilesX86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
  path.join(localAppData, 'Programs', 'Microsoft VS Code', 'Code.exe'),
];

for (const p of samplePaths) {
  console.log(p, '=> Exists:', fs.existsSync(p));
}
