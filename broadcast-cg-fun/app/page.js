import Link from 'next/link';

export default function HomePage() {
  return (
    <main className="min-h-screen bg-neutral-950 text-neutral-100 flex flex-col justify-center items-center p-6 select-none">
      <div className="w-full max-w-lg bg-neutral-900/90 border border-neutral-800 rounded-3xl p-8 shadow-2xl backdrop-blur-xl text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600/20 text-indigo-400 text-3xl mb-4 border border-indigo-500/30">
          🎙️
        </div>
        <h1 className="text-3xl font-extrabold text-white mb-2">
          실시간 방송 전광판 시스템
        </h1>
        <p className="text-sm text-neutral-400 mb-8">
          원하시는 페이지를 선택해 접속하세요.
        </p>

        <div className="space-y-4">
          {/* 리모컨 링크 */}
          <Link
            href="/remote"
            className="block w-full py-4 px-6 rounded-2xl font-bold text-lg text-white bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 hover:opacity-90 active:scale-[0.98] transition-all shadow-lg shadow-indigo-500/25"
          >
            📱 송신용 리모컨 열기 (/remote)
          </Link>

          {/* 오버레이 화면 링크 */}
          <Link
            href="/screen"
            className="block w-full py-4 px-6 rounded-2xl font-bold text-lg text-neutral-200 bg-neutral-800 border border-neutral-700 hover:bg-neutral-750 active:scale-[0.98] transition-all"
          >
            📺 OBS / 오버레이 화면 열기 (/screen)
          </Link>
        </div>

        <div className="mt-8 pt-6 border-t border-neutral-800/80 text-xs text-neutral-500 text-left space-y-1.5">
          <p>• <strong>OBS 설정:</strong> 브라우저 소스 URL에 <code className="text-indigo-400 bg-neutral-800 px-1.5 py-0.5 rounded">/screen</code> 경로를 넣으세요.</p>
          <p>• <strong>시청자/친구 공유:</strong> 스마트폰으로 <code className="text-indigo-400 bg-neutral-800 px-1.5 py-0.5 rounded">/remote</code> 링크를 전달하세요.</p>
        </div>
      </div>
    </main>
  );
}
