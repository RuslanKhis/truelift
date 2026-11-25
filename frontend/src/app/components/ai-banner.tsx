import { CirclePause, CloudOff } from 'lucide-react';

import { useAiStatus } from '@/app/ai-status';

import { Notice, NoticeBody, NoticeTitle } from './ui/notice';

// C15 banners. The wording of the titles is fixed by the design; the event's own message is
// shown beneath as text (SB10). Deterministic screens stay usable: this only informs.
export function AiBanner() {
  const { state, message } = useAiStatus();
  if (state === 'unavailable') {
    return (
      <Notice variant="warning" aria-live="polite">
        <CloudOff aria-hidden />
        <NoticeBody>
          <NoticeTitle>AI unavailable</NoticeTitle>
          <p className="text-muted-foreground">
            {message ?? 'The AI provider did not answer. Data, mapping, DAG cards, runs and results still work.'}
          </p>
        </NoticeBody>
      </Notice>
    );
  }
  if (state === 'budget_paused') {
    return (
      <Notice variant="warning" aria-live="polite">
        <CirclePause aria-hidden />
        <NoticeBody>
          <NoticeTitle>AI paused: budget reached</NoticeTitle>
          <p className="text-muted-foreground">{message ?? 'Raise it or continue without AI.'}</p>
        </NoticeBody>
      </Notice>
    );
  }
  return null;
}
