import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no scrolling; React Router's ScrollRestoration calls window.scrollTo on every navigation.
window.scrollTo = () => {};

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
  window.localStorage.clear();
});
