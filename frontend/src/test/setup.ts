// Test helpers: extra DOM assertions (toBeInTheDocument...), cleanup between tests, and
// browser APIs that jsdom lacks (matchMedia, scrollIntoView).
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => cleanup());

if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false, media: query, onchange: null,
    addEventListener: vi.fn(), removeEventListener: vi.fn(), addListener: vi.fn(), removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView || vi.fn();

// Node 22+ has its own built-in `localStorage` (empty unless started with --localstorage-file), and it
// hides jsdom's. If that happened, give the tests a simple in-memory one with the same methods.
if (typeof globalThis.localStorage === "undefined" || globalThis.localStorage === null) {
  const data = new Map<string, string>();
  const memoryStorage: Storage = {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k) => (data.has(k) ? data.get(k)! : null),
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  };
  Object.defineProperty(globalThis, "localStorage", { value: memoryStorage, configurable: true });
}
