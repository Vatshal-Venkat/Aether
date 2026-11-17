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
