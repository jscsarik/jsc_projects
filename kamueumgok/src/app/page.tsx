"use client";

import { useState, useEffect, useRef, useMemo } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Play, Pause, SkipBack, SkipForward, Library, Music, Disc3,
  FolderSearch, User, Tags, ArrowLeft, Image as ImageIcon
} from 'lucide-react';

interface Song {
  path: string;
  title: string;
  artist: string;
  album: string;
  genre: string;
  duration: number;
  picture: string | null;
  track?: number;
}

type TabType = 'all' | 'albums' | 'artists' | 'genres';

export default function App() {
  const [library, setLibrary] = useState<Song[]>([]);
  const [currentSongIndex, setCurrentSongIndex] = useState<number>(-1);
  const [currentPlaylist, setCurrentPlaylist] = useState<Song[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  const [activeTab, setActiveTab] = useState<TabType>('all');
  const [selectedGroup, setSelectedGroup] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);

  // currentSong은 currentPlaylist 기반이 아니라 전체 재생 목록 문맥에 의존하지만,
  // 깔끔하게 재생은 currentPlaylist 기반으로 동작하게 한다고 하면 복잡해지므로, 
  // 여기서는 단순히 어떤 곡이 선택되었는지 전역 인덱스 대신, 현재 재생중인 곡 객체 자체를 추적하는게 나을 수 있습니다.
  const [currentSong, setCurrentSong] = useState<Song | null>(null);

  useEffect(() => {
    const loadCachedLibrary = async () => {
      if (typeof window !== 'undefined' && (window as any).electronAPI) {
        const cached = await (window as any).electronAPI.loadLibrary();
        if (cached && cached.length > 0) {
          setLibrary(cached);
        }
      }
    };
    loadCachedLibrary();
  }, []);

  // library가 업데이트되면 초기화
  useEffect(() => {
    // 첫 로드 후 폴더 스캔으로 곡이 추가되면 기본 곡 설정은 생략하고, 그냥 둡니다.
  }, [library]);

  useEffect(() => {
    audioRef.current = new Audio();
    audioRef.current.crossOrigin = "anonymous";

    const updateProgress = () => {
      if (audioRef.current && audioRef.current.duration) {
        setProgress((audioRef.current.currentTime / audioRef.current.duration) * 100);
        setCurrentTime(audioRef.current.currentTime);
      }
    };

    audioRef.current.addEventListener('timeupdate', updateProgress);

    return () => {
      if (audioRef.current) {
        audioRef.current.removeEventListener('timeupdate', updateProgress);
        audioRef.current.pause();
      }
    };
  }, []);

  useEffect(() => {
    if (currentSong && audioRef.current) {
      const audio = audioRef.current;

      // AbortError 방지를 위한 명시적 pause
      audio.pause();

      // ★ 이 부분에 딱 한 줄을 추가하세요! (곡이 끝나면 다음 곡으로 넘어가도록 엔진에 묶어둡니다)
      audio.onended = handleNext;
 
      const encodedPath = encodeURIComponent(currentSong.path.replace(/\\/g, '/'));
      audio.src = `music-app://local/${encodedPath}`;

      audio.load();

      const playPromise = audio.play();
      if (playPromise !== undefined) {
        playPromise.then(() => {
          setIsPlaying(true);
        }).catch((err) => {
          console.error("Playback failed or aborted:", err);
          setIsPlaying(false);
        });
      }
    }
  }, [currentSong]);

  const handlePlayPause = () => {
    if (!audioRef.current || !currentSong) return;

    if (isPlaying) {
      audioRef.current.pause();
      setIsPlaying(false);
    } else {
      const playPromise = audioRef.current.play();
      if (playPromise !== undefined) {
        playPromise.then(() => {
          setIsPlaying(true);
        }).catch((err) => {
          console.error("Playback failed:", err);
        });
      }
    }
  };

  const handlePrev = () => {
    if (currentPlaylist.length === 0 || !currentSong) return;
    const idx = currentPlaylist.findIndex(s => s.path === currentSong.path);
    if (idx === -1) return;
    const prevIdx = idx > 0 ? idx - 1 : currentPlaylist.length - 1;
    setCurrentSong(currentPlaylist[prevIdx]);
  };

  const handleNext = () => {
    if (currentPlaylist.length === 0 || !currentSong) return;
    const idx = currentPlaylist.findIndex(s => s.path === currentSong.path);
    if (idx === -1) return;
    const nextIdx = idx < currentPlaylist.length - 1 ? idx + 1 : 0;
    setCurrentSong(currentPlaylist[nextIdx]);
  };

  const playSong = (song: Song, contextPlaylist: Song[]) => {
    setCurrentPlaylist(contextPlaylist);
    setCurrentSong(song);
  };

  const handleScan = async () => {
    if (typeof window !== 'undefined' && (window as any).electronAPI) {
      const res = await (window as any).electronAPI.scanLibrary();
      if (res && res.length > 0) {
        setLibrary(prev => {
          // 중복 방지 로직 (단순 파일 경로 기반)
          const newSongs = res.filter((newSong: Song) => !prev.some(p => p.path === newSong.path));
          return [...prev, ...newSongs];
        });
      }
    } else {
      alert("Electron API not defined. App is strictly for Electron env.");
    }
  };

  const formatTime = (seconds: number) => {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s < 10 ? '0' : ''}${s}`;
  };

  const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (audioRef.current) {
      const val = parseFloat(e.target.value);
      const newTime = (val / 100) * (audioRef.current.duration || 0);
      audioRef.current.currentTime = newTime;
      setProgress(val);
      setCurrentTime(newTime);
    }
  };

 // 데이터 그룹화 로직
  const groupedData = useMemo(() => {
    if (activeTab === 'all') return { All: library };

    const groups: Record<string, Song[]> = {};
    library.forEach(song => {
      let key = 'Unknown';
      if (activeTab === 'albums') key = song.album || 'Unknown Album';
      else if (activeTab === 'artists') key = song.artist || 'Unknown Artist';
      else if (activeTab === 'genres') key = song.genre || 'Unknown Genre';

      if (!groups[key]) groups[key] = [];
      groups[key].push(song);
    });

    const sortedGroups: Record<string, Song[]> = {};
    Object.keys(groups).sort().forEach(key => {
      // ★ 앨범 탭일 경우 트랙 번호순으로, 아닐 경우 제목순으로 정렬
      const sortedSongs = groups[key].sort((a, b) => {
        if (activeTab === 'albums') {
          return (a.track || 0) - (b.track || 0);
        }
        return a.title.localeCompare(b.title);
      });
      sortedGroups[key] = sortedSongs;
    });

    return sortedGroups;
  }, [library, activeTab]);

  const changeTab = (tab: TabType) => {
    setActiveTab(tab);
    setSelectedGroup(null);
  };

  // 렌더링 헬퍼: 곡 리스트 렌더링
  const renderSongsGrid = (songs: Song[]) => (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-6"
    >
      {songs.map((song, idx) => {
        const isCurrent = currentSong?.path === song.path;
        return (
          <motion.div
            key={song.path + idx}
            whileHover={{ scale: 1.03 }}
            whileTap={{ scale: 0.97 }}
            className={`group cursor-pointer rounded-2xl overflow-hidden bg-neutral-800/40 hover:bg-neutral-800/80 transition-all p-4 border ${isCurrent ? 'border-rose-500/50 bg-neutral-800/80' : 'border-neutral-800 hover:border-neutral-700'} backdrop-blur-sm flex flex-col`}
            onClick={() => playSong(song, songs)}
          >
            <div className="aspect-square bg-neutral-900 rounded-xl mb-4 overflow-hidden shadow-lg relative flex-shrink-0">
              {song.picture ? (
                <img src={song.picture} crossOrigin="anonymous" alt="Album Art" className="w-full h-full object-cover transition duration-500 group-hover:scale-110" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-neutral-600 bg-neutral-800/50">
                  <Music size={40} className="opacity-40" />
                </div>
              )}
              <div className={`absolute inset-0 bg-black/50 transition-opacity flex items-center justify-center ${isCurrent && isPlaying ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}>
                {isCurrent && isPlaying ? (
                  <div className="flex items-center gap-1.5">
                    <motion.div animate={{ height: [10, 24, 10] }} transition={{ repeat: Infinity, duration: 0.6 }} className="w-1.5 bg-rose-500 rounded-full" />
                    <motion.div animate={{ height: [14, 30, 14] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.2 }} className="w-1.5 bg-rose-500 rounded-full" />
                    <motion.div animate={{ height: [10, 24, 10] }} transition={{ repeat: Infinity, duration: 0.6, delay: 0.4 }} className="w-1.5 bg-rose-500 rounded-full" />
                  </div>
                ) : (
                  <div className="w-12 h-12 rounded-full bg-rose-500/90 text-white flex items-center justify-center shadow-xl shadow-rose-500/30 transform translate-y-4 group-hover:translate-y-0 transition-all duration-300">
                    <Play fill="white" size={20} className="ml-1" />
                  </div>
                )}
              </div>
            </div>
            <div className="flex flex-col flex-1 min-h-0">
              <span className={`font-semibold truncate text-base ${isCurrent ? 'text-rose-400' : 'text-white'}`}>{song.title}</span>
              <span className="text-sm text-neutral-400 truncate mt-1">{song.artist}</span>
            </div>
          </motion.div>
        );
      })}
    </motion.div>
  );

  // 렌더링 헬퍼: 그룹 (앨범, 아티스트, 장르) 카드 렌더링
  const renderGroupGrid = () => {
    const keys = Object.keys(groupedData);
    if (keys.length === 0) return null;

    return (
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-6"
      >
        {keys.map((key, idx) => {
          const songs = groupedData[key];
          // Use the first song's picture as the group thumbnail
          const thumbnail = songs.find(s => s.picture)?.picture;

          let Icon = Disc3;
          if (activeTab === 'artists') Icon = User;
          if (activeTab === 'genres') Icon = Tags;

          return (
            <motion.div
              key={key + idx}
              whileHover={{ scale: 1.03 }}
              whileTap={{ scale: 0.97 }}
              className="group cursor-pointer rounded-2xl overflow-hidden bg-neutral-800/30 hover:bg-neutral-800/70 py-6 px-4 border border-neutral-800 flex flex-col items-center text-center transition-all"
              onClick={() => setSelectedGroup(key)}
            >
              <div className={`w-32 h-32 mb-4 overflow-hidden shadow-lg relative ${activeTab === 'artists' ? 'rounded-full' : 'rounded-xl'}`}>
                {thumbnail ? (
                  <img src={thumbnail} crossOrigin="anonymous" alt={key} className="w-full h-full object-cover transition duration-500 group-hover:scale-110" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-neutral-800 text-neutral-600">
                    <Icon size={48} className="opacity-30" />
                  </div>
                )}
                <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors" />
              </div>
              <h3 className="font-bold text-white text-lg truncate w-full px-2">{key}</h3>
              <p className="text-sm text-neutral-400 mt-1">{songs.length} {songs.length === 1 ? 'song' : 'songs'}</p>
            </motion.div>
          );
        })}
      </motion.div>
    );
  };

  const SidebarButton = ({ icon, label, active, onClick }: { icon: React.ReactNode, label: string, active: boolean, onClick: () => void }) => (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 px-4 py-3 rounded-xl transition-all w-full text-left font-medium ${active ? 'bg-rose-500/10 text-rose-500 font-semibold' : 'text-neutral-400 hover:text-white hover:bg-neutral-800/50'}`}
    >
      {icon}
      {label}
    </button>
  );

  return (
    <div className="flex h-screen bg-neutral-950 text-neutral-100 font-sans overflow-hidden selection:bg-rose-500/30">
      {/* Sidebar */}
      <aside className="w-64 bg-neutral-900 border-r border-neutral-800 flex flex-col p-6 z-10 shrink-0">
        <h1 className="text-2xl font-extrabold mb-8 flex items-center gap-3 tracking-tight text-white">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-rose-500 to-rose-700 flex items-center justify-center shadow-lg shadow-rose-500/30">
            <Disc3 className="text-white" size={24} />
          </div>
          KaMuEumGok
        </h1>

        {/* 상시 고정 버튼: 항상 접근하기 쉽도록 상단 메뉴 위에 배치 */}
        <button
          onClick={handleScan}
          className="flex items-center justify-center gap-2 bg-neutral-800 hover:bg-neutral-700 text-white py-3 px-4 rounded-xl transition-all mb-8 border border-neutral-700 hover:border-neutral-600 shadow-sm font-medium w-full group"
        >
          <FolderSearch size={20} className="text-rose-400 group-hover:text-rose-300 transition-colors" />
          Scan Folder
        </button>

        <div className="text-xs font-bold text-neutral-500 uppercase tracking-wider mb-3 px-4">Your Library</div>
        <nav className="flex-1 space-y-1">
          <SidebarButton active={activeTab === 'all'} onClick={() => changeTab('all')} icon={<Library size={20} />} label="All Songs" />
          <SidebarButton active={activeTab === 'albums'} onClick={() => changeTab('albums')} icon={<Disc3 size={20} />} label="Albums" />
          <SidebarButton active={activeTab === 'artists'} onClick={() => changeTab('artists')} icon={<User size={20} />} label="Artists" />
          <SidebarButton active={activeTab === 'genres'} onClick={() => changeTab('genres')} icon={<Tags size={20} />} label="Genres" />
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-y-auto bg-gradient-to-br from-neutral-900 via-neutral-950 to-neutral-950 relative pb-32">
        {library.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-neutral-500 max-w-md mx-auto px-6 text-center">
            <div className="w-32 h-32 bg-neutral-800/50 rounded-full flex items-center justify-center mb-8 border border-neutral-800 shadow-2xl relative">
              <Music size={48} className="text-neutral-400" />
              <div className="absolute -bottom-2 -right-2 bg-rose-500 w-12 h-12 rounded-full flex items-center justify-center border-4 border-neutral-950">
                <FolderSearch size={20} className="text-white" />
              </div>
            </div>
            <h2 className="text-3xl font-bold text-white mb-4">No music found</h2>
            <p className="text-neutral-400 mb-10 text-lg">
              Your library is currently empty. Add your local music folders to start listening.
            </p>
            {/* 중앙 빈 화면 스캔 버튼 (크고 강조됨) */}
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={handleScan}
              className="flex items-center gap-3 bg-rose-600 hover:bg-rose-500 text-white py-4 px-10 rounded-2xl transition-all shadow-[0_0_30px_rgba(225,29,72,0.3)] hover:shadow-[0_0_40px_rgba(225,29,72,0.5)] font-bold text-lg"
            >
              <FolderSearch size={24} />
              Add Local Music
            </motion.button>
          </div>
        ) : (
          <div className="p-8 lg:p-12">
            <div className="flex items-center justify-between mb-10">
              <h2 className="text-4xl font-extrabold tracking-tight capitalize flex items-center gap-4">
                {selectedGroup ? (
                  <>
                    <button
                      onClick={() => setSelectedGroup(null)}
                      className="p-2 bg-neutral-800 hover:bg-neutral-700 rounded-full transition-colors text-neutral-300"
                    >
                      <ArrowLeft size={24} />
                    </button>
                    {selectedGroup}
                  </>
                ) : (
                  activeTab.replace('-', ' ')
                )}
              </h2>

              {!selectedGroup && (
                <span className="text-neutral-400 font-medium">
                  {activeTab === 'all'
                    ? `${library.length} songs`
                    : `${Object.keys(groupedData).length} ${activeTab}`}
                </span>
              )}
            </div>

            <AnimatePresence mode="wait">
              <motion.div
                key={activeTab + (selectedGroup || '')}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2 }}
              >
                {activeTab === 'all' ? (
                  renderSongsGrid(library)
                ) : selectedGroup ? (
                  renderSongsGrid(groupedData[selectedGroup] || [])
                ) : (
                  renderGroupGrid()
                )}
              </motion.div>
            </AnimatePresence>
          </div>
        )}
      </main>

      {/* Floating Player Bar */}
      <div className={`absolute bottom-0 left-0 right-0 h-24 bg-neutral-900/95 backdrop-blur-2xl border-t border-white/5 px-6 flex items-center justify-between z-50 transition-transform duration-500 ${currentSong ? 'translate-y-0' : 'translate-y-full'}`}>
        {/* Left: Now Playing Info */}
        <div className="flex items-center gap-4 w-1/3">
          {currentSong && (
            <>
              <div className="w-14 h-14 bg-neutral-800 rounded-xl overflow-hidden shadow-lg border border-neutral-700/50 flex-shrink-0">
                {currentSong.picture ? (
                  <img src={currentSong.picture} crossOrigin="anonymous" alt="Current Album" className="w-full h-full object-cover" />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-neutral-500 bg-neutral-800">
                    <Music size={24} />
                  </div>
                )}
              </div>
              <div className="flex flex-col min-w-0">
                <span className="font-bold text-white truncate text-base">{currentSong.title}</span>
                <span className="text-xs text-neutral-400 truncate mt-0.5 font-medium">{currentSong.artist}</span>
              </div>
            </>
          )}
        </div>

        {/* Center: Controls & Progress */}
        <div className="flex flex-col items-center w-2/5 max-w-xl gap-2.5">
          <div className="flex items-center gap-6">
            <button onClick={handlePrev} className="text-neutral-400 hover:text-white transition-colors" disabled={!currentSong}>
              <SkipBack size={20} fill="currentColor" />
            </button>
            <button
              onClick={handlePlayPause}
              disabled={!currentSong}
              className="w-12 h-12 flex items-center justify-center bg-white text-black rounded-full hover:scale-105 active:scale-95 transition-all shadow-[0_0_15px_rgba(255,255,255,0.2)] disabled:opacity-50 disabled:hover:scale-100"
            >
              {isPlaying ? <Pause fill="currentColor" size={20} /> : <Play fill="currentColor" size={20} className="ml-1" />}
            </button>
            <button onClick={handleNext} className="text-neutral-400 hover:text-white transition-colors" disabled={!currentSong}>
              <SkipForward size={20} fill="currentColor" />
            </button>
          </div>
          <div className="w-full flex items-center gap-4">
            <span className="text-xs font-medium text-neutral-500 w-10 text-right font-mono">
              {formatTime(currentTime)}
            </span>
            <input
              type="range"
              min="0"
              max="100"
              value={progress || 0}
              onChange={handleSeek}
              disabled={!currentSong}
              className="w-full h-1.5 bg-neutral-800 rounded-full appearance-none [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:bg-white [&::-webkit-slider-thumb]:rounded-full cursor-pointer accent-white transition-all hover:[&::-webkit-slider-thumb]:w-4 hover:[&::-webkit-slider-thumb]:h-4 disabled:opacity-50 group hover:accent-rose-500"
            />
            <span className="text-xs font-medium text-neutral-500 w-10 font-mono">
              {currentSong ? formatTime(currentSong.duration) : '0:00'}
            </span>
          </div>
        </div>

        {/* Right: Extra Controls (Volume etc, omitted for space but layout ready) */}
        <div className="w-1/3 flex justify-end">
          {/* placeholder for volume control */}
        </div>
      </div>
    </div>
  );
}
