// A1: the theme carries the house tokens from docs/design/DESIGN.md exactly, in both scopes.
// (frontend/scripts/check_theme.py separately proves no shadcn default token or font is left.)

import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

// Normalise line endings: checkouts with core.autocrlf have CRLF files.
const read = (path: string) => readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
const design = read(resolve(import.meta.dirname, '../../../docs/design/DESIGN.md'));
const theme = read(resolve(import.meta.dirname, 'theme.css'));

function designColours(): Map<string, string> {
  const block = design.split('\ncolors:\n')[1]?.split(/\n[a-z]+:\n/)[0] ?? '';
  const raw = new Map<string, string>();
  for (const m of block.matchAll(/^ {2}([\w-]+): "([^"]+)"$/gm)) raw.set(m[1]!, m[2]!);
  const resolveRef = (v: string): string => {
    const ref = /^\{colors\.([\w-]+)\}$/.exec(v);
    return ref ? resolveRef(raw.get(ref[1]!) ?? '') : v;
  };
  return new Map([...raw].map(([k, v]) => [k, resolveRef(v)]));
}

function scopeVars(selector: string): Map<string, string> {
  const body = new RegExp(`^${selector.replace('.', '\\.')} \\{([^}]*)\\}`, 'm').exec(theme)?.[1] ?? '';
  return new Map([...body.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1]!, m[2]!.trim()]));
}

describe('house theme (A1)', () => {
  const colours = designColours();
  const light = scopeVars(':root');
  const dark = scopeVars('.dark');

  it('reads the DESIGN.md colour tokens', () => {
    expect(colours.size).toBeGreaterThan(80);
  });

  it('maps every token one to one, light into :root and dark- into .dark', () => {
    for (const [name, value] of colours) {
      if (name.startsWith('dark-')) expect(dark.get(name.slice(5)), name).toBe(value);
      else expect(light.get(name), name).toBe(value);
    }
  });

  it('pins the radius steps and the self-hosted fonts', () => {
    expect(light.get('radius')).toBe('0.375rem');
    expect(theme).toContain('--radius-lg: 8px;');
    expect(theme).toContain('--radius-xl: 12px;');
    expect(theme).toContain('--radius-4xl: 16px;');
    expect(theme).toContain('--font-sans: "Manrope Variable"');
    expect(theme).toContain('--font-display: "Schibsted Grotesk Variable"');
    expect(theme).toContain('@import "@fontsource-variable/manrope";');
    expect(theme).toContain('@import "@fontsource-variable/schibsted-grotesk";');
    expect(theme).not.toMatch(/fonts\.googleapis|Geist|Source Serif|Inter Variable|--font-serif/);
  });

  it('uses the display font for headings and figures and Manrope for the rest, as DESIGN.md says', () => {
    const families = new Map(
      [...design.matchAll(/^ {2}([\w-]+):\n {4}fontFamily: (.+)$/gm)].map((m) => [m[1]!, m[2]!] as const),
    );
    expect(new Set(families.values())).toEqual(new Set(['Schibsted Grotesk', 'Manrope', 'JetBrains Mono']));
    const display = ['display', 'headline-lg', 'headline-md', 'metric'];
    for (const token of display) expect(families.get(token), token).toBe('Schibsted Grotesk');
    expect(families.get('body-md')).toBe('Manrope');
    for (const token of display) {
      expect(theme, token).toContain(`@utility type-${token} {\n  font-family: var(--font-display);`);
    }
  });

  it('shows a pointer on every enabled control and has the fluid display scale', () => {
    for (const selector of ['button:not(:disabled)', 'select:not(:disabled)', "input[type='radio']:not(:disabled)", 'label[for]']) {
      expect(theme, selector).toContain(selector);
    }
    expect(theme).toMatch(/summary \{\n\s+cursor: pointer;/);
    expect(theme).toContain('@utility type-hero {\n  font-family: var(--font-display);\n  font-size: clamp(2.5rem, 5vw, 4rem);');
    expect(theme).toContain('@utility type-lead {');
    expect(theme).toMatch(/@utility type-body-md \{[^}]*font-weight: 450;/);
  });

  it('has the green, chip, card edge, selection and brand tokens in both modes', () => {
    for (const token of ['primary', 'primary-foreground', 'primary-ink', 'chip', 'chip-foreground', 'chip-fill', 'card-edge', 'selected', 'choice', 'gold', 'brand']) {
      expect(light.has(token), token).toBe(true);
      expect(dark.has(token), token).toBe(true);
      expect(theme, token).toContain(`--color-${token}: var(--${token});`);
    }
    expect(light.get('ring')).toBe(light.get('primary-ink'));
  });

  it('keeps the hero grid strong to mid-headline, then fades it slowly to a full blend at the bottom', () => {
    expect(theme).toMatch(
      /mask-image: linear-gradient\(\s*to bottom,\s*#000 0,\s*#000 160px,\s*rgb\(0 0 0 \/ 0\.5\) 50%,\s*rgb\(0 0 0 \/ 0\.3\) 70%,\s*rgb\(0 0 0 \/ 0\.15\) 88%,\s*transparent 100%\s*\);/,
    );
    expect(theme).toContain('--grid-line: color-mix(in oklab, var(--border) 50%, transparent);');
  });

  it('gives cards a resting shadow in light mode only', () => {
    expect(light.get('card-shadow')).toBe('0 1px 2px rgb(15 23 42 / 0.04), 0 8px 24px -12px rgb(15 23 42 / 0.12)');
    expect(dark.get('card-shadow')).toBe('0 0 #0000');
    expect(theme).toContain('@utility shadow-card {\n  box-shadow: var(--card-shadow);');
    expect(theme).toContain('@utility shadow-card-hover {\n  box-shadow: var(--card-shadow-hover);');
  });

  it('makes the label on a primary fill heavier in dark mode', () => {
    expect(light.get('primary-label-weight')).toBe('600');
    expect(dark.get('primary-label-weight')).toBe('700');
    expect(theme).toMatch(/@utility type-label-primary \{[^}]*font-weight: var\(--primary-label-weight\);/);
  });
});
