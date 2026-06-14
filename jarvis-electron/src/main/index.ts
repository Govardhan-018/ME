/**
 * J.A.R.V.I.S — Electron main process.
 *
 * Hardened vs. the original shell:
 *   • contextIsolation: true, sandbox: true, nodeIntegration: false
 *   • the renderer talks to the OS only through the minimal preload bridge
 *
 * It also OWNS the Python "brain": on launch it spawns the FastAPI Agent Core
 * (`core.app.main:app` on 127.0.0.1:8000), reports a live online/offline status
 * to the renderer, and kills it on quit. If a brain is already serving :8000
 * (e.g. you ran it by hand) it just attaches instead of double-spawning.
 */
import { app, BrowserWindow, globalShortcut, ipcMain } from 'electron'
import { spawn, type ChildProcess } from 'node:child_process'
import { connect } from 'node:net'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'

let win: BrowserWindow | null = null

/* ── Python brain lifecycle ──────────────────────────────────────────── */
type BackendStatus = 'starting' | 'online' | 'offline'
let brain: ChildProcess | null = null
let backendStatus: BackendStatus = 'offline'
let healthTimer: ReturnType<typeof setInterval> | null = null

function setStatus(s: BackendStatus): void {
  backendStatus = s
  for (const w of BrowserWindow.getAllWindows()) w.webContents.send('backend:status', s)
}

function portOpen(port: number): Promise<boolean> {
  return new Promise((res) => {
    const sock = connect({ host: '127.0.0.1', port })
    sock.once('connect', () => {
      sock.destroy()
      res(true)
    })
    sock.once('error', () => res(false))
    sock.setTimeout(700, () => {
      sock.destroy()
      res(false)
    })
  })
}

function startHealthPolling(): void {
  if (healthTimer) return
  healthTimer = setInterval(async () => {
    try {
      const r = await fetch('http://127.0.0.1:8000/api/health')
      setStatus(r.ok ? 'online' : 'offline')
    } catch {
      setStatus(brain ? 'starting' : 'offline')
    }
  }, 1500)
}

async function startBrain(): Promise<void> {
  if (process.env['JARVIS_NO_BACKEND'] === '1') {
    startHealthPolling()
    return
  }

  // Already serving (manual run / hot-reload session)? Attach, don't double-spawn.
  if (await portOpen(8000)) {
    setStatus('starting')
    startHealthPolling()
    return
  }

  const projectRoot = resolve(app.getAppPath(), '..')
  const entry = join(projectRoot, 'core', 'app', 'main.py')
  if (!existsSync(entry)) {
    console.warn(`[brain] core not found at ${entry} (appPath=${app.getAppPath()}) — skipping auto-launch`)
    setStatus('offline')
    return
  }

  const python = process.env['JARVIS_PYTHON'] || 'python'
  console.log(`[brain] launching: ${python} -m uvicorn core.app.main:app  (cwd=${projectRoot})`)
  setStatus('starting')
  try {
    brain = spawn(
      python,
      ['-m', 'uvicorn', 'core.app.main:app', '--host', '127.0.0.1', '--port', '8000'],
      { cwd: projectRoot, env: { ...process.env, PYTHONUNBUFFERED: '1' } }
    )
    brain.stdout?.on('data', (d: Buffer) => process.stdout.write(`[brain] ${d}`))
    brain.stderr?.on('data', (d: Buffer) => process.stdout.write(`[brain] ${d}`))
    brain.on('error', (err) => {
      console.error('[brain] spawn failed:', err.message)
      setStatus('offline')
    })
    brain.on('exit', (code) => {
      console.log(`[brain] exited (code ${code})`)
      brain = null
      setStatus('offline')
    })
  } catch (e) {
    console.error('[brain] spawn error:', e)
    setStatus('offline')
  }
  startHealthPolling()
}

function stopBrain(): void {
  if (healthTimer) {
    clearInterval(healthTimer)
    healthTimer = null
  }
  const child = brain
  brain = null
  if (child?.pid) {
    try {
      if (process.platform === 'win32') spawn('taskkill', ['/pid', String(child.pid), '/T', '/F'])
      else child.kill('SIGTERM')
    } catch {
      /* ignore */
    }
  }
}

function createWindow(): void {
  win = new BrowserWindow({
    width: 1320,
    height: 840,
    minWidth: 1040,
    minHeight: 680,
    show: false,
    frame: false,
    transparent: true,
    backgroundColor: '#00000000',
    titleBarStyle: 'hidden',
    autoHideMenuBar: true,
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  win.once('ready-to-show', () => win?.show())

  win.on('maximize', () => win?.webContents.send('window:maximized', true))
  win.on('unmaximize', () => win?.webContents.send('window:maximized', false))
  // Send the current brain status to a freshly-loaded renderer.
  win.webContents.on('did-finish-load', () => win?.webContents.send('backend:status', backendStatus))
  win.on('closed', () => {
    win = null
  })

  const devUrl = process.env['ELECTRON_RENDERER_URL']
  if (devUrl) {
    win.loadURL(devUrl)
  } else {
    win.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

/* ── Window-control IPC (custom title bar) ───────────────────────────── */
ipcMain.on('window:minimize', () => win?.minimize())
ipcMain.on('window:toggle-maximize', () => {
  if (!win) return
  win.isMaximized() ? win.unmaximize() : win.maximize()
})
ipcMain.on('window:close', () => win?.close())
ipcMain.handle('window:is-maximized', () => win?.isMaximized() ?? false)
ipcMain.handle('backend:get-status', () => backendStatus)

/* ── Lifecycle ───────────────────────────────────────────────────────── */
app.whenReady().then(() => {
  createWindow()
  void startBrain()

  const ok = globalShortcut.register('CommandOrControl+Space', () => {
    if (!win) return
    if (win.isVisible() && win.isFocused()) {
      win.hide()
    } else {
      win.show()
      win.focus()
    }
  })
  if (!ok) console.warn('[JARVIS] CommandOrControl+Space already in use.')

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit()
})

app.on('before-quit', () => stopBrain())
app.on('will-quit', () => globalShortcut.unregisterAll())
