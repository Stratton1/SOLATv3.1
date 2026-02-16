import { createContext, useContext, type ReactNode } from "react";
import { useEngineHealth } from "../hooks/useEngineHealth";
import { useWebSocket } from "../hooks/useWebSocket";

type EngineConnectionValue = ReturnType<typeof useProvideEngineConnection>;

const EngineConnectionContext = createContext<EngineConnectionValue | null>(null);

function useProvideEngineConnection() {
  const engineHealth = useEngineHealth();
  const webSocket = useWebSocket();

  return {
    ...engineHealth,
    ...webSocket,
  };
}

export function EngineConnectionProvider({
  children,
}: {
  children: ReactNode;
}) {
  const value = useProvideEngineConnection();
  return (
    <EngineConnectionContext.Provider value={value}>
      {children}
    </EngineConnectionContext.Provider>
  );
}

export function useEngineConnection() {
  const ctx = useContext(EngineConnectionContext);
  if (!ctx) {
    throw new Error("useEngineConnection must be used within EngineConnectionProvider");
  }
  return ctx;
}
