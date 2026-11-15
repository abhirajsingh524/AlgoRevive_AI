import '@testing-library/jest-dom';

// Polyfill ResizeObserver for recharts / jsdom
class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = ResizeObserverMock;
}
if (typeof global !== 'undefined' && !global.ResizeObserver) {
  (global as any).ResizeObserver = ResizeObserverMock;
}

