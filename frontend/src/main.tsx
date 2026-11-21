import { MutationCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./app/App";
import { AuthProvider } from "./lib/auth";
import "./index.css";

const queryClient: QueryClient = new QueryClient({
  // After ANY successful action (assign, submit, review, comment ...) re-read the notification count, because the action
  // may have created or cleared notices; this replaces the old WebSocket push.
  mutationCache: new MutationCache({ onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["notifications"] }); } }),
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: true, staleTime: 3_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
