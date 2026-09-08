import "@testing-library/jest-dom/vitest";

// jsdom doesn't implement ResizeObserver - LoginPage.tsx uses one to keep
// its form as wide as the rendered title, and any future component that
// measures its own layout will hit the same gap.
class ResizeObserverStub {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= ResizeObserverStub as unknown as typeof ResizeObserver;

// jsdom doesn't implement Element.scrollTo either - LogsView.tsx calls it
// to auto-scroll to the newest log line, and any future component that
// scrolls its own container will hit the same gap.
Element.prototype.scrollTo ??= function scrollTo() {};
