/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Menu, X, Gamepad } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import rehypeRaw from 'rehype-raw';
import { GAMES } from './constants';

export default function App() {
  const [selectedGameId, setSelectedGameId] = useState(GAMES[0].id);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (contentRef.current) {
      contentRef.current.scrollTop = 0;
    }
  }, [selectedGameId]);

  const selectedGame = GAMES.find(game => game.id === selectedGameId) || GAMES[0];

  return (
    <div className="flex h-screen bg-[#36393f] text-[#dcddde] font-sans overflow-hidden">
      {/* Mobile Toggle */}
      <button 
        className="lg:hidden fixed top-4 left-4 z-50 p-2 bg-[#2f3136] rounded-md"
        onClick={() => setIsSidebarOpen(!isSidebarOpen)}
      >
        {isSidebarOpen ? <X className="text-white" /> : <Menu className="text-white" />}
      </button>

      {/* Sidebar */}
      <aside className={`fixed lg:relative z-40 w-64 h-full bg-[#2f3136] flex flex-col border-r border-[#202225] transition-transform duration-300 ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}`}>
        <div className="h-14 flex items-center px-4 shadow-md border-b border-[#202225] shrink-0">
          <h1 className="text-white font-bold text-sm tracking-wide uppercase flex items-center gap-2">
            <Gamepad className="w-5 h-5 text-[#5865F2]" /> 주제어 설명서
          </h1>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 space-y-0.5">
          {GAMES.map(game => (
            <button
              key={game.id}
              onClick={() => {
                setSelectedGameId(game.id);
                setIsSidebarOpen(false);
              }}
              className={`w-full flex items-center px-4 py-2 text-sm transition-colors ${
                selectedGameId === game.id 
                  ? 'bg-[#393d43] text-white font-medium rounded-md mx-2 w-[calc(100%-16px)]' 
                  : 'text-[#8e9297] hover:bg-[#393d43] hover:text-[#dcddde]'
              }`}
            >
              {game.title}
            </button>
          ))}
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-14 flex items-center justify-between px-6 bg-[#36393f] shadow-sm z-10 shrink-0">
          <div className="flex items-center space-x-2">
            <span className="text-[#8e9297] text-xl font-bold">#</span>
            <h2 className="text-white font-bold">{selectedGame.title}</h2>
          </div>
        </header>

        {/* Content Container */}
        <div ref={contentRef} className="flex-1 p-8 space-y-6 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div
              key={selectedGame.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.2 }}
              className="max-w-3xl mx-auto space-y-6"
            >
              {/* Hero section */}
              <div className="bg-[#40444b] rounded-lg p-6 border-l-4 border-[#5865F2]">
                <h3 className="text-white text-xl font-bold mb-2">게임 개요</h3>
                <p className="text-[#b9bbbe] leading-relaxed">
                  {selectedGame.summary}
                </p>
              </div>
              
              {/* Rules Grid */}
              <div className="space-y-4">
                <h3 className="text-lg font-semibold text-[#5865F2] uppercase tracking-wider">게임 규칙</h3>
                <div className="grid grid-cols-1 gap-6">
                  {selectedGame.rules.map((rule, idx) => (
                    <div key={idx} className="bg-[#2f3136] rounded-md p-6 border border-[#202225] shadow-lg transition-all hover:bg-[#32353b]">
                      <div className="text-[#dcddde] text-[15px] leading-relaxed markdown-body">
                        <ReactMarkdown rehypePlugins={[rehypeRaw]}>{rule}</ReactMarkdown>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
    </div>
  );
}
