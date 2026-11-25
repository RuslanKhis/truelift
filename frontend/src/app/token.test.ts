import { afterEach, describe, expect, it } from 'vitest';

import { captureLaunchToken, clearLaunchToken, getLaunchToken } from './token';

// Made at run time, not written as a literal: a random-looking string in the source trips gitleaks.
// Mixed case, digits, '-' and '_' cover the URL-safe alphabet the real launch token uses.
const TOKEN = `Ab_${globalThis.crypto.randomUUID()}`;

afterEach(() => clearLaunchToken());

describe('launch token (D12, SB08)', () => {
  it('moves #token from the fragment to sessionStorage and strips it from the URL', () => {
    window.history.replaceState(null, '', `/projects/demo/data?tab=1#token=${TOKEN}`);
    captureLaunchToken();
    expect(getLaunchToken()).toBe(TOKEN);
    expect(window.sessionStorage.getItem('truelift-launch-token')).toBe(TOKEN);
    expect(window.location.hash).toBe('');
    expect(window.location.pathname + window.location.search).toBe('/projects/demo/data?tab=1');
  });

  it('never writes the token to localStorage', () => {
    window.history.replaceState(null, '', `/#token=${TOKEN}`);
    captureLaunchToken();
    expect(JSON.stringify({ ...window.localStorage })).not.toContain(TOKEN);
  });

  it('ignores a fragment without a token and keeps an earlier one', () => {
    window.history.replaceState(null, '', `/#token=${TOKEN}`);
    captureLaunchToken();
    window.history.replaceState(null, '', '/#section');
    captureLaunchToken();
    expect(getLaunchToken()).toBe(TOKEN);
    expect(window.location.hash).toBe('#section');
  });
});
