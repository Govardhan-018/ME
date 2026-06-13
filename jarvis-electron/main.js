const { app, BrowserWindow, globalShortcut, ipcMain } = require('electron');
const path = require('path');

let mainWindow;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 560,
    frame: false, // Frameless window
    transparent: true, // Transparent background
    backgroundColor: '#00000000', // Ensure complete transparency at the window level
    resizable: true,
    webPreferences: {
      nodeIntegration: true, // Required for IPC in the renderer
      contextIsolation: false // Required for direct require('electron') in renderer
    }
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  // Uncomment to open the DevTools.
  // mainWindow.webContents.openDevTools();

  // Listen for window control events from the renderer
  ipcMain.on('win-minimize', () => {
    mainWindow.minimize();
  });

  ipcMain.on('win-maximize', () => {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  });

  ipcMain.on('win-close', () => {
    mainWindow.close();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  createWindow();

  // Register a global shortcut to toggle window visibility
  // CommandOrControl+Space will hide or show the HUD
  globalShortcut.register('CommandOrControl+Space', () => {
    if (mainWindow) {
      if (mainWindow.isVisible()) {
        mainWindow.hide();
      } else {
        mainWindow.show();
      }
    }
  });

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Unregister shortcuts when quitting
app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

// Quit when all windows are closed, except on macOS
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});
