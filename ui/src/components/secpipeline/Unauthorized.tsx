import { useNavigate } from "@tanstack/react-router";
import catWalking from "@/assets/cat-walking.png";
import { useLang } from "@/hooks/use-lang";
import { clearSessionExpired } from "@/lib/session-expired-store";

// Shown in place of the whole /app shell once a protected query 401s -
// the session died mid-use (cookie expiry, backend restart, logged out
// from another tab). Not shown to a never-logged-in visitor hitting /app
// cold - that case is handled by app.tsx's beforeLoad redirecting straight
// to /login before this ever mounts.
export function Unauthorized() {
  const { t } = useLang();
  const navigate = useNavigate();

  const handleLogInAgain = () => {
    clearSessionExpired();
    navigate({ to: "/login" });
  };

  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-background px-6 text-center">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />
      {/* Cat watermark, deliberately faint and blurred rather than crisp -
          the source mockup centered a sharp, higher-opacity cat right behind
          the "403" glyphs and the two competed for legibility at this size.
          Turning it into soft ambient texture keeps the motif without the
          collision. */}
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 h-[420px] w-[500px] -translate-x-1/2 -translate-y-1/2 bg-primary opacity-[0.07] blur-sm"
        style={{
          WebkitMaskImage: `url(${catWalking})`,
          WebkitMaskPosition: "center",
          WebkitMaskSize: "contain",
          WebkitMaskRepeat: "no-repeat",
          maskImage: `url(${catWalking})`,
          maskPosition: "center",
          maskSize: "contain",
          maskRepeat: "no-repeat",
        }}
      />

      <div className="relative z-10 flex flex-col items-center gap-5">
        <span className="font-button text-[11px] tracking-[0.22em] text-primary">
          {t.unauthorized.errorLabel}
        </span>
        <h1 className="font-title text-[7rem] leading-none tracking-wide text-foreground sm:text-[9rem]">
          {t.unauthorized.title}
        </h1>
        <p className="max-w-md text-lg font-light leading-relaxed text-muted-foreground">
          {t.unauthorized.description}
        </p>
        <button
          onClick={handleLogInAgain}
          className="mt-2 border-b border-primary/35 pb-1 text-[13px] font-medium uppercase tracking-[0.2em] text-primary transition-colors hover:border-primary"
        >
          &larr; {t.unauthorized.cta}
        </button>
      </div>
    </main>
  );
}
