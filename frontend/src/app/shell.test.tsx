// A1: the shell renders, every call goes through the generated client with the bearer header,
// and a missing or rejected token shows how to reopen truelift.

import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { installFakeApi, json, renderApp, TOKEN } from './test-utils';
import { clearLaunchToken } from './token';

afterEach(() => clearLaunchToken());

describe('app shell (A1)', () => {
  it('renders the sidebar, the page heading and the environment badge', async () => {
    installFakeApi();
    renderApp('/');
    expect(await screen.findByRole('heading', { level: 1, name: 'Home' })).toBeInTheDocument();
    expect(screen.getByRole('navigation', { name: 'Main' })).toBeInTheDocument();
    expect(screen.getByText('On this computer')).toBeInTheDocument();
    const main = screen.getByRole('main');
    expect(await within(main).findByRole('link', { name: /Pet food, Germany/ })).toBeInTheDocument();
    expect(within(screen.getByRole('navigation', { name: 'Main' })).getByRole('link', { name: /Pet food, Germany/ })).toBeInTheDocument();
  });

  it('keeps the selected nav item at the same size and only makes it bold', async () => {
    installFakeApi();
    renderApp('/setup');
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    const selected = within(nav).getByRole('link', { name: 'AI provider' });
    const other = await within(nav).findByRole('link', { name: /Pet food, Germany/ });
    expect(selected).toHaveAttribute('aria-current', 'page');
    expect(selected).toHaveClass('type-body-md', 'font-semibold', 'before:bg-sidebar-primary');
    expect(selected).not.toHaveClass('type-label-md');
    expect(other).toHaveClass('type-body-md');
    expect(other).not.toHaveClass('font-semibold');
    expect(other).not.toHaveClass('before:bg-sidebar-primary');
  });

  it('pins the nav links on mobile while the brand row scrolls away', async () => {
    installFakeApi();
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(nav).toHaveClass('max-md:sticky', 'max-md:-top-13', 'max-md:z-20', 'md:sticky', 'md:top-0');
  });

  it('opens a new page at the top', async () => {
    const user = userEvent.setup();
    const scrollTo = vi.spyOn(window, 'scrollTo');
    installFakeApi();
    renderApp('/');
    const nav = await screen.findByRole('navigation', { name: 'Main' });
    scrollTo.mockClear();
    await user.click(within(nav).getByRole('link', { name: 'AI provider' }));
    expect(scrollTo).toHaveBeenCalledWith(0, 0);
    scrollTo.mockRestore();
  });

  it('has a Home link that is selected only on the landing page', async () => {
    installFakeApi();
    const view = renderApp('/');
    let nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Home' })).toHaveAttribute('aria-current', 'page');
    view.unmount();
    renderApp('/setup');
    nav = await screen.findByRole('navigation', { name: 'Main' });
    expect(within(nav).getByRole('link', { name: 'Home' })).not.toHaveAttribute('aria-current');
  });

  it('sends the launch token as a bearer header on every API call and never in a URL', async () => {
    const calls = installFakeApi();
    renderApp('/projects/demo/mapping');
    await screen.findByRole('button', { name: 'Confirm roles' });
    expect(calls.length).toBeGreaterThan(2);
    for (const call of calls) {
      expect(call.path.startsWith('/api/')).toBe(true);
      expect(call.headers.get('Authorization')).toBe(`Bearer ${TOKEN}`);
      expect(call.path).not.toContain(TOKEN);
    }
  });

  it('shows the relaunch screen without a token and calls nothing', async () => {
    const calls = installFakeApi();
    clearLaunchToken();
    renderApp('/', { token: null });
    expect(await screen.findByRole('heading', { name: 'Open truelift from its link' })).toBeInTheDocument();
    expect(calls).toHaveLength(0);
  });

  it('switches to the relaunch screen when the API answers 401', async () => {
    installFakeApi({
      'GET /api/projects': () =>
        json(401, { code: 'unauthorized', message: 'Open truelift from the link the truelift command printed.', request_id: 'r1' }),
    });
    renderApp('/');
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Open truelift from its link' })).toBeInTheDocument());
  });
});
