const { app, BrowserWindow, protocol, dialog, ipcMain } = require('electron');
const path = require('path');
const fs = require('fs');
const http = require('http');
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
let nextProcess = null; // 백그라운드 Next.js 프로세스

// 로컬 Next.js 서버(포트 3000) 응답 여부 체크
function isServerReady(port = 3000) {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${port}/`, (res) => {
      resolve(true);
    });
    req.on('error', () => {
      resolve(false);
    });
    req.setTimeout(1000, () => {
      req.destroy();
      resolve(false);
    });
  });
}

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
    width: 440,
    height: 440,
    transparent: true, // 배경 투명하게
    frame: false,      // 창틀 제거
    alwaysOnTop: true, // 무조건 맨 위에
    center: true,
    icon: path.join(__dirname, 'icon.png')
  });

  // 로고를 중앙에 띄우고 두근거리는(Pulse) 애니메이션과 상태 메시지를 표시합니다.
  splash.loadURL(`data:text/html;charset=utf-8,
    <body style="margin:0; display:flex; flex-direction:column; align-items:center; justify-content:center; height:100vh; overflow:hidden; background:transparent; font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; user-select:none;">
      <img src="music-app://local/${encodeURIComponent(path.join(__dirname, 'icon.png').replace(/\\/g, '/'))}" 
           style="width:180px; height:180px; filter: drop-shadow(0 0 25px rgba(225,29,72,0.6)); animation: pulse 2s infinite;">
      <div style="margin-top:18px; color:#f43f5e; font-size:15px; font-weight:700; text-shadow:0 2px 8px rgba(0,0,0,0.9); letter-spacing:0.5px;">
        가무음곡 음악 엔진을 시작하는 중입니다...
      </div>
      <div style="margin-top:6px; color:rgba(255,255,255,0.7); font-size:12px; text-shadow:0 1px 4px rgba(0,0,0,0.9);">
        잠시만 기다려 주세요 (최초 실행 시 10~25초 소요)
      </div>
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
    title: 'KaMuEumGok - Developed by 정승찬 (jscsarik)',
    icon: path.join(__dirname, 'icon.png'),
    show: false, // 로딩 완료 전까지 숨김
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      webSecurity: false,
    }
  });

  // 로드가 완전히 성공했을 때만 스플래시를 닫고 메인 창을 표시!
  mainWindow.webContents.on('did-finish-load', () => {
    if (splash && !splash.isDestroyed()) {
      splash.close();
    }
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  // 로딩 실패 시 (아직 서버가 기동 중일 때): 에러창을 띄우지 않고 조용히 재시도
  mainWindow.webContents.on('did-fail-load', () => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      setTimeout(async () => {
        const ready = await isServerReady(3000);
        if (ready && mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.loadURL('http://localhost:3000').catch(() => {});
        }
      }, 1000);
    }
  });
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
  // ★ AAA 부팅 시퀀스 시작
  // ==========================================================
  
  // 1. 더블클릭 즉시 빛의 속도로 스플래시 로고 창부터 띄웁니다.
  createSplashWindow();

  // 2. 메인 창을 만들고 뒤에 숨겨둡니다.
  createWindow();

  // 3. Next.js 서버 감지 및 안전한 부팅 시퀀스
  (async () => {
    let ready = await isServerReady(3000);
    if (!ready) {
      console.log('Next.js server not detected. Spawning next dev in background...');
      const npmCmd = process.platform === 'win32' ? 'npm.cmd' : 'npm';
      nextProcess = spawn(npmCmd, ['run', 'dev'], {
        cwd: __dirname,
        windowsHide: true,
        shell: true,
        stdio: 'ignore'
      });
      nextProcess.on('error', (err) => {
        console.error('Failed to spawn Next.js process:', err);
      });
    }

    // 4. 서버가 완전히 준비(200 OK)될 때까지 기다렸다가 mainWindow.loadURL 호출
    const maxWait = 90; // 최대 90초 대기 (사양이 낮은 노트북이나 최초 빌드 대비)
    let waited = 0;
    while (waited < maxWait) {
      ready = await isServerReady(3000);
      if (ready) {
        console.log('Next.js server is ready! Connecting mainWindow...');
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.loadURL('http://localhost:3000').catch(() => {});
        }
        return;
      }
      await new Promise(res => setTimeout(res, 1000));
      waited++;
    }

    // 90초 초과 시에만 안내 대화상자 표시
    dialog.showErrorBox(
      '가무음곡 시작 오류',
      'Next.js 서버(http://localhost:3000)를 시작하지 못했습니다.\n\n3000번 포트가 다른 프로그램에서 사용 중이거나 최초 빌드 시간이 지연되었을 수 있습니다.\n프로그램을 다시 실행해 보세요.'
    );
    if (splash && !splash.isDestroyed()) splash.close();
    app.quit();
  })();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  // 백그라운드에서 실행한 Next.js 프로세스 깔끔하게 종료
  if (nextProcess && nextProcess.pid) {
    if (process.platform === 'win32') {
      exec(`taskkill /pid ${nextProcess.pid} /T /F`, () => {});
    } else {
      try { nextProcess.kill('SIGTERM'); } catch (e) {}
    }
  }
});