// The landing page says what truelift does at a glance and sends people to the right place.

import { screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { installFakeApi, renderApp } from './test-utils';

describe('landing page', () => {
  it('leads with what truelift does and two clear next steps', async () => {
    installFakeApi();
    renderApp('/');
    const hero = await screen.findByRole('region', { name: /Find out if your discounts actually pay off/ });
    expect(within(hero).getByText(/measures the true return on your discounts/)).toBeInTheDocument();
    expect(await within(hero).findByRole('link', { name: 'Open the demo project' })).toHaveAttribute('href', '/projects/demo/data');
    expect(within(hero).getByRole('link', { name: 'Set up your AI provider' })).toHaveAttribute('href', '/setup');
    const privacy = within(hero).getByRole('list', { name: 'Privacy' });
    expect(within(privacy).getAllByRole('listitem').map((li) => li.textContent)).toEqual([
      'Data stays on this computer',
      'Your own AI key',
      'Nothing is sent without your consent',
    ]);
  });

  it('labels the example result as illustrative', async () => {
    installFakeApi();
    renderApp('/');
    expect(await screen.findByText('Example · illustrative numbers')).toBeInTheDocument();
    expect(screen.getByRole('img', { name: /95% range from 1.4 to 2.8/ })).toBeInTheDocument();
  });

  it('explains how it works in four steps and what you get', async () => {
    installFakeApi();
    renderApp('/');
    const how = await screen.findByRole('region', { name: 'From a spreadsheet to a measured answer' });
    expect(within(how).getAllByRole('heading', { level: 3 }).map((h) => h.textContent)).toEqual([
      'Step 1: Connect your AI',
      'Step 2: Upload weekly sales',
      'Step 3: Answer a short interview',
      'Step 4: Get a measured return',
    ]);
    const get = screen.getByRole('region', { name: /An answer you can defend/ });
    expect(within(get).getAllByRole('heading', { level: 3 })).toHaveLength(3);
  });

  it('sets How it works on its own band and ends with one call to action on the dark band', async () => {
    installFakeApi();
    renderApp('/');
    const how = await screen.findByRole('region', { name: 'From a spreadsheet to a measured answer' });
    expect(how).toHaveClass('bg-section');
    const cta = screen.getByRole('region', { name: 'Start with one spreadsheet of weekly sales' });
    const start = await within(cta).findByRole('link', { name: 'Open the demo project' });
    expect(start).toHaveAttribute('href', '/projects/demo/data');
    expect(start).toHaveClass('bg-gold', 'text-brand');
    expect(within(cta).getByRole('link', { name: 'Set up your AI provider' })).toHaveAttribute('href', '/setup');
    // The band closes the page, after the projects, with only the footer below it.
    const projects = screen.getByRole('region', { name: 'Your projects' });
    expect(projects.compareDocumentPosition(cta) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(screen.getByRole('contentinfo')).toHaveTextContent('© 2026 the truelift authors');
  });

  it('falls back to setup when there is no project yet', async () => {
    installFakeApi({ 'GET /api/projects': () => ({ status: 200, body: [] }) });
    renderApp('/');
    const hero = await screen.findByRole('region', { name: /actually pay off/ });
    expect(await within(hero).findByRole('link', { name: /Get started/ })).toHaveAttribute('href', '/setup');
  });
});
