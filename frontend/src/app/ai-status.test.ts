// A stream event is fresher than a usage snapshot: a later usage response never clears it.

import { afterEach, describe, expect, it } from 'vitest';

import { aiStatusStore } from './ai-status';

const event = (state: 'unavailable' | 'budget_paused' | 'available') =>
  ({ type: 'ai_status', seq: 2, turn_id: 't', state, message: `stream says ${state}` }) as const;

afterEach(() => aiStatusStore.reset());

describe('AI status precedence (C15)', () => {
  it('a usage response saying available does not clear a banner the stream raised', () => {
    aiStatusStore.applyEvent(event('budget_paused'));
    aiStatusStore.applyUsage('available');
    expect(aiStatusStore.get()).toEqual({ state: 'budget_paused', message: 'stream says budget_paused' });
  });

  it('usage can raise and later clear its own banner', () => {
    aiStatusStore.applyUsage('budget_paused');
    expect(aiStatusStore.get().state).toBe('budget_paused');
    aiStatusStore.applyUsage('available');
    expect(aiStatusStore.get().state).toBe('available');
  });

  it('the stream can clear any banner', () => {
    aiStatusStore.applyUsage('budget_paused');
    aiStatusStore.applyEvent(event('available'));
    expect(aiStatusStore.get().state).toBe('available');
  });
});
