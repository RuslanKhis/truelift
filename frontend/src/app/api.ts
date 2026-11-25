// The generated client is the only way the app talks to the API (C12, A1). This module configures
// it once: same-origin base URL, the launch token as a bearer header (SB08), and errors converted
// to ApiError so TanStack Query sees one shape. A 401 tells the shell to show the relaunch screen.

import { client } from '@/client/client.gen';

import { toApiError } from './errors';
import { getLaunchToken } from './token';

type Listener = () => void;
const unauthorisedListeners = new Set<Listener>();

export function onUnauthorised(listener: Listener): () => void {
  unauthorisedListeners.add(listener);
  return () => unauthorisedListeners.delete(listener);
}

let configured = false;

export function configureApi(): void {
  if (configured) return;
  configured = true;
  // Same origin as the page (the API serves the SPA). Absolute, because Request() needs one outside a page.
  client.setConfig({ baseUrl: typeof window === 'undefined' ? '' : window.location.origin, throwOnError: true });
  client.interceptors.request.use((request) => {
    const token = getLaunchToken();
    if (token) request.headers.set('Authorization', `Bearer ${token}`);
    return request;
  });
  client.interceptors.error.use((error, response) => {
    const apiError = toApiError(error, response);
    if (apiError.status === 401) unauthorisedListeners.forEach((fn) => fn());
    return apiError;
  });
}

/**
 * Headers for the one route outside the generated client, the agent SSE stream: the client's
 * configured headers plus the bearer token, so the two paths cannot drift apart.
 */
export function authHeaders(): Headers {
  const headers = new Headers(client.getConfig().headers as HeadersInit | undefined);
  const token = getLaunchToken();
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return headers;
}

/** The API origin the generated client uses, for the stream route it does not cover. */
export function apiBaseUrl(): string {
  return client.getConfig().baseUrl ?? '';
}
