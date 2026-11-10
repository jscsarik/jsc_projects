import React from 'react';
import { Subtitles, Map, RotateCcw, Download } from 'lucide-react';

interface NavbarProps {
  onClearAll: () => void;
  onExportImage: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onClearAll, onExportImage }) => {
  return (
    <nav className="h-14 bg-slate-900 border-b border-slate-700 flex items-center justify-between px-6 z-50">
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-blue-500 rounded flex items-center justify-center">
          <Map size={20} className="text-white" />
        </div>
        <span className="text-white font-bold tracking-tight text-lg">
          SubwayMK <span className="text-slate-400 font-normal text-xs ml-1">v0.8.2</span>
        </span>
      </div>

      <div className="flex items-center gap-2">
        <button 
          onClick={onClearAll}
          className="px-4 py-2 text-sm text-slate-300 hover:text-white font-medium transition-colors cursor-pointer"
        >
          초기화
        </button>
        <button 
          onClick={onExportImage}
          className="px-5 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm font-semibold flex items-center gap-2 shadow-lg shadow-blue-500/20 transition-all cursor-pointer"
        >
          <Download size={16} />
          이미지로 저장
        </button>
      </div>
    </nav>
  );
};
