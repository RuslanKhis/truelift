// Disclosure and consent (A2; C8, D17): before any AI call, show exactly what would be shared with
// the chosen provider, including an example payload built from the user's own file, then record
// consent for that disclosure version. The payload renders as text in a <pre> (SB10).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleCheck, Info, ShieldCheck } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router';

import { ErrorNotice } from '@/app/components/error-notice';
import { Button } from '@/app/components/ui/button';
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/app/components/ui/card';
import { NativeSelect } from '@/app/components/ui/native-select';
import { Notice, NoticeBody, NoticeTitle } from '@/app/components/ui/notice';
import { useProjectId, useSessionConsent } from '@/app/project-layout';
import { disclosureQuery, keys, projectQuery, setupQuery } from '@/app/queries';
import { setupPostConsent } from '@/client';
import type { ConsentRecord, Provider } from '@/client';

export const handle = { title: 'What is shared' };

const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' });

export function Component() {
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const setup = useQuery(setupQuery());
  const project = useQuery(projectQuery(projectId));
  const [chosen, setChosen] = useState<Provider | null>(null);
  const [localRecord, setRecord] = useState<ConsentRecord | null>(null);
  // Consent given earlier in this session still counts when the person comes back to this step.
  const sessionConsent = useSessionConsent(projectId);
  const record = localRecord ?? sessionConsent;
  const selectId = useId();
  const payloadId = useId();

  const provider = chosen ?? setup.data?.active_provider ?? setup.data?.providers[0]?.provider ?? null;
  const info = setup.data?.providers.find((p) => p.provider === provider);
  const disclosure = useQuery({ ...disclosureQuery(projectId, provider ?? 'gemini'), enabled: provider !== null });

  const consent = useMutation({
    mutationFn: async (vars: { provider: Provider; version: string }) =>
      (await setupPostConsent({
        path: { project_id: projectId },
        body: { provider: vars.provider, disclosure_version: vars.version },
        throwOnError: true,
      })).data,
    onSuccess: (r) => {
      setRecord(r);
      queryClient.setQueryData(keys.consent(projectId), r);
    },
    onError: (error) => {
      // The disclosure changed under us: reload it so the person reviews the new version.
      if (error.code === 'disclosure_changed' && provider) {
        void queryClient.invalidateQueries({ queryKey: keys.disclosure(projectId, provider) });
      }
    },
  });

  if (setup.error) return <ErrorNotice error={setup.error} title="The provider list could not be loaded." />;
  if (!setup.data || !provider) return <p className="text-muted-foreground">Loading…</p>;

  const accepted = record && record.provider === provider && record.disclosure_version === disclosure.data?.version;
  const noData = project.data && project.data.data_version === null;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader icon={ShieldCheck}>
          <CardTitle>What truelift will share with {info?.label ?? provider}</CardTitle>
          <CardDescription>
            Nothing is sent to the provider until you allow it here. Your raw file is never sent.
          </CardDescription>
        </CardHeader>
        <div className="flex max-w-md flex-col gap-2">
          <label htmlFor={selectId} className="type-label-md">
            Provider
          </label>
          <NativeSelect
            id={selectId}
            value={provider}
            onChange={(e) => {
              setChosen(e.target.value as Provider);
              setRecord(null);
              queryClient.setQueryData(keys.consent(projectId), null);
              consent.reset();
            }}
          >
            {setup.data.providers.map((p) => (
              <option key={p.provider} value={p.provider}>
                {p.label} ({p.model_id})
              </option>
            ))}
          </NativeSelect>
        </div>
        {noData ? (
          <Notice variant="info">
            <Info aria-hidden />
            <NoticeBody>
              <p>
                The example below is built from your own file.{' '}
                <Link to="../data" className="text-primary-ink underline underline-offset-4">
                  Upload your data
                </Link>{' '}
                first to see it.
              </p>
            </NoticeBody>
          </Notice>
        ) : null}
        {disclosure.error ? <ErrorNotice error={disclosure.error} title="The disclosure could not be loaded." /> : null}
        {disclosure.data ? (
          <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-8">
            <ul className="flex flex-col divide-y divide-border self-start">
              {disclosure.data.categories.map((c) => (
                <li key={c.id} className="flex flex-col gap-0.5 py-3 first:pt-0">
                  <span className="type-label-md">{c.title}</span>
                  <span className="text-muted-foreground">{c.description}</span>
                </li>
              ))}
            </ul>
            <div className="flex min-w-0 flex-col gap-2">
              <h3 id={payloadId} className="type-label-md">
                Example of what one request contains, from your file
              </h3>
              <pre
                role="region"
                aria-labelledby={payloadId}
                tabIndex={0}
                className="max-h-56 overflow-auto rounded-lg bg-muted p-3 type-code-sm whitespace-pre xl:max-h-72"
              >
                {JSON.stringify(disclosure.data.example_payload, null, 2)}
              </pre>
              <p className="type-body-sm text-muted-foreground">{disclosure.data.retention_note}</p>
              <p className="type-caption text-muted-foreground">Disclosure version {disclosure.data.version}</p>
            </div>
          </div>
        ) : !disclosure.error ? (
          <p className="text-muted-foreground">Loading what will be shared…</p>
        ) : null}
        {consent.error ? <ErrorNotice error={consent.error} title="Your choice was not recorded." /> : null}
        {accepted && record ? (
          <Notice variant="success">
            <CircleCheck aria-hidden />
            <NoticeBody>
              <NoticeTitle>Sharing allowed</NoticeTitle>
              <p>
                You allowed {info?.label ?? provider} to receive the items above (version {record.disclosure_version}) on{' '}
                {dateFormat.format(new Date(record.accepted_at))}.
              </p>
            </NoticeBody>
          </Notice>
        ) : null}
        <CardFooter sticky>
          <Button
            disabled={!disclosure.data || consent.isPending || Boolean(accepted)}
            onClick={() => disclosure.data && consent.mutate({ provider, version: disclosure.data.version })}
          >
            {consent.isPending ? 'Recording…' : accepted ? 'Allowed' : `Allow sharing with ${info?.label ?? provider}`}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
