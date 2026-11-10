// popup.js - 부분 일치(Fuzzy) + 최후의 보루(전체 다운로드) 적용
// 리스트 테이블 형태의 UI로 가독성 개선

const VIDEO_EXTENSIONS = ['.mp4', '.avi', '.flv', '.mpg', '.wmv', '.mkv', '.webm'];

let beatmapInfo = null;
let selectedDiffs = new Set();

const els = {
  status: document.getElementById('status'),
  counter: document.getElementById('selected-counter'),
  btnDownload: document.getElementById('download-btn'),
  progressText: document.getElementById('progress-text'),
  progressBar: document.getElementById('progress-bar'),
  barContainer: document.getElementById('progress-bar-container'),
  btnClear: document.getElementById('clear-btn'),
  btnAll: document.getElementById('all-btn'),
  container: document.getElementById('canvas-container'), // 이 컨테이너에 리스트를 렌더링합니다
  videoCheckbox: document.getElementById('video-checkbox'),
  videoBadge: document.getElementById('video-badge')
};

const STORAGE_KEY_INCLUDE_VIDEO = 'osu_selective_include_video';

function initVideoOption() {
  if (!els.videoCheckbox) return;
  const saved = localStorage.getItem(STORAGE_KEY_INCLUDE_VIDEO);
  // 기본값은 false (No-Video)
  els.videoCheckbox.checked = saved === 'true';

  els.videoCheckbox.addEventListener('change', () => {
    localStorage.setItem(STORAGE_KEY_INCLUDE_VIDEO, els.videoCheckbox.checked);
  });
}

function estimateStarsByName(name) {
  const n = name.toLowerCase();
  if (n.includes('easy')) return 1.5;
  if (n.includes('normal')) return 2.5;
  if (n.includes('hard')) return 3.5;
  if (n.includes('insane')) return 4.8;
  if (n.includes('expert')) return 6.0;
  if (n.includes('extra') || n.includes('extreme') || n.includes('expert+')) return 7.2;
  return 4.0;
}

function getDifficultyColor(stars) {
  const s = Math.max(1, Math.min(9, stars));
  if (s < 3.5) {
    const ratio = (s - 1) / (3.5 - 1);
    const r = 255;
    const g = Math.round(255 - (255 - 102) * ratio);
    const b = Math.round(255 - (255 - 170) * ratio);
    return `rgb(${r},${g},${b})`;
  } else if (s < 6.5) {
    const ratio = (s - 3.5) / (6.5 - 3.5);
    const r = 255;
    const g = Math.round(102 - 102 * ratio);
    const b = Math.round(170 - 170 * ratio);
    return `rgb(${r},${g},${b})`;
  } else {
    const ratio = (s - 6.5) / (9.0 - 6.5);
    const r = Math.round(255 - 255 * ratio);
    const g = 0;
    const b = 0;
    return `rgb(${r},${g},${b})`;
  }
}

function renderDifficultyList(diffs) {
  if (!els.container) return;
  els.container.innerHTML = ''; // 기존 내용물 비우기

  if (!diffs || diffs.length === 0) { 
    els.status.textContent = "난이도 정보 없음"; 
    return; 
  }

  // 난이도 별점(stars) 오름차순으로 정렬하여 유저가 편하게 볼 수 있도록 함
  const sortedDiffs = [...diffs].map(d => ({
    name: d.name,
    stars: Number(d.stars) || estimateStarsByName(d.name)
  })).sort((a, b) => a.stars - b.stars);

  sortedDiffs.forEach(diff => {
    const stars = diff.stars;
    const color = getDifficultyColor(stars);
    
    // 별점에 따른 텍스트 대비색 (가독성 향상)
    const textColor = stars < 3.5 ? '#111111' : '#ffffff';

    // 1. 아이템 컨테이너
    const item = document.createElement('div');
    item.className = 'diff-item';
    item.dataset.name = diff.name;

    // 2. 체크박스 + 이름 라벨
    const label = document.createElement('label');
    label.className = 'diff-label';

    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'diff-checkbox';
    checkbox.value = diff.name;
    
    const nameText = document.createElement('span');
    nameText.className = 'diff-name-text';
    nameText.textContent = diff.name;

    label.appendChild(checkbox);
    label.appendChild(nameText);
    item.appendChild(label);

    // 3. 난이도 별점 뱃지
    const badge = document.createElement('span');
    badge.className = 'diff-badge';
    badge.style.backgroundColor = color;
    badge.style.color = textColor;
    
    // 검정색/어두운 배경 뱃지의 경우 얇은 테두리 추가
    if (stars >= 6.5) {
      badge.style.border = '1px solid rgba(255, 255, 255, 0.4)';
    }
    badge.textContent = `★ ${stars.toFixed(2)}`;
    item.appendChild(badge);

    // 4. 선택 토글 로직
    const toggle = (forceState) => {
      const checked = typeof forceState === 'boolean' ? forceState : !checkbox.checked;
      checkbox.checked = checked;
      if (checked) {
        selectedDiffs.add(diff.name);
        item.classList.add('selected');
      } else {
        selectedDiffs.delete(diff.name);
        item.classList.remove('selected');
      }
      updateUI();
    };

    // 아이템 행을 클릭하면 토글
    item.addEventListener('click', (e) => {
      if (e.target === checkbox || e.target.closest('.diff-checkbox')) return;
      e.preventDefault();
      toggle();
    });

    checkbox.addEventListener('change', () => {
      toggle(checkbox.checked);
    });

    // 외부 제어를 위해 요소를 저장
    item._toggle = toggle;

    els.container.appendChild(item);
  });
}

function updateUI() {
  els.counter.textContent = selectedDiffs.size;
  els.btnDownload.disabled = selectedDiffs.size === 0;
}

async function fetchBeatmapData() {
  els.status.textContent = "페이지 분석 중...";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.url?.includes('osu.ppy.sh/beatmapsets/')) {
      els.status.textContent = 'osu! 비트맵 페이지가 아닙니다.'; return;
    }
    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const el = document.getElementById('json-beatmapset');
        return el ? JSON.parse(el.textContent) : null;
      }
    });
    if (!results?.[0]?.result) throw new Error('메타데이터 태그 없음');
    const data = results[0].result;
    
    let maxLen = 0;
    if (data.beatmaps && data.beatmaps.length > 0) {
      maxLen = Math.max(...data.beatmaps.map(m => m.total_length || 0));
    }
    const mm = Math.floor(maxLen / 60);
    const ss = (maxLen % 60).toString().padStart(2, '0');
    const timeStr = maxLen > 0 ? ` [${mm}:${ss}]` : '';

    const hasVideo = Boolean(data.has_video || data.video);
    beatmapInfo = {
      setId: data.id,
      title: `${data.artist} - ${data.title}`.replace(/[\\/:*?"<>|]/g, '_'),
      hasVideo: hasVideo,
      diffs: data.beatmaps.map(m => ({ name: m.version, stars: m.difficulty_rating }))
    };
    els.status.textContent = `ID: ${beatmapInfo.setId} (${beatmapInfo.diffs.length}곡)${timeStr}`;
    
    if (els.videoBadge) {
      if (hasVideo) {
        els.videoBadge.textContent = '🎬 영상 있음';
        els.videoBadge.className = 'video-badge has-video';
        els.videoBadge.title = '이 비트맵에는 배경 동영상이 포함되어 있습니다.';
      } else {
        els.videoBadge.textContent = '영상 없음';
        els.videoBadge.className = 'video-badge no-video';
        els.videoBadge.title = '이 비트맵에는 배경 동영상이 없습니다.';
      }
    }

    renderDifficultyList(beatmapInfo.diffs);
  } catch (err) { els.status.textContent = '데이터 스캔 실패'; }
}

async function getFileBlob(setId, includeVideo = false) {
  const modeText = includeVideo ? '영상 포함' : '영상 제외';

  // 1. Nerinyan (보통 글로벌 CDN을 사용하여 매우 빠름)
  try {
    updateProgress(10, `초고속 미러 요청 중.. (Nerinyan, ${modeText})`);
    const nerinyanUrl = includeVideo 
      ? `https://api.nerinyan.moe/d/${setId}`
      : `https://api.nerinyan.moe/d/${setId}?novideo=1`;
    const res = await fetch(nerinyanUrl);
    if (res.ok) return await res.blob();
  } catch (err) {
    console.warn("Nerinyan 실패 -> 다음 미러 시도");
  }

  // 2. Sayobot (아시아 지역 전용 CDN으로 한국에서 매우 빠름)
  try {
    updateProgress(15, `초고속 아시아 미러 요청 중.. (Sayobot, ${modeText})`);
    const sayobotUrl = includeVideo
      ? `https://txy1.sayobot.cn/beatmaps/download/full/${setId}`
      : `https://txy1.sayobot.cn/beatmaps/download/novideo/${setId}`;
    const res = await fetch(sayobotUrl);
    if (res.ok) return await res.blob();
  } catch (err) {
    console.warn("Sayobot 실패 -> 다음 미러 시도");
  }

  // 3. Catboy (기존 백업 미러)
  try {
    updateProgress(20, `대체 미러 서버 요청 중.. (Catboy, ${modeText})`);
    const catboyUrl = includeVideo
      ? `https://catboy.best/d/${setId}`
      : `https://catboy.best/d/${setId}n`;
    const res = await fetch(catboyUrl);
    if (res.ok) return await res.blob();
  } catch (err) {
    console.warn("Catboy 실패 -> 공식 서버 전환");
  }

  // 4. 공식 서버 (마지막 보루, 속도 제한이 걸릴 수 있으며 로그인 필요 가능)
  try {
    updateProgress(25, `공식 서버 요청 중.. (${modeText})`);
    const officialUrl = includeVideo
      ? `https://osu.ppy.sh/d/${setId}`
      : `https://osu.ppy.sh/d/${setId}n`;
    const res = await fetch(officialUrl, { credentials: 'include' });
    const type = res.headers.get("content-type");
    if (type && type.includes("text/html")) throw new Error("봇 차단/로그인 필요");
    if (res.ok) return await res.blob();
  } catch (err) {
    console.warn("공식 서버 실패");
  }

  throw new Error("모든 서버에서 다운로드에 실패했습니다. 잠시 후 다시 시도해주세요.");
}

async function handleDownload() {
  if (!beatmapInfo || selectedDiffs.size === 0) return;
  els.btnDownload.disabled = true;
  els.barContainer.style.display = 'block';

  const includeVideo = Boolean(els.videoCheckbox && els.videoCheckbox.checked);

  try {
    const blob = await getFileBlob(beatmapInfo.setId, includeVideo);
    updateProgress(40, '파일 구조 분석 중...');
    const zip = new JSZip();
    const contents = await zip.loadAsync(blob);
    const allFiles = Object.keys(contents.files);
    
    if (!includeVideo) {
      updateProgress(50, '영상 파일 제거 중...');
      allFiles.forEach(fileName => {
          const lowerName = fileName.toLowerCase();
          if (VIDEO_EXTENSIONS.some(ext => lowerName.endsWith(ext))) {
              zip.remove(fileName);
          }
      });
    } else {
      updateProgress(50, '영상 파일 유지 중...');
    }

    updateProgress(60, '난이도 매칭 중...');
    const osuFiles = allFiles.filter(f => f.toLowerCase().endsWith('.osu'));
    
    const filesToRemove = [];
    let kept = 0;

    // 기호 파괴 클리너
    const cleanStrSafe = (str) => {
        if (!str) return "";
        const txt = document.createElement("textarea");
        txt.innerHTML = str;
        return txt.value.toLowerCase().replace(/[ \t\r\n\[\]\(\)\{\}\-\_\.\,\!\?\*\&\^\%\$\#\@\~\`\'\"\:\;\<\>\/\\\|\+]/g, '');
    };

    for (const file of osuFiles) {
      let diffNameInFile = "";
      try {
        const fileData = await zip.file(file).async("string");
        const vIdx = fileData.indexOf("Version:");
        if (vIdx !== -1) {
            const endIdx = fileData.indexOf("\n", vIdx);
            diffNameInFile = fileData.substring(vIdx + 8, endIdx !== -1 ? endIdx : fileData.length).trim();
        }
      } catch (e) {}

      const filenameMatch = file.match(/\[(.*)\]\.osu$/i);
      const diffNameInFilename = filenameMatch ? filenameMatch[1].trim() : "";

      const isSelected = Array.from(selectedDiffs).some(sel => {
        const target = cleanStrSafe(sel);
        const fileVer = cleanStrSafe(diffNameInFile);
        const nameVer = cleanStrSafe(diffNameInFilename);
        
        // 부분 일치 검사 (단어가 포함되어 있으면 통과!)
        return (target && fileVer && (target.includes(fileVer) || fileVer.includes(target))) ||
               (target && nameVer && (target.includes(nameVer) || nameVer.includes(target)));
      });

      if (!isSelected) {
        filesToRemove.push(file); // 일단 삭제 대기열에 넣음
      } else {
        kept++;
      }
    }

    // 🔥 최후의 보루: 하나도 못 찾았다면, 삭제를 취소하고 에러 대신 전체 난이도를 보존!
    if (kept === 0) {
        alert("선택한 난이도를 찾지 못했습니다. (서버 데이터 불일치)\n대신 전체 난이도를 유지하여 다운로드합니다.");
        // filesToRemove를 삭제하지 않음 = 모든 난이도가 살아남음
    } else {
        // 정상적으로 찾았다면, 선택 안 된 것들만 삭제
        filesToRemove.forEach(f => zip.remove(f));
    }

    updateProgress(80, '최적화된 패키지 생성 중...');
    const newBlob = await zip.generateAsync({ 
        type: 'blob', 
        compression: "STORE",
        mimeType: "application/octet-stream" 
    });
    
    updateProgress(100, '완료!');
    const url = URL.createObjectURL(newBlob);
    const downloadFilename = includeVideo 
      ? `${beatmapInfo.title}.osz` 
      : `${beatmapInfo.title} (NoVideo).osz`;

    chrome.downloads.download({
      url: url,
      filename: downloadFilename,
      saveAs: true
    }, () => {
      setTimeout(() => {
        els.barContainer.style.display = 'none';
        els.btnDownload.disabled = false;
        els.progressText.textContent = '';
      }, 2000);
    });

  } catch (err) {
    alert(`오류 발생:\n${err.message}`);
    els.btnDownload.disabled = false;
    els.barContainer.style.display = 'none';
  }
}

function updateProgress(percent, text) {
  els.progressBar.style.width = `${percent}%`;
  els.progressText.textContent = text;
}

els.btnClear.addEventListener('click', () => {
  selectedDiffs.clear(); 
  const items = els.container.querySelectorAll('.diff-item');
  items.forEach(item => {
    if (item._toggle) item._toggle(false);
  });
  updateUI();
});

els.btnAll.addEventListener('click', () => {
  const items = els.container.querySelectorAll('.diff-item');
  items.forEach(item => {
    if (item._toggle) item._toggle(true);
  });
  updateUI();
});

els.btnDownload.addEventListener('click', handleDownload);
document.addEventListener('DOMContentLoaded', () => {
  initVideoOption();
  fetchBeatmapData();
});