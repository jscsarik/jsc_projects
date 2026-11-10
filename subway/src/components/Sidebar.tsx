import React from 'react';
import { PenTool, MousePointer2, Type, Eraser, RotateCcw, Trash2, Download } from 'lucide-react';
import { cn } from '../lib/utils';
import { Tool } from '../App';

interface SidebarProps {
  className?: string;
  tool: Tool;
  setTool: (tool: Tool) => void;
  selectedColor: string;
  setSelectedColor: (color: string) => void;
  strokeWidth: number;
  setStrokeWidth: (width: number) => void;
  onUndo: () => void;
  onClearAll: () => void;
  onExportImage: () => void;
  canUndo: boolean;
}

const COLORS = [
  '#ef4444', '#2563eb', '#10b981', '#f59e0b', '#8b5cf6', 
  '#fbbf24', '#ec4899', '#0f172a', '#38bdf8', '#4338ca',
  '#64748b', '#000000'
];

export const Sidebar: React.FC<SidebarProps> = ({ 
  className, 
  tool,
  setTool,
  selectedColor,
  setSelectedColor,
  strokeWidth,
  setStrokeWidth,
  onUndo,
  onClearAll,
  onExportImage,
  canUndo
}) => {
  return (
    <aside className={cn("w-72 bg-white border-r border-slate-200 flex flex-col z-40 shadow-2xl transition-all", className)}>
      <div className="p-6 border-b border-slate-100 space-y-5">
        <div className="flex items-center justify-between pl-1">
          <span className="text-[11px] font-black text-slate-400 uppercase tracking-widest">도구 선택</span>
          <div className="flex gap-1.5">
            <button 
              onClick={onUndo}
              disabled={!canUndo}
              className={cn(
                "p-2 rounded-lg border transition-all cursor-pointer",
                canUndo ? "bg-white border-slate-200 text-slate-600 hover:bg-slate-50 active:scale-90" : "bg-slate-50 border-slate-100 text-slate-200 cursor-not-allowed"
              )}
              title="실행 취소 (Ctrl+Z)"
            >
              <RotateCcw size={14} />
            </button>
            <button 
              onClick={onExportImage}
              className="p-2 rounded-lg border border-slate-200 text-slate-600 hover:bg-slate-50 transition-all cursor-pointer active:scale-90"
              title="이미지로 저장"
            >
              <Download size={14} />
            </button>
            <button 
              onClick={onClearAll}
              className="p-2 rounded-lg border border-slate-200 text-red-500 hover:bg-red-50 hover:border-red-100 transition-all cursor-pointer active:scale-90"
              title="캔버스 초기화"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <button 
            onClick={() => setTool('pen')}
            className={cn(
              "py-4 rounded-xl border-2 flex flex-col items-center gap-2 transition-all cursor-pointer group",
              tool === 'pen' ? "bg-blue-50 border-blue-500 text-blue-600 shadow-md scale-[1.02]" : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
            )}
          >
            <PenTool size={22} className={tool === 'pen' ? "animate-pulse" : ""} />
            <span className="text-[10px] font-bold uppercase tracking-tight">자유 드로잉</span>
          </button>
          <button 
            onClick={() => setTool('station')}
            className={cn(
              "py-4 rounded-xl border-2 flex flex-col items-center gap-2 transition-all cursor-pointer group",
              tool === 'station' ? "bg-emerald-50 border-emerald-500 text-emerald-600 shadow-md scale-[1.02]" : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
            )}
          >
            <Type size={22} />
            <span className="text-[10px] font-bold uppercase tracking-tight">역 도장 찍기</span>
          </button>
          <button 
            onClick={() => setTool('eraser')}
            className={cn(
              "py-4 rounded-xl border-2 flex flex-col items-center gap-2 transition-all cursor-pointer group",
              tool === 'eraser' ? "bg-pink-50 border-pink-500 text-pink-600 shadow-md scale-[1.02]" : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
            )}
          >
            <Eraser size={22} />
            <span className="text-[10px] font-bold uppercase tracking-tight">지우개</span>
          </button>
          <button 
            onClick={() => setTool('select')}
            className={cn(
              "py-4 rounded-xl border-2 flex flex-col items-center gap-2 transition-all cursor-pointer group",
              tool === 'select' ? "bg-slate-900 border-slate-900 text-white shadow-lg scale-[1.02]" : "bg-white border-slate-100 text-slate-400 hover:border-slate-200"
            )}
          >
            <MousePointer2 size={22} />
            <span className="text-[10px] font-bold uppercase tracking-tight">선택 및 이동</span>
          </button>
        </div>
      </div>

      <div className="p-6 border-b border-slate-100 flex-1 bg-slate-50/20 overflow-y-auto">
        <span className="text-[11px] font-black text-slate-400 uppercase tracking-widest block mb-5 pl-1">색상 & 브러시</span>
        
        <div className="grid grid-cols-4 gap-3 mb-8">
          {COLORS.map((color) => (
            <button
              key={color}
              onClick={() => setSelectedColor(color)}
              className={cn(
                "w-full aspect-square rounded-full border-2 transition-all cursor-pointer relative",
                selectedColor === color ? "border-slate-900 scale-110 shadow-md z-10" : "border-white shadow-sm hover:scale-105"
              )}
              style={{ backgroundColor: color }}
            >
              {selectedColor === color && <div className="absolute inset-0 rounded-full border border-white opacity-40" />}
            </button>
          ))}
        </div>
        
        <div className="space-y-6">
          <div className="p-4 bg-white rounded-2xl border border-slate-100 shadow-sm space-y-4">
            <div className="flex justify-between items-center">
              <span className="text-[10px] text-slate-400 font-black uppercase tracking-wider">브러시 굵기</span>
              <span className="text-xs font-mono font-black text-slate-900 px-3 py-1 bg-slate-100 rounded-full">{strokeWidth}px</span>
            </div>
            <input 
              type="range" 
              min={tool === 'eraser' ? "4" : "2"}
              max={tool === 'eraser' ? "100" : "60"}
              step="2"
              value={strokeWidth}
              onChange={(e) => setStrokeWidth(parseInt(e.target.value))}
              className="w-full h-2 bg-slate-100 rounded-lg appearance-none cursor-pointer accent-slate-900"
            />
          </div>
        </div>
      </div>
      
      <div className="p-6 bg-slate-950 text-white">
        <div className="space-y-4">
          <div className="flex items-start gap-3">
             <div className="mt-1 w-1.5 h-1.5 rounded-full bg-blue-500 flex-shrink-0 shadow-[0_0_8px_rgba(59,130,246,0.5)]" />
             <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
               <span className="text-blue-400 font-bold">Shift</span>를 누르면 <span className="text-slate-200">10도 단위</span>로 꺾이는 직선을 그립니다.
             </p>
          </div>
          <div className="flex items-start gap-3">
             <div className="mt-1 w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
             <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
               <span className="text-emerald-400 font-bold">선택 모드</span>에서 역을 <span className="text-slate-200">더블 클릭</span>하여 이름을 수정하세요.
             </p>
          </div>
        </div>
      </div>
    </aside>
  );
};
