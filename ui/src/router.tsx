import { QueryCache, QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";
import { ApiError } from "@/lib/api";
import { markSessionExpired } from "@/lib/session-expired-store";
import { routeTree } from "./routeTree.gen";

export const getRouter = () => {
  // A 401 from any protected query means the session died mid-use (cookie
  // expiry, backend restart, logged out from another tab) - every panel
  // polling status/results would otherwise just fail silently. Caught here,
  // once, at the QueryCache level, rather than in each of queries.ts's
  // hooks individually.
  const queryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.status === 401) {
          markSessionExpired();
        }
      },
    }),
  });

  const router = createRouter({
    routeTree,
    context: { queryClient },
    scrollRestoration: true,
    defaultPreloadStaleTime: 0,
  });

  return router;
};
