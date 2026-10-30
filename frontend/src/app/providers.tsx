import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiClient } from "../lib/api/client";
import type { Session } from "../lib/api/types";

type Auth = { api: ApiClient; session: Session; disconnect: () => void };
const Context = createContext<Auth | null>(null);
export function SessionProvider({
  api,
  session,
  disconnect,
  children,
}: Auth & { children: ReactNode }) {
  const [queries] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            staleTime: 15000,
            refetchOnWindowFocus: false,
          },
          mutations: { retry: false },
        },
      }),
  );
  useEffect(
    () => () => {
      api.dispose();
      void queries.cancelQueries();
      queries.clear();
    },
    [api, queries],
  );
  return (
    <Context.Provider value={{ api, session, disconnect }}>
      <QueryClientProvider client={queries}>{children}</QueryClientProvider>
    </Context.Provider>
  );
}
export function useSession() {
  const value = useContext(Context);
  if (!value) throw new Error("SessionProvider required");
  return value;
}
export function useScope() {
  const { session } = useSession();
  return [session.school_id, session.user_id];
}
