import { toast } from "sonner";
import { logout } from "@/lib/api";
import { useLang } from "@/hooks/use-lang";

/** Calls the backend's logout endpoint and surfaces a toast either way.
 * onLoggedOut (the caller's job - e.g. navigating to "/") only fires once
 * the session is actually confirmed cleared server-side: navigating away
 * on a failed request would leave the cookie valid while telling the user
 * they're logged out. Router-agnostic on purpose, same reasoning as
 * LoginPage's onAuthenticated prop - keeps this unit-testable without a
 * router context. */
export function useLogoutHandler(onLoggedOut: () => void) {
  const { t } = useLang();

  return async function handleLogout() {
    try {
      await logout();
      toast.success(t.topBar.loggedOutTitle, { description: t.topBar.loggedOutDescription });
      onLoggedOut();
    } catch {
      toast.error(t.topBar.logoutErrorTitle);
    }
  };
}
