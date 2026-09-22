import { useSyncExternalStore } from "react";
import { en } from "@/lib/en";
import { es } from "@/lib/es";

export type Lang = "en" | "es";

const STORAGE_KEY = "siftpipe-lang";
const dictionaries = { en, es };

// The login page (Security, sequenced right after this) sits in front of the
// app shell and can't reach TopBar.tsx's toggle — checking navigator.language
// before localStorage has anything is the only way a Spanish-speaking
// visitor's very first screen shows in Spanish at all. Only falls through to
// it when localStorage genuinely has nothing yet, so an explicit past choice
// always wins on repeat visits.
function detectInitialLang(): Lang {
  if (typeof window === "undefined") return "en";
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored === "en" || stored === "es") return stored;
  } catch {
    // localStorage unavailable (private mode, disabled) — fall through to browser detection
  }
  return window.navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
}

let currentLang: Lang = detectInitialLang();
const listeners = new Set<() => void>();

function setLang(lang: Lang) {
  if (lang === currentLang) return;
  currentLang = lang;
  try {
    window.localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // best-effort persistence only
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function getSnapshot() {
  return currentLang;
}

// SSR render has no window, so it always sees "en" here; useSyncExternalStore
// reconciles that against the real client value (from localStorage/
// navigator.language) right after hydration without a mismatch warning.
function getServerSnapshot(): Lang {
  return "en";
}

export function useLang() {
  const lang = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return { lang, setLang, t: dictionaries[lang] };
}
