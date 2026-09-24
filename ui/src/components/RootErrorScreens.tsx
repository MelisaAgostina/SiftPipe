import { Link, useRouter } from "@tanstack/react-router";
import { useLang } from "@/hooks/use-lang";

// The root route's fallback screens, split out of routes/__root.tsx so they can be
// unit-tested (a route file can't export components without upsetting fast refresh).

export function NotFoundScreen() {
  const { t } = useLang();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="font-title text-7xl text-foreground">404</h1>
        <h2 className="font-title mt-4 text-xl text-foreground">{t.rootErrors.notFoundTitle}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t.rootErrors.notFoundDescription}</p>
        <div className="mt-6">
          <Link
            to="/"
            className="font-button inline-flex items-center justify-center rounded-xl bg-primary px-5 py-2.5 text-base text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t.rootErrors.goHome}
          </Link>
        </div>
      </div>
    </div>
  );
}

export function ErrorScreen({ error, reset }: { error: Error; reset: () => void }) {
  console.error(error);
  const router = useRouter();
  const { t } = useLang();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="max-w-md text-center">
        <h1 className="font-title text-xl text-foreground">{t.rootErrors.errorTitle}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{t.rootErrors.errorDescription}</p>
        <div className="mt-6 flex flex-wrap justify-center gap-2">
          <button
            onClick={() => {
              router.invalidate();
              reset();
            }}
            className="font-button inline-flex items-center justify-center rounded-xl bg-primary px-5 py-2.5 text-base text-primary-foreground transition-colors hover:bg-primary/90"
          >
            {t.rootErrors.tryAgain}
          </button>
          <a
            href="/"
            className="font-button inline-flex items-center justify-center rounded-xl border border-input bg-background px-5 py-2.5 text-base text-foreground transition-colors hover:bg-accent"
          >
            {t.rootErrors.goHome}
          </a>
        </div>
      </div>
    </div>
  );
}
