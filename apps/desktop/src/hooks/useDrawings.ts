/**
 * Hook for CRUD operations on chart drawings.
 * Persists to localStorage per panel.
 */

import { useState, useCallback, useEffect } from "react";
import {
  Drawing,
  DrawingTool,
  loadDrawings,
  saveDrawings,
  generateDrawingId,
  DEFAULT_DRAWING_COLOR,
  filterDrawingsForChart,
} from "../lib/drawings";

interface UseDrawingsOptions {
  panelId: string;
  symbol: string;
  timeframe: string;
}

interface UseDrawingsResult {
  /** All drawings for this panel */
  allDrawings: Drawing[];
  /** Drawings filtered for current symbol+timeframe */
  chartDrawings: Drawing[];
  /** Currently active drawing tool */
  activeTool: DrawingTool;
  setActiveTool: (tool: DrawingTool) => void;
  /** Add a new drawing */
  addDrawing: (drawing: Omit<Drawing, "id">) => Drawing;
  /** Update an existing drawing */
  updateDrawing: (id: string, updates: Partial<Drawing>) => void;
  /** Delete a drawing */
  deleteDrawing: (id: string) => void;
  /** Delete all drawings for current symbol+timeframe */
  clearDrawings: () => void;
}

export function useDrawings({
  panelId,
  symbol,
  timeframe,
}: UseDrawingsOptions): UseDrawingsResult {
  const [drawings, setDrawings] = useState<Drawing[]>(() =>
    loadDrawings(panelId)
  );
  const [activeTool, setActiveTool] = useState<DrawingTool>("select");

  // Save on change
  useEffect(() => {
    saveDrawings(panelId, drawings);
  }, [panelId, drawings]);

  // Reload when panelId changes
  useEffect(() => {
    setDrawings(loadDrawings(panelId));
  }, [panelId]);

  const chartDrawings = filterDrawingsForChart(drawings, symbol, timeframe);

  const addDrawing = useCallback(
    (drawing: Omit<Drawing, "id">): Drawing => {
      const newDrawing: Drawing = {
        ...drawing,
        id: generateDrawingId(),
        color: drawing.color || DEFAULT_DRAWING_COLOR,
      };
      setDrawings((prev) => [...prev, newDrawing]);
      return newDrawing;
    },
    []
  );

  const updateDrawing = useCallback((id: string, updates: Partial<Drawing>) => {
    setDrawings((prev) =>
      prev.map((d) => (d.id === id ? { ...d, ...updates } : d))
    );
  }, []);

  const deleteDrawing = useCallback((id: string) => {
    setDrawings((prev) => prev.filter((d) => d.id !== id));
  }, []);

  const clearDrawings = useCallback(() => {
    setDrawings((prev) =>
      prev.filter((d) => !(d.symbol === symbol && d.timeframe === timeframe))
    );
  }, [symbol, timeframe]);

  return {
    allDrawings: drawings,
    chartDrawings,
    activeTool,
    setActiveTool,
    addDrawing,
    updateDrawing,
    deleteDrawing,
    clearDrawings,
  };
}
