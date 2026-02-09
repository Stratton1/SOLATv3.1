/**
 * Hook for managing workspaces with CRUD operations.
 *
 * Provides workspace state management and persistence.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Workspace,
  WorkspaceStore,
  Panel,
  LayoutType,
  loadWorkspaceStore,
  saveWorkspaceStore,
  createDefaultWorkspace,
  updateWorkspacePanels,
  updatePanel as updatePanelHelper,
  duplicateWorkspace,
} from "../lib/workspace";

// =============================================================================
// Types
// =============================================================================

interface UseWorkspaceResult {
  // Current workspace
  workspace: Workspace;
  workspaces: Workspace[];

  // Workspace CRUD
  createWorkspace: (name: string) => Workspace;
  switchWorkspace: (id: string) => void;
  renameWorkspace: (id: string, name: string) => void;
  deleteWorkspace: (id: string) => void;
  duplicateWorkspace: (id: string, newName: string) => Workspace;

  // Layout
  setLayout: (layout: LayoutType) => void;

  // Panel operations
  updatePanel: (panelId: string, updates: Partial<Panel>) => void;
  getPanel: (panelId: string) => Panel | undefined;

  // Link group operations
  setLinkedTimeframe: (linkGroup: string, timeframe: string) => void;
  setLinkedSymbol: (linkGroup: string, symbol: string) => void;
}

// =============================================================================
// Hook
// =============================================================================

export function useWorkspace(): UseWorkspaceResult {
  const [store, setStore] = useState<WorkspaceStore>(() => loadWorkspaceStore());
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  // Debounced save
  const saveStore = useCallback((newStore: WorkspaceStore) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveWorkspaceStore(newStore);
    }, 300);
  }, []);

  // Update store and trigger save
  const updateStore = useCallback(
    (updater: (prev: WorkspaceStore) => WorkspaceStore) => {
      setStore((prev) => {
        const next = updater(prev);
        saveStore(next);
        return next;
      });
    },
    [saveStore]
  );

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  // Get current workspace
  const workspace = useMemo(() => {
    return (
      store.workspaces.find((w) => w.id === store.activeWorkspaceId) ??
      store.workspaces[0] ??
      createDefaultWorkspace()
    );
  }, [store]);

  // CRUD operations
  const createWorkspaceHandler = useCallback(
    (name: string): Workspace => {
      const newWorkspace = createDefaultWorkspace(name);
      updateStore((prev) => ({
        activeWorkspaceId: newWorkspace.id,
        workspaces: [...prev.workspaces, newWorkspace],
      }));
      return newWorkspace;
    },
    [updateStore]
  );

  const switchWorkspaceHandler = useCallback(
    (id: string) => {
      updateStore((prev) => ({
        ...prev,
        activeWorkspaceId: id,
      }));
    },
    [updateStore]
  );

  const renameWorkspaceHandler = useCallback(
    (id: string, name: string) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === id
            ? { ...w, name, updatedAt: new Date().toISOString() }
            : w
        ),
      }));
    },
    [updateStore]
  );

  const deleteWorkspaceHandler = useCallback(
    (id: string) => {
      updateStore((prev) => {
        const remaining = prev.workspaces.filter((w) => w.id !== id);
        if (remaining.length === 0) {
          // Always keep at least one workspace
          const defaultWs = createDefaultWorkspace();
          return {
            activeWorkspaceId: defaultWs.id,
            workspaces: [defaultWs],
          };
        }
        return {
          activeWorkspaceId:
            prev.activeWorkspaceId === id
              ? remaining[0].id
              : prev.activeWorkspaceId,
          workspaces: remaining,
        };
      });
    },
    [updateStore]
  );

  const duplicateWorkspaceHandler = useCallback(
    (id: string, newName: string): Workspace => {
      const source = store.workspaces.find((w) => w.id === id);
      if (!source) {
        return createDefaultWorkspace(newName);
      }
      const dup = duplicateWorkspace(source, newName);
      updateStore((prev) => ({
        activeWorkspaceId: dup.id,
        workspaces: [...prev.workspaces, dup],
      }));
      return dup;
    },
    [store.workspaces, updateStore]
  );

  // Layout
  const setLayoutHandler = useCallback(
    (layout: LayoutType) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId
            ? updateWorkspacePanels(w, layout)
            : w
        ),
      }));
    },
    [updateStore]
  );

  // Panel operations
  const updatePanelHandler = useCallback(
    (panelId: string, updates: Partial<Panel>) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId
            ? updatePanelHelper(w, panelId, updates)
            : w
        ),
      }));
    },
    [updateStore]
  );

  const getPanelHandler = useCallback(
    (panelId: string): Panel | undefined => {
      return workspace.panels.find((p) => p.id === panelId);
    },
    [workspace.panels]
  );

  // Link group operations
  const setLinkedTimeframe = useCallback(
    (linkGroup: string, timeframe: string) => {
      if (linkGroup === "none") return;
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId
            ? {
                ...w,
                panels: w.panels.map((p) =>
                  p.linkGroup === linkGroup ? { ...p, timeframe } : p
                ),
                updatedAt: new Date().toISOString(),
              }
            : w
        ),
      }));
    },
    [updateStore]
  );

  const setLinkedSymbol = useCallback(
    (linkGroup: string, symbol: string) => {
      if (linkGroup === "none") return;
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId
            ? {
                ...w,
                panels: w.panels.map((p) =>
                  p.linkGroup === linkGroup ? { ...p, symbol } : p
                ),
                updatedAt: new Date().toISOString(),
              }
            : w
        ),
      }));
    },
    [updateStore]
  );

  return {
    workspace,
    workspaces: store.workspaces,
    createWorkspace: createWorkspaceHandler,
    switchWorkspace: switchWorkspaceHandler,
    renameWorkspace: renameWorkspaceHandler,
    deleteWorkspace: deleteWorkspaceHandler,
    duplicateWorkspace: duplicateWorkspaceHandler,
    setLayout: setLayoutHandler,
    updatePanel: updatePanelHandler,
    getPanel: getPanelHandler,
    setLinkedTimeframe,
    setLinkedSymbol,
  };
}
