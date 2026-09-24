import { LANG_STORAGE_KEY } from "../hooks/use-lang";
import { en } from "./en";
import { es } from "./es";

// Both languages are embedded and a few lines of inline script pick one, because this
// page is plain HTML with no React/useLang(). It is sent when server rendering fails
// outright, so it can't rely on the app bundle having loaded either. Without JS (or if
// the script throws) it simply stays in English. The wording comes from the same
// rootErrors entries as the in-app error screen, so the two never drift apart.
// "<" is escaped so a future string containing "</script>" can't end the script early.
const STRINGS_JSON = JSON.stringify({ en: en.rootErrors, es: es.rootErrors }).replace(
  /</g,
  "\\u003c",
);

const LANG_SCRIPT = `(function () {
  try {
    var strings = ${STRINGS_JSON};
    var lang = null;
    try {
      var stored = window.localStorage.getItem(${JSON.stringify(LANG_STORAGE_KEY)});
      if (stored === "en" || stored === "es") lang = stored;
    } catch (e) {}
    if (!lang) lang = (navigator.language || "").toLowerCase().indexOf("es") === 0 ? "es" : "en";
    var t = strings[lang];
    document.documentElement.lang = lang;
    document.title = t.errorTitle;
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.textContent = t[el.getAttribute("data-i18n")];
    });
  } catch (e) {}
})();`;

export function renderErrorPage(): string {
  const t = en.rootErrors;
  return `<!doctype html>
<html lang="en" translate="no">
  <head>
    <meta charset="utf-8" />
    <meta name="google" content="notranslate" />
    <title>${t.errorTitle}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <style>
      body { font: 15px/1.5 system-ui, -apple-system, sans-serif; background: #fafafa; color: #111; display: grid; place-items: center; min-height: 100vh; margin: 0; padding: 1.5rem; }
      .card { max-width: 28rem; width: 100%; text-align: center; padding: 2rem; }
      h1 { font-size: 1.25rem; margin: 0 0 0.5rem; }
      p { color: #4b5563; margin: 0 0 1.5rem; }
      .actions { display: flex; gap: 0.5rem; justify-content: center; flex-wrap: wrap; }
      a, button { padding: 0.5rem 1rem; border-radius: 0.375rem; font: inherit; cursor: pointer; text-decoration: none; border: 1px solid transparent; }
      .primary { background: #111; color: #fff; }
      .secondary { background: #fff; color: #111; border-color: #d1d5db; }
    </style>
  </head>
  <body>
    <div class="card">
      <h1 data-i18n="errorTitle">${t.errorTitle}</h1>
      <p data-i18n="errorDescription">${t.errorDescription}</p>
      <div class="actions">
        <button class="primary" data-i18n="tryAgain" onclick="location.reload()">${t.tryAgain}</button>
        <a class="secondary" data-i18n="goHome" href="/">${t.goHome}</a>
      </div>
    </div>
    <script>${LANG_SCRIPT}</script>
  </body>
</html>`;
}
