import { useEffect, useState } from "react";
import { checkSession } from "@/lib/api";

/** Whether the current visitor has a valid session, per the backend -
 * starts `false` (pessimistic default) until that check resolves, so a
 * logged-out visitor never briefly sees authenticated-only UI. Client-only
 * by construction (the check runs inside an effect, never during SSR) -
 * a server-side check would hit the same cookie-less-fetch gap that broke
 * the post-login redirect (see LoginPage/app.tsx's beforeLoad). */
export function useSessionAuthenticated(): boolean {
  const [authenticated, setAuthenticated] = useState(false);

  useEffect(() => {
    let cancelled = false;
    checkSession().then((result) => {
      if (!cancelled) setAuthenticated(result);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return authenticated;
}
