import React, { useCallback, useState, useEffect, useRef } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar } from './components/Sidebar';
import { Canvas } from './components/Canvas';

export interface Station {
  id: string;
  x: number;
  y: number;
  name: string;
}

export interface Line {
  points: number[];
  color: string;
  width: number;
  globalCompositeOperation?: string;
}

export type Tool = 'select' | 'pen' | 'station' | 'eraser';

export default function App() {
  const [lines, setLines] = useState<Line[]>([]);
  const [stations, setStations] = useState<Station[]>([]);
  const [currentTool, setCurrentTool] = useState<Tool>('pen');
  const [selectedColor, setSelectedColor] = useState('#ef4444');
  const [strokeWidth, setStrokeWidth] = useState(12);
  
  // History for Undo
  const [history, setHistory] = useState<{ lines: Line[]; stations: Station[] }[]>([]);
  
  const saveHistory = useCallback(() => {
    setHistory(prev => [...prev.slice(-19), { lines: JSON.parse(JSON.stringify(lines)), stations: JSON.parse(JSON.stringify(stations)) }]);
  }, [lines, stations]);

  const undo = useCallback(() => {
    if (history.length === 0) return;
    const last = history[history.length - 1];
    setLines(last.lines);
    setStations(last.stations);
    setHistory(prev => prev.slice(0, -1));
  }, [history]);

  const clearAll = useCallback(() => {
    if (window.confirm('모든 내용을 지우시겠습니까?')) {
      saveHistory();
      setLines([]);
      setStations([]);
    }
  }, [saveHistory]);

  // Keyboard Shortcuts (Undo)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'z') {
        e.preventDefault();
        undo();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [undo]);

  const handleStationNameChange = useCallback((id: string, newName: string) => {
    saveHistory();
    setStations(prev => prev.map(s => s.id === id ? { ...s, name: newName } : s));
  }, [saveHistory]);

  const handleStationDelete = useCallback((id: string) => {
    saveHistory();
    setStations(prev => prev.filter(s => s.id !== id));
  }, [saveHistory]);

  const handleLineDelete = useCallback((index: number) => {
    saveHistory();
    setLines(prev => prev.filter((_, i) => i !== index));
  }, [saveHistory]);

  const handleExportImage = useCallback(() => {
    const stage = (window as any).canvasStage;
    const gridLayer = (window as any).gridLayer;
    
    if (stage) {
      // Temporarily hide grid layer if it exists
      if (gridLayer) gridLayer.visible(false);
      
      // Create a high-quality dataURL with a white background
      const dataURL = stage.toDataURL({ 
        pixelRatio: 2, 
        backgroundColor: 'white' 
      });
      
      // Show grid layer again
      if (gridLayer) gridLayer.visible(true);
      
      const link = document.createElement('a');
      link.download = 'subway-map.png';
      link.href = dataURL;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }
  }, []);

  return (
    <div className="flex flex-col h-screen overflow-hidden text-slate-900 font-sans">
      <Navbar onClearAll={clearAll} onExportImage={handleExportImage} />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar 
          className="hidden md:flex" 
          tool={currentTool}
          setTool={setCurrentTool}
          selectedColor={selectedColor}
          setSelectedColor={setSelectedColor}
          strokeWidth={strokeWidth}
          setStrokeWidth={setStrokeWidth}
          onClearAll={clearAll}
          onUndo={undo}
          onExportImage={handleExportImage}
          canUndo={history.length > 0}
        />
        <main className="flex-1 relative bg-slate-100">
          <Canvas 
            lines={lines}
            setLines={setLines}
            stations={stations}
            setStations={setStations}
            tool={currentTool}
            selectedColor={selectedColor}
            strokeWidth={strokeWidth}
            saveHistory={saveHistory}
            onStationNameChange={handleStationNameChange}
            onStationDelete={handleStationDelete}
            onLineDelete={handleLineDelete}
          />
        </main>
      </div>
    </div>
  );
}
