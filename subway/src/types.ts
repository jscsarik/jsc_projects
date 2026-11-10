export type ToolType = 'selection' | 'station';
export type StationType = 'local' | 'transfer';

export interface EditorState {
  selectedTool: ToolType;
  selectedStationType: StationType;
  setTool: (tool: ToolType) => void;
  setStationType: (type: StationType) => void;
}
