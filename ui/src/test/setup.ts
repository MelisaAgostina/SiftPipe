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
