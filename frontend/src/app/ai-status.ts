// AI availability for the banners (C15, A6). Fed by `ai_status` stream events (the agent stream,
// G16's chat) and by the project usage endpoint. The deterministic screens never read it to
// disable themselves: mapping, upload and confirm stay usable whatever it says.

import { useSyncExternalStore } from 'react';

import type { AiState } from '@/client';

import type { ValidatedAgentEvent } from './stream';

export type AiStatus = { state: AiState; message: string | null };

const AVAILABLE: AiStatus = { state: 'available', message: null };
let current: AiStatus = AVAILABLE;
// Who set the current state. A stream event is fresher than a usage snapshot, so a later usage
// response (or a refetch) never clears a banner the stream raised; only the stream can.
let source: 'none' | 'stream' | 'usage' = 'none';
const listeners = new Set<() => void>();

function publish(next: AiStatus, from: typeof source): void {
  source = next.state === 'available' ? 'none' : from;
  if (next.state === current.state && next.message === current.message) return;
  current = next;
  listeners.forEach((fn) => fn());
}

export const aiStatusStore = {
  get: (): AiStatus => current,
  subscribe(fn: () => void): () => void {
    listeners.add(fn);
    return () => listeners.delete(fn);
  },
  /** Apply one validated stream event; only `ai_status` changes the state. */
  applyEvent(event: ValidatedAgentEvent): void {
    if (event.type === 'ai_status') publish({ state: event.state, message: event.message }, 'stream');
  },
  /** The usage endpoint's view. It never overrides a state the stream set. */
  applyUsage(state: AiState): void {
    if (source === 'stream') return;
    if (state === 'budget_paused' || state === 'unavailable') publish({ state, message: null }, 'usage');
    else if (source === 'usage') publish(AVAILABLE, 'usage');
  },
  reset(): void {
    publish(AVAILABLE, 'none');
  },
};

export function useAiStatus(): AiStatus {
  return useSyncExternalStore(aiStatusStore.subscribe, aiStatusStore.get, aiStatusStore.get);
}
