import { CircleAlert } from 'lucide-react';

import type { ApiError } from '@/app/errors';

import { Notice, NoticeBody, NoticeTitle } from './ui/notice';

/** An API error in words, with its request ID for reports. Server text renders as text (SB10). */
export function ErrorNotice({ error, title }: { error: ApiError | Error; title?: string }) {
  const requestId = 'requestId' in error ? error.requestId : null;
  return (
    <Notice variant="destructive" role="alert">
      <CircleAlert aria-hidden />
      <NoticeBody>
        {title ? <NoticeTitle>{title}</NoticeTitle> : null}
        <p>{error.message}</p>
        {requestId ? <p className="type-caption text-muted-foreground">Request ID: {requestId}</p> : null}
      </NoticeBody>
    </Notice>
  );
}
