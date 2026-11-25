// Launch-token handling (D12, SB08): the CLI opens http://127.0.0.1:<port>/#token=<token>.
// The fragment never reaches the server. On load we move the token to sessionStorage, strip it
// from the address bar and send it only as `Authorization: Bearer`. Never in a query string,
// never in localStorage.

const KEY = 'truelift-launch-token';
const TOKEN_FRAGMENT = /^#?(?:.*&)?token=([A-Za-z0-9_-]{16,256})(?:&.*)?$/;

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

let memoryToken: string | null = null;

/** Read `#token=…` once, keep it for this tab and remove it from the URL. */
export function captureLaunchToken(loc: Location = window.location, hist: History = window.history): void {
  const match = TOKEN_FRAGMENT.exec(loc.hash);
  if (!match?.[1]) return;
  memoryToken = match[1];
  storage()?.setItem(KEY, match[1]);
  hist.replaceState(hist.state, '', loc.pathname + loc.search);
}

/** Keep a token for this tab without a fragment (tests and non-browser callers). */
export function rememberLaunchToken(token: string): void {
  memoryToken = token;
  storage()?.setItem(KEY, token);
}

export function getLaunchToken(): string | null {
  return storage()?.getItem(KEY) ?? memoryToken;
}

export function clearLaunchToken(): void {
  memoryToken = null;
  storage()?.removeItem(KEY);
}
