import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Outlet, createRootRouteWithContext, HeadContent, Scripts } from "@tanstack/react-router";
import { useEffect } from "react";

import { ErrorScreen, NotFoundScreen } from "@/components/RootErrorScreens";
import { Toaster } from "@/components/ui/sonner";
import { useLang } from "@/hooks/use-lang";
import appCss from "../styles.css?url";

export const Route = createRootRouteWithContext<{ queryClient: QueryClient }>()({
  head: () => ({
    meta: [
      { charSet: "utf-8" },
      { name: "viewport", content: "width=device-width, initial-scale=1" },
      // The app translates itself (lib/en.ts / es.ts). Browser page-translation
      // rewrites the DOM text nodes React owns, and React then throws
      // removeChild/insertBefore errors that land on the "This page didn't load" screen.
      { name: "google", content: "notranslate" },
      { title: "SiftPipe" },
      { property: "og:image", content: "/assets/Sift pipe-Photoroom.png" },
      { name: "twitter:image", content: "/assets/Sift pipe-Photoroom.png" },
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
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
      { name: "twitter:title", content: "SiftPipe — Hybrid security pipeline" },
      {
        name: "twitter:description",
        content:
          "Hybrid AI + human security pipeline: from static analysis to correlated, confirmed findings.",
      },
    ],
    links: [
      {
        rel: "stylesheet",
        href: appCss,
      },
      {
        rel: "icon",
        href: "/assets/Sift pipe-Photoroom.png",
      },
      {
        rel: "apple-touch-icon",
        href: "/assets/Sift pipe-Photoroom.png",
      },
    ],
  }),
  shellComponent: RootShell,
  component: RootComponent,
  notFoundComponent: NotFoundScreen,
  errorComponent: ErrorScreen,
});

function RootShell({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" translate="no">
      <head>
        <HeadContent />
      </head>
      <body>
        {children}
        <Scripts />
      </body>
    </html>
  );
}

function RootComponent() {
  const { queryClient } = Route.useRouteContext();
  const { lang } = useLang();

  // The server always renders lang="en" (it can't read localStorage/navigator), so
  // the attribute is corrected here, after hydration, to match the language actually
  // shown. Done in an effect on purpose: changing it earlier would make the client's
  // <html> disagree with the server HTML mid-hydration. React never rewrites it, since
  // RootShell's lang prop never changes.
  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  return (
    <QueryClientProvider client={queryClient}>
      <Outlet />
      <Toaster />
    </QueryClientProvider>
  );
}
