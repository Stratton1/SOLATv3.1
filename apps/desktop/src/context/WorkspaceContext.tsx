/**
 * React context for shared workspace state.
 *
 * Ensures all components (WorkspaceShell, WorkspaceGrid, ChartPanel)
 * share a single workspace state instance instead of each creating
 * independent useState copies via useWorkspace().
 */

import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Workspace,
  WorkspaceStore,
  Panel,
  LayoutType,
  LinkGroup,
  loadWorkspaceStore,
  saveWorkspaceStore,
  createDefaultWorkspace,
  updateWorkspacePanels,
  updatePanel as updatePanelHelper,
  duplicateWorkspace as duplicateWorkspaceHelper,
} from "../lib/workspace";

// =============================================================================
// Types
// =============================================================================

interface WorkspaceContextValue {
  workspace: Workspace;
  workspaces: Workspace[];
  createWorkspace: (name: string) => Workspace;
  switchWorkspace: (id: string) => void;
  renameWorkspace: (id: string, name: string) => void;
  deleteWorkspace: (id: string) => void;
  duplicateWorkspace: (id: string, newName: string) => Workspace;
  setLayout: (layout: LayoutType) => void;
  updatePanel: (panelId: string, updates: Partial<Panel>) => void;
  getPanel: (panelId: string) => Panel | undefined;
  setLinkedTimeframe: (linkGroup: string, timeframe: string) => void;
  setLinkedSymbol: (linkGroup: string, symbol: string) => void;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

// =============================================================================
// Provider
// =============================================================================

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [store, setStore] = useState<WorkspaceStore>(() => loadWorkspaceStore());
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout>>();

  const saveStore = useCallback((newStore: WorkspaceStore) => {
    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current);
    }
    saveTimeoutRef.current = setTimeout(() => {
      saveWorkspaceStore(newStore);
    }, 300);
  }, []);

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

  useEffect(() => {
    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current);
      }
    };
  }, []);

  const workspace = useMemo(() => {
    return (
      store.workspaces.find((w) => w.id === store.activeWorkspaceId) ??
      store.workspaces[0] ??
      createDefaultWorkspace()
    );
  }, [store]);

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
      updateStore((prev) => ({ ...prev, activeWorkspaceId: id }));
    },
    [updateStore]
  );

  const renameWorkspaceHandler = useCallback(
    (id: string, name: string) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === id ? { ...w, name, updatedAt: new Date().toISOString() } : w
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
          const defaultWs = createDefaultWorkspace();
          return { activeWorkspaceId: defaultWs.id, workspaces: [defaultWs] };
        }
        return {
          activeWorkspaceId:
            prev.activeWorkspaceId === id ? remaining[0].id : prev.activeWorkspaceId,
          workspaces: remaining,
        };
      });
    },
    [updateStore]
  );

  const duplicateWorkspaceHandler = useCallback(
    (id: string, newName: string): Workspace => {
      const source = store.workspaces.find((w) => w.id === id);
      if (!source) return createDefaultWorkspace(newName);
      const dup = duplicateWorkspaceHelper(source, newName);
      updateStore((prev) => ({
        activeWorkspaceId: dup.id,
        workspaces: [...prev.workspaces, dup],
      }));
      return dup;
    },
    [store.workspaces, updateStore]
  );

  const setLayoutHandler = useCallback(
    (layout: LayoutType) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId ? updateWorkspacePanels(w, layout) : w
        ),
      }));
    },
    [updateStore]
  );

  const updatePanelHandler = useCallback(
    (panelId: string, updates: Partial<Panel>) => {
      updateStore((prev) => ({
        ...prev,
        workspaces: prev.workspaces.map((w) =>
          w.id === prev.activeWorkspaceId ? updatePanelHelper(w, panelId, updates) : w
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
                  p.linkGroup === (linkGroup as LinkGroup) ? { ...p, timeframe } : p
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
                  p.linkGroup === (linkGroup as LinkGroup) ? { ...p, symbol } : p
                ),
                updatedAt: new Date().toISOString(),
              }
            : w
        ),
      }));
    },
    [updateStore]
  );

  const value = useMemo<WorkspaceContextValue>(
    () => ({
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
    }),
    [
      workspace,
      store.workspaces,
      createWorkspaceHandler,
      switchWorkspaceHandler,
      renameWorkspaceHandler,
      deleteWorkspaceHandler,
      duplicateWorkspaceHandler,
      setLayoutHandler,
      updatePanelHandler,
      getPanelHandler,
      setLinkedTimeframe,
      setLinkedSymbol,
    ]
  );

  return (
    <WorkspaceContext.Provider value={value}>
      {children}
    </WorkspaceContext.Provider>
  );
}

// =============================================================================
// Consumer hook
// =============================================================================

export function useWorkspaceContext(): WorkspaceContextValue {
  const ctx = useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspaceContext must be used within a WorkspaceProvider");
  }
  return ctx;
}
