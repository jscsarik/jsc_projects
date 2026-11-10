const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
    scanLibrary: () => ipcRenderer.invoke('scan-library'),
    loadLibrary: () => ipcRenderer.invoke('load-library')
});
