const { app, BrowserWindow, protocol, dialog, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const crypto = require('crypto');
const { exec, spawn } = require('child_process');

// protocol 등록: 앱 시작 전에 호출해야 함
protocol.registerSchemesAsPrivileged([
  {
    scheme: 'music-app',
    privileges: {
      standard: true,
      secure: true,
      bypassCSP: true,
      stream: true,
      supportFetchAPI: true
    }
  }
]);

let parseFile;
let splash;      // 스플래시(로고) 창 변수
let mainWindow;  // 메인 창 변수

// music-metadata 비동기 로드
(async () => {
  const mm = await import('music-metadata');
  parseFile = mm.parseFile;
})();

function scanDirectory(dirPath, filesList = []) {
  try {
    const files = fs.readdirSync(dirPath);
    for (const file of files) {
      const fullPath = path.join(dirPath, file);
      try {
        const stat = fs.statSync(fullPath);
        if (stat.isDirectory()) {
          scanDirectory(fullPath, filesList);
        } else {
          const ext = path.extname(file).toLowerCase();
          if (['.mp3', '.flac', '.wav', '.ogg', '.m4a'].includes(ext)) {
            filesList.push(fullPath);
          }
        }
      } catch (e) {
        console.error('Error reading file stat:', e);
      }
    }
  } catch (err) {
    console.error('Error reading directory:', err);
  }
  return filesList;
}

// ★ 1. 스플래시(게임 로고) 화면 생성 함수
const createSplashWindow = () => {
  splash = new BrowserWindow({
    width: 400,
    height: 400,
    transparent: true, // 배경 투명하게
    frame: false,      // 창틀 제거
    alwaysOnTop: true, // 무조건 맨 위에
    center: true,
    icon: path.join(__dirname, 'icon.png')
  });

  // 로고를 중앙에 띄우고 두근거리는(Pulse) 애니메이션을 줍니다.
  splash.loadURL(`data:text/html;charset=utf-8,
    <body style="margin:0; display:flex; align-items:center; justify-content:center; height:100vh; overflow:hidden; background:transparent;">
      <img src="music-app://local/${encodeURIComponent(path.join(__dirname, 'icon.png').replace(/\\/g, '/'))}" 
           style="width:200px; height:200px; filter: drop-shadow(0 0 25px rgba(225,29,72,0.6)); animation: pulse 2s infinite;">
      <style>
        @keyframes pulse {
          0% { transform: scale(0.95); opacity: 0.8; }
          50% { transform: scale(1.05); opacity: 1; }
          100% { transform: scale(0.95); opacity: 0.8; }
        }
      </style>
    </body>
  `);
};

// ★ 2. 메인 화면 생성 함수
const createWindow = () => {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800, 
    title: 'KaMuEumGok',
    icon: path.join(__dirname, 'icon.png'),
    show: false, // ★ 중요: 일단 창을 투명 망토 씌워서 숨겨둡니다.
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false,
    }
  });

  // 뒤에서 돌고 있는 Next.js 서버가 켜질 시간(약 2초)을 벌어준 뒤에 화면을 연결합니다.
  setTimeout(() => {
    mainWindow.loadURL('http://localhost:3000');
  }, 2000);
};

app.whenReady().then(() => {
  // Protocol 핸들러 등록
  protocol.handle('music-app', (request) => {
    const urlStr = request.url;
    let filePath = decodeURIComponent(urlStr.replace(/^music-app:\/\/local\//i, ''));

    if (process.platform === 'win32' && filePath.match(/^\/[a-zA-Z]:/)) {
      filePath = filePath.slice(1);
    }

    filePath = path.normalize(filePath);

    try {
      const data = fs.readFileSync(filePath);
      const ext = path.extname(filePath).toLowerCase();
      let contentType = 'application/octet-stream';

      if (ext === '.mp3') contentType = 'audio/mpeg';
      else if (ext === '.flac') contentType = 'audio/flac';
      else if (ext === '.wav') contentType = 'audio/wav';
      else if (ext === '.ogg') contentType = 'audio/ogg';
      else if (ext === '.m4a') contentType = 'audio/mp4';
      else if (ext === '.jpg' || ext === '.jpeg') contentType = 'image/jpeg';
      else if (ext === '.png') contentType = 'image/png';

      // ★ 핵심: 구간 이동(탐색)을 지원하는 206 Partial Content 통신 로직
      const range = request.headers.get('range');
      
      if (range) {
        // 브라우저가 "여기서부터 여기까지 줘!" 라고 요청한 범위를 파싱합니다.
        const parts = range.replace(/bytes=/, "").split("-");
        const start = parseInt(parts[0], 10);
        const end = parts[1] ? parseInt(parts[1], 10) : data.length - 1;
        const chunksize = (end - start) + 1;

        // 요청한 구간만큼만 버퍼를 잘라서 206 상태 코드로 보냅니다.
        return new Response(data.slice(start, end + 1), {
          status: 206, // 구간 응답 성공
          statusText: 'Partial Content',
          headers: {
            'Content-Type': contentType,
            'Content-Range': `bytes ${start}-${end}/${data.length}`,
            'Accept-Ranges': 'bytes',
            'Content-Length': chunksize.toString(),
            'Access-Control-Allow-Origin': '*'
          }
        });
      } else {
        // 처음부터 재생할 때는 전체 길이를 알려주며 보냅니다.
        return new Response(data, {
          status: 200,
          headers: {
            'Content-Type': contentType,
            'Content-Length': data.length.toString(),
            'Accept-Ranges': 'bytes',
            'Access-Control-Allow-Origin': '*'
          }
        });
      }
    } catch (e) {
      console.error('Failed to read file:', filePath, e);
      return new Response(null, { status: 404 });
    }
  });

  const userDataPath = app.getPath('userData');
  const coversPath = path.join(userDataPath, 'covers');
  const libraryFile = path.join(userDataPath, 'library.json');

  if (!fs.existsSync(coversPath)) {
    fs.mkdirSync(coversPath, { recursive: true });
  }

  // Load library handler
  ipcMain.handle('load-library', () => {
    if (fs.existsSync(libraryFile)) {
      try {
        const data = fs.readFileSync(libraryFile, 'utf8');
        return JSON.parse(data);
      } catch (err) {
        console.error('Failed to read library.json:', err);
        return [];
      }
    }
    return [];
  });

  // 스캔 핸들러
  ipcMain.handle('scan-library', async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openDirectory']
    });

    if (result.canceled) return [];

    const folderPath = result.filePaths[0];
    const audioFiles = scanDirectory(folderPath);

    let library = [];
    if (fs.existsSync(libraryFile)) {
      try {
        library = JSON.parse(fs.readFileSync(libraryFile, 'utf8'));
      } catch (e) {
        library = [];
      }
    }
    const existingPaths = new Set(library.map(s => s.path));
    let updated = false;

    for (const file of audioFiles) {
      if (existingPaths.has(file)) continue;

      updated = true;
      try {
        if (!parseFile) {
          throw new Error('music-metadata is not loaded yet');
        }
        const metadata = await parseFile(file, { duration: true, skipCovers: false });
        let pictureStr = null;

        if (metadata.common.picture && metadata.common.picture.length > 0) {
          const pic = metadata.common.picture[0];
          const hash = crypto.createHash('md5').update(pic.data).digest('hex');
          const ext = pic.format === 'image/png' ? 'png' : 'jpg';
          const coverFilePath = path.join(coversPath, `${hash}.${ext}`);

          if (!fs.existsSync(coverFilePath)) {
            fs.writeFileSync(coverFilePath, pic.data);
          }
          pictureStr = `music-app://local/${encodeURIComponent(coverFilePath.replace(/\\/g, '/'))}`;
        }

        library.push({
          path: file,
          title: metadata.common.title || path.basename(file),
          artist: metadata.common.artist || 'Unknown Artist',
          album: metadata.common.album || 'Unknown Album',
          genre: (metadata.common.genre && metadata.common.genre.length > 0) ? metadata.common.genre[0] : 'Unknown Genre',
          duration: metadata.format.duration || 0,
          picture: pictureStr,
          track: metadata.common.track.no || 0
        });
      } catch (e) {
        console.error('Metadata parsing error for file', file, e);
        library.push({
          path: file,
          title: path.basename(file),
          artist: 'Unknown',
          album: 'Unknown',
          genre: 'Unknown',
          duration: 0,
          picture: null,
          track: 0
        });
      }
    }

    if (updated) {
      fs.writeFileSync(libraryFile, JSON.stringify(library), 'utf8');
    }

    return library;
  });

  // ==========================================================
  // ★ AAA 게임식 부팅 시퀀스 시작
  // ==========================================================
  
  // 1. 더블클릭 즉시 빛의 속도로 스플래시 로고 창부터 띄웁니다.
  createSplashWindow();

// 2. 로고가 떠 있는 동안, 뒤에서 창 없이 몰래 Next.js 서버를 부팅시킵니다.
  // ★ 맨 끝에 shell: true 옵션을 추가했습니다!
  spawn(/^win/.test(process.platform) ? 'npm.cmd' : 'npm', ['run', 'dev'], { windowsHide: true, shell: true });

  // 3. 메인 창을 만들고 뒤에 숨겨둡니다.
  createWindow();

  // 4. 서버 부팅 시간(약 4.5초)이 지나면 로고를 닫고 본 화면을 짠! 보여줍니다.
  setTimeout(() => {
    if (splash) splash.close();
    if (mainWindow) mainWindow.show();
  }, 4500);

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  // 창이 닫히면 백그라운드에서 몰래 돌던 Next.js(node.exe) 프로세스까지 강제로 깔끔하게 킬합니다.
  exec('taskkill /f /im node.exe', () => {
    if (process.platform !== 'darwin') app.quit();
  });
});