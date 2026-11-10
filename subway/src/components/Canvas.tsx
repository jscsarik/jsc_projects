import React, { useRef, useState, useEffect } from 'react';
import { Stage, Layer, Line as KonvaLine, Circle, Text, Group, Rect } from 'react-konva';
import { Line, Station, Tool } from '../App';

interface CanvasProps {
  lines: Line[];
  setLines: React.Dispatch<React.SetStateAction<Line[]>>;
  stations: Station[];
  setStations: React.Dispatch<React.SetStateAction<Station[]>>;
  tool: Tool;
  selectedColor: string;
  strokeWidth: number;
  saveHistory: () => void;
  onStationNameChange: (id: string, newName: string) => void;
  onStationDelete: (id: string) => void;
  onLineDelete: (index: number) => void;
}

export const Canvas: React.FC<CanvasProps> = ({
  lines,
  setLines,
  stations,
  setStations,
  tool,
  selectedColor,
  strokeWidth,
  saveHistory,
  onStationNameChange,
  onStationDelete,
  onLineDelete,
}) => {
  const isDrawing = useRef(false);
  const stageRef = useRef<any>(null);
  const gridLayerRef = useRef<any>(null);
  const [size, setSize] = useState({ width: window.innerWidth, height: window.innerHeight });

  useEffect(() => {
    const handleResize = () => {
      setSize({ width: window.innerWidth, height: window.innerHeight });
    };
    window.addEventListener('resize', handleResize);
    
    // For Export Feature
    if (stageRef.current) {
      (window as any).canvasStage = stageRef.current;
      (window as any).gridLayer = gridLayerRef.current;
    }

    return () => window.removeEventListener('resize', handleResize);
  }, []);

  const handleMouseDown = (e: any) => {
    if (tool === 'select') return;
    
    saveHistory();
    const pos = e.target.getStage().getPointerPosition();

    if (tool === 'pen' || tool === 'eraser') {
      isDrawing.current = true;
      setLines([...lines, { 
        points: [pos.x, pos.y], 
        color: tool === 'eraser' ? '#ffffff' : selectedColor, 
        width: strokeWidth,
        globalCompositeOperation: tool === 'eraser' ? 'destination-out' : 'source-over'
      } as any]);
    } else if (tool === 'station') {
      const newStation: Station = {
        id: `station-${Date.now()}`,
        x: pos.x,
        y: pos.y,
        name: '새 역',
      };
      setStations([...stations, newStation]);
    }
  };

  const handleMouseMove = (e: any) => {
    if (!isDrawing.current || (tool !== 'pen' && tool !== 'eraser')) return;

    const stage = e.target.getStage();
    const point = stage.getPointerPosition();
    let updatedLines = [...lines];
    let lastLine = { ...updatedLines[updatedLines.length - 1] };
    
    if (e.evt.shiftKey && lastLine.points.length >= 2 && tool === 'pen') {
      // Shift Snap Logic: Snap to 10-degree increments
      const startX = lastLine.points[0];
      const startY = lastLine.points[1];
      const dx = point.x - startX;
      const dy = point.y - startY;

      // Calculate distance and angle (in radians)
      const radius = Math.sqrt(dx * dx + dy * dy);
      const angleInRadians = Math.atan2(dy, dx);
      
      // Convert to degrees, snap to 10 degree increments, then back to radians
      const angleInDegrees = (angleInRadians * 180) / Math.PI;
      const snappedDegrees = Math.round(angleInDegrees / 10) * 10;
      const snappedRadians = (snappedDegrees * Math.PI) / 180;

      const finalX = startX + radius * Math.cos(snappedRadians);
      const finalY = startY + radius * Math.sin(snappedRadians);
      
      lastLine.points = [startX, startY, finalX, finalY];
    } else {
      // Normal freehand or eraser
      lastLine.points = lastLine.points.concat([point.x, point.y]);
    }

    updatedLines[updatedLines.length - 1] = lastLine;
    setLines(updatedLines);
  };

  const handleMouseUp = () => {
    isDrawing.current = false;
  };

  const handleStationClick = (id: string, name: string) => {
    if (tool !== 'select') return;
    const newName = window.prompt('역 이름을 입력하세요:', name);
    if (newName !== null) {
      onStationNameChange(id, newName);
    }
  };

  return (
    <div className="w-full h-full cursor-crosshair overflow-hidden bg-white">
      <Stage
        width={size.width}
        height={size.height}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        ref={stageRef}
      >
        {/* Layer 1: Persistent White Background */}
        <Layer>
          <Rect width={size.width} height={size.height} fill="white" />
        </Layer>

        {/* Layer 2: Background Grid */}
        <Layer ref={gridLayerRef}>
          {[...Array(Math.floor(size.width / 40))].map((_, i) => (
            <KonvaLine
              key={`v-${i}`}
              points={[i * 40, 0, i * 40, size.height]}
              stroke="#f1f5f9"
              strokeWidth={1}
            />
          ))}
          {[...Array(Math.floor(size.height / 40))].map((_, i) => (
            <KonvaLine
              key={`h-${i}`}
              points={[0, i * 40, size.width, i * 40]}
              stroke="#f1f5f9"
              strokeWidth={1}
            />
          ))}
        </Layer>

        {/* Layer 3: Subjects (Lines & Stations) */}
        <Layer>
          {/* Lines */}
          {lines.map((line, i) => (
            <KonvaLine
              key={i}
              points={line.points}
              stroke={line.color}
              strokeWidth={line.width}
              tension={0.5}
              lineCap="round"
              lineJoin="round"
              globalCompositeOperation={(line.globalCompositeOperation as any) || 'source-over'}
              onContextMenu={(e) => {
                e.evt.preventDefault();
                onLineDelete(i);
              }}
            />
          ))}

          {/* Stations */}
          {stations.map((s) => (
            <Group 
              key={s.id} 
              x={s.x} 
              y={s.y}
              draggable={tool === 'select'}
              onDragEnd={(e) => {
                saveHistory();
                const newStations = stations.map(st => 
                  st.id === s.id ? { ...st, x: e.target.x(), y: e.target.y() } : st
                );
                setStations(newStations);
              }}
              onDblClick={() => handleStationClick(s.id, s.name)}
              onDblTap={() => handleStationClick(s.id, s.name)}
              onMouseEnter={(e) => {
                if (tool === 'select') {
                  const container = e.target.getStage().container();
                  container.style.cursor = 'pointer';
                }
              }}
              onMouseLeave={(e) => {
                const container = e.target.getStage().container();
                container.style.cursor = tool === 'select' ? 'default' : 'crosshair';
              }}
              onContextMenu={(e) => {
                e.evt.preventDefault();
                onStationDelete(s.id);
              }}
            >
              <Circle
                radius={9}
                fill="white"
                stroke={tool === 'select' ? "#3b82f6" : "#1e293b"}
                strokeWidth={3}
                shadowBlur={s.id.includes('hover') ? 10 : 5}
                shadowColor="rgba(0,0,0,0.2)"
              />
              <Text
                text={s.name}
                fontSize={13}
                fontStyle="bold"
                fill="#334155"
                y={-24}
                align="center"
                width={120}
                offsetX={60}
              />
            </Group>
          ))}
        </Layer>
      </Stage>
    </div>
  );
};
