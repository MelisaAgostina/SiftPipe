import { createFileRoute, redirect } from "@tanstack/react-router";
import { SecPipelineApp } from "@/components/secpipeline/SecPipelineApp";
import { checkSession } from "@/lib/api";

export const Route = createFileRoute("/app")({
  // The session cookie has no Domain attribute (api.py's SessionMiddleware),
  // so per cookie spec it's scoped to api.siftpipe.com exactly - a browser
  // never attaches it to a request for siftpipe.com (this frontend's own
  // origin) in the first place. That means beforeLoad's checkSession() call
  // can never see it when run server-side (no incoming cookie to forward,
  // regardless of the fetch-side fix in lib/api.ts), so ssr:false is what
  // actually fixes "direct navigation/refresh of /app bounces to /login
  // despite a valid session" - it skips beforeLoad server-side entirely,
  // deferring the check to the client, where the browser correctly holds
  // and attaches the real api.siftpipe.com cookie.
  ssr: false,
  beforeLoad: async () => {
    const authenticated = await checkSession();
    if (!authenticated) {
      throw redirect({ to: "/login" });
    }
  },
  component: () => <SecPipelineApp />,
});
