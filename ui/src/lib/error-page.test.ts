import { afterEach, describe, expect, it } from "vitest";
import { LANG_STORAGE_KEY } from "@/hooks/use-lang";
import { en } from "./en";
import { es } from "./es";
import { renderErrorPage } from "./error-page";

// Loads the page the way a browser would - markup first, then the inline script - into
// the jsdom document. (innerHTML never runs <script>, so the script is run by hand.)
function loadPage(language: string) {
  const html = renderErrorPage();
  const script = /<script>([\s\S]*)<\/script>/.exec(html)![1];
  document.body.innerHTML = /<body>([\s\S]*)<\/body>/.exec(html)![1].replace(script, "");
  Object.defineProperty(window.navigator, "language", { value: language, configurable: true });
  new Function(script)();
}

describe("renderErrorPage", () => {
  afterEach(() => {
    window.localStorage.clear();
    document.body.innerHTML = "";
    document.documentElement.lang = "en";
  });

  it("is English before any script runs (no-JS fallback)", () => {
    const html = renderErrorPage();

    expect(html).toContain(`<h1 data-i18n="errorTitle">${en.rootErrors.errorTitle}</h1>`);
    expect(html).toContain(en.rootErrors.goHome);
  });

  it("switches to Spanish for a Spanish browser", () => {
    loadPage("es-AR");

    expect(document.querySelector("h1")!.textContent).toBe(es.rootErrors.errorTitle);
    expect(document.querySelector("p")!.textContent).toBe(es.rootErrors.errorDescription);
    expect(document.querySelector("button")!.textContent).toBe(es.rootErrors.tryAgain);
    expect(document.querySelector("a")!.textContent).toBe(es.rootErrors.goHome);
    expect(document.documentElement.lang).toBe("es");
  });

  it("stays English for an English browser", () => {
    loadPage("en-US");

    expect(document.querySelector("h1")!.textContent).toBe(en.rootErrors.errorTitle);
    expect(document.documentElement.lang).toBe("en");
  });

  it("lets the visitor's saved app language win over the browser language", () => {
    window.localStorage.setItem(LANG_STORAGE_KEY, "en");
    loadPage("es-ES");

    expect(document.querySelector("h1")!.textContent).toBe(en.rootErrors.errorTitle);
  });
});
