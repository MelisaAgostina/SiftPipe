import { describe, expect, it } from "vitest";
import {
  clearSessionExpired,
  getSnapshot,
  markSessionExpired,
  subscribe,
} from "./session-expired-store";

describe("session-expired-store", () => {
  it("starts false", () => {
    expect(getSnapshot()).toBe(false);
  });

  it("becomes true after markSessionExpired and notifies subscribers", () => {
    let notified = false;
    const unsubscribe = subscribe(() => {
      notified = true;
    });

    markSessionExpired();

    expect(getSnapshot()).toBe(true);
    expect(notified).toBe(true);
    unsubscribe();
    clearSessionExpired();
  });

  it("does not notify subscribers on a redundant markSessionExpired call", () => {
    markSessionExpired();
    let notifyCount = 0;
    const unsubscribe = subscribe(() => {
      notifyCount++;
    });

    markSessionExpired();

    expect(notifyCount).toBe(0);
    unsubscribe();
    clearSessionExpired();
  });

  it("goes back to false after clearSessionExpired and notifies subscribers", () => {
    markSessionExpired();
    let notified = false;
    const unsubscribe = subscribe(() => {
      notified = true;
    });

    clearSessionExpired();

    expect(getSnapshot()).toBe(false);
    expect(notified).toBe(true);
    unsubscribe();
  });
});
