// Setup: choose a provider and send its API key once (A2; C7). The key lives only in this form's
// state until the PUT succeeds, then it is cleared. It is never put in localStorage,
// sessionStorage, the query cache or a URL; the backend keeps it in the OS keychain (G11).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, CircleCheck, Info, KeyRound } from 'lucide-react';
import { useId, useState } from 'react';
import { Link } from 'react-router';

import { ErrorNotice } from '@/app/components/error-notice';
import { PageHeader } from '@/app/components/page-header';
import { Badge } from '@/app/components/ui/badge';
import { Button } from '@/app/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/app/components/ui/card';
import { Input } from '@/app/components/ui/input';
import { Notice, NoticeBody } from '@/app/components/ui/notice';
import { keys, setupQuery } from '@/app/queries';
import { setupPutApiKey } from '@/client';
import type { Provider, ProviderInfo } from '@/client';

export const handle = { title: 'AI provider' };

function ProviderChoice({
  providers,
  value,
  onChange,
}: {
  providers: ProviderInfo[];
  value: Provider;
  onChange: (p: Provider) => void;
}) {
  return (
    <fieldset className="grid gap-3 md:grid-cols-2">
      <legend className="mb-2 type-label-md">Provider</legend>
      {providers.map((p) => (
        <label
          key={p.provider}
          className="flex min-h-16 cursor-pointer items-center gap-3 rounded-xl border border-border bg-card px-4 py-3 transition-[border-color,background-color] duration-150 ease-out hover:border-input has-checked:border-primary-ink has-checked:bg-choice"
        >
          <input
            type="radio"
            name="provider"
            value={p.provider}
            checked={value === p.provider}
            onChange={() => onChange(p.provider)}
            className="size-4 accent-primary-ink"
          />
          <span className="flex flex-1 flex-col">
            <span className="type-label-md">{p.label}</span>
            <span className="type-caption text-muted-foreground">Model {p.model_id}</span>
          </span>
          {p.key_configured ? (
            <Badge variant="success">
              <CircleCheck aria-hidden />
              Key saved
            </Badge>
          ) : (
            <Badge variant="outline">No key yet</Badge>
          )}
        </label>
      ))}
    </fieldset>
  );
}

/** Why an AI model, kept short: the landing page already explains the product. The model talks;
 *  the numbers come from code on this computer (AGENTS.md: the model talks and code decides). */
function WhyPanel() {
  const does = ['Runs the interview', 'Drafts the cause-and-effect map', 'Explains the results in words'];
  // A callout, not a section: extra information under the key card, on the muted surface with an
  // info icon, the title inline in bold and the model's three jobs as plain check lines.
  return (
    <section aria-labelledby="why-ai" className="flex gap-3 rounded-xl bg-muted p-4 md:p-5">
      <Info aria-hidden className="mt-0.5 size-5 shrink-0 text-primary-ink" />
      <div className="flex min-w-0 flex-col gap-3">
        <p>
          <strong id="why-ai" className="font-semibold">
            Why truelift needs an AI model
          </strong>
          <span className="text-muted-foreground">
            {' '}
            · It talks with you. The return on your discounts is calculated on this computer, never by the AI.
          </span>
        </p>
        <ul className="flex flex-col gap-1.5">
          {does.map((title) => (
            <li key={title} className="flex items-start gap-2">
              <Check aria-hidden className="mt-1 size-4 shrink-0 text-primary-ink" />
              {title}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function Component() {
  const setup = useQuery(setupQuery());
  const queryClient = useQueryClient();
  const [chosen, setChosen] = useState<Provider | null>(null);
  const [apiKey, setApiKey] = useState('');
  const [saved, setSaved] = useState<Provider | null>(null);
  const keyId = useId();
  const hintId = useId();

  const provider = chosen ?? setup.data?.active_provider ?? setup.data?.providers[0]?.provider ?? null;
  const info = setup.data?.providers.find((p) => p.provider === provider);

  const save = useMutation({
    mutationFn: async (vars: { provider: Provider; key: string }) => {
      await setupPutApiKey({ body: { provider: vars.provider, api_key: vars.key }, throwOnError: true });
      return vars.provider;
    },
    onSuccess: (p) => {
      setApiKey('');
      setSaved(p);
      void queryClient.invalidateQueries({ queryKey: keys.setup });
    },
    onError: () => setApiKey(''),
  });

  const header = (
    <PageHeader
      eyebrow="Setup"
      title="Connect an AI provider"
      lead="truelift uses an AI model to talk with you in plain language. It never does the maths."
    />
  );

  if (setup.error || !setup.data || !provider) {
    return (
      <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
        {header}
        {setup.error ? (
          <ErrorNotice error={setup.error} title="The provider list could not be loaded." />
        ) : (
          <p className="text-muted-foreground">Loading providers…</p>
        )}
      </div>
    );
  }

  const tooShort = apiKey.length > 0 && apiKey.length < 10;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-8">
      {header}
      <div className="flex flex-col gap-6">
        <Card>
          <CardHeader icon={KeyRound}>
            <CardTitle>Choose your provider and add a key</CardTitle>
            <CardDescription>
              truelift uses your own key and your own account. You pay the provider directly for what you use.
            </CardDescription>
          </CardHeader>
          <ProviderChoice
            providers={setup.data.providers}
            value={provider}
            onChange={(p) => {
              setChosen(p);
              setSaved(null);
              save.reset();
            }}
          />
          <form
            className="flex flex-col gap-2"
            autoComplete="off"
            onSubmit={(e) => {
              e.preventDefault();
              if (apiKey.length >= 10) save.mutate({ provider, key: apiKey });
            }}
          >
            <label htmlFor={keyId} className="type-label-md">
              API key for {info?.label ?? provider}
            </label>
            <div className="flex max-w-2xl gap-2 max-sm:flex-col">
              <Input
                id={keyId}
                type="password"
                name="api-key"
                autoComplete="off"
                spellCheck={false}
                value={apiKey}
                aria-describedby={hintId}
                aria-invalid={tooShort || undefined}
                onChange={(e) => setApiKey(e.target.value)}
              />
              <Button type="submit" disabled={apiKey.length < 10 || save.isPending}>
                {save.isPending ? 'Saving…' : 'Save key'}
              </Button>
            </div>
            <p id={hintId} className="type-caption text-muted-foreground">
              {tooShort
                ? 'This key looks too short. Paste the whole key.'
                : 'Sent once to truelift on this computer, which keeps it in your system keychain. It is never stored in this browser.'}
            </p>
          </form>
          {save.error ? <ErrorNotice error={save.error} title="The key was not saved." /> : null}
          {saved === provider && !save.isPending ? (
            <Notice variant="success">
              <CircleCheck aria-hidden />
              <NoticeBody>
                <p>The key for {info?.label ?? provider} is saved. truelift will not show it again.</p>
              </NoticeBody>
            </Notice>
          ) : null}
        </Card>
        <WhyPanel />
      </div>
      <p className="text-muted-foreground">
        Next: open a project, upload your data and review what will be shared. Go to the{' '}
        <Link to="/" className="text-primary-ink underline underline-offset-4">
          home page
        </Link>
        .
      </p>
    </div>
  );
}
