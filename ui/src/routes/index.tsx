import { createFileRoute } from "@tanstack/react-router";
import { Link } from "@tanstack/react-router";
import logo from "@/assets/siftpipe-logo.png";
import pic from "@/assets/Sift pipe-Photoroom.png";
import { useLang } from "@/hooks/use-lang";
import { useSessionAuthenticated } from "@/hooks/use-session-authenticated";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "SiftPipe — Hybrid security pipeline" },
      {
        name: "description",
        content:
          "SiftPipe runs a hybrid AI + human security pipeline on live apps: static analysis, dynamic discovery, contextual payloads, and correlated results.",
      },
      { property: "og:title", content: "SiftPipe — Hybrid security pipeline" },
      {
        property: "og:description",
        content:
          "Hybrid AI + human security pipeline: from static analysis to correlated, confirmed findings.",
      },
      { property: "og:image", content: pic },
    ],
    links: [{ rel: "icon", href: pic, type: "image/png" }],
  }),
  component: Index,
});

function Index() {
  const { t } = useLang();
  const authenticated = useSessionAuthenticated();
  return (
    <main className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-linear-to-br from-background via-background to-card px-6 text-foreground">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage:
            "linear-gradient(to right, currentColor 1px, transparent 1px), linear-gradient(to bottom, currentColor 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute left-1/2 top-1/2 h-130 w-130 -translate-x-1/2 -translate-y-1/2 rounded-full bg-primary/10 blur-3xl"
      />

      <section className="relative z-10 mx-auto flex max-w-2xl flex-col items-center text-center">
        <img
          src={logo}
          alt="SiftPipe logo"
          className="mb-0 mt-16 block w-lg h-auto object-contain select-none invert"
          draggable={false}
        />

        <h1 className="font-title mt-2 text-5xl sm:text-5xl text-foreground uppercase tracking-[0.15em] sm:tracking-[0.2em]">
          {t.landing.heading}
        </h1>

        <p className=" mt-8 text-muted-foreground max-w-xl text-balance text-base leading-relaxed sm:text-lg">
          {t.landing.description}
        </p>

        <div className="mt-10 flex flex-wrap items-center justify-center gap-3">
          <Link
            to={authenticated ? "/app" : "/login"}
            className="font-button group inline-flex items-center gap-3 rounded-full bg-primary px-10 py-6 text-lg text-primary-foreground transition-colors hover:bg-primary/90 [-webkit-text-stroke:0.6px_currentColor]"
          >
            {authenticated ? t.landing.openPipeline : t.landing.logIn}
            <span aria-hidden className="transition-transform group-hover:translate-x-0.5"></span>
          </Link>
        </div>
      </section>

      <footer className=" italic relative z-10 mt-16 mb-16 text-xs text-muted-foreground">
        {t.landing.footerTagline}
      </footer>
    </main>
  );
}
