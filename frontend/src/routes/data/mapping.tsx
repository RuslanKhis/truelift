// Mapping review (A4; C12): each column's role with the backend's per-role check shown inline.
// A change is sent to the backend, which validates it; Confirm stays disabled until every role
// is valid. The browser never decides validity itself (D2: code decides, here the backend).

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { CircleAlert, CircleCheck, Columns3 } from 'lucide-react';
import { useId } from 'react';

import { ErrorNotice } from '@/app/components/error-notice';
import { Badge } from '@/app/components/ui/badge';
import { Button } from '@/app/components/ui/button';
import { Card, CardDescription, CardFooter, CardHeader, CardTitle } from '@/app/components/ui/card';
import { NativeSelect } from '@/app/components/ui/native-select';
import { Notice, NoticeBody, NoticeTitle } from '@/app/components/ui/notice';
import { useProjectId } from '@/app/project-layout';
import { keys, mappingQuery, profileQuery } from '@/app/queries';
import { intakeConfirmMapping, intakePutMapping } from '@/client';
import type { Mapping, Role, RoleCheck } from '@/client';

export const handle = { title: 'Column roles' };

export const ROLE_LABELS: Record<Role, string> = {
  date: 'Week (date)',
  region: 'Region',
  category: 'Category',
  outcome: 'Sales (outcome)',
  treatment_rate: 'Discount rate',
  treatment_spend: 'Discount spend',
  population: 'Population',
  control: 'Other driver (control)',
  ignore: 'Ignore',
};

function RoleRow({
  check,
  groundTruth,
  disabled,
  onChange,
}: {
  check: RoleCheck;
  groundTruth: boolean;
  disabled: boolean;
  onChange: (role: Role) => void;
}) {
  const selectId = useId();
  const reasonId = useId();
  return (
    <tr className="border-b border-border align-top last:border-0">
      <th scope="row" className="px-3 py-2 text-left font-normal">
        <label htmlFor={selectId} className="type-code-sm">
          {check.column}
        </label>
        {groundTruth ? (
          <Badge variant="outline" className="ml-2">
            ground truth: excluded
          </Badge>
        ) : null}
      </th>
      <td className="w-56 px-3 py-2">
        <NativeSelect
          id={selectId}
          value={check.role}
          disabled={disabled}
          aria-invalid={!check.ok || undefined}
          aria-describedby={reasonId}
          onChange={(e) => onChange(e.target.value as Role)}
        >
          {(Object.keys(ROLE_LABELS) as Role[]).map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </NativeSelect>
      </td>
      <td className="px-3 py-2" id={reasonId}>
        {check.ok ? (
          <span className="inline-flex items-center gap-1 text-success">
            <CircleCheck aria-hidden className="size-4" />
            Valid
          </span>
        ) : (
          <span className="inline-flex items-start gap-1 text-destructive">
            <CircleAlert aria-hidden className="mt-0.5 size-4 shrink-0" />
            <span>
              <span className="sr-only">Not valid:</span> {check.reason ?? 'This role does not fit this column.'}
            </span>
          </span>
        )}
      </td>
    </tr>
  );
}

export function Component() {
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const mapping = useQuery(mappingQuery(projectId));
  const profile = useQuery(profileQuery(projectId));

  const setMapping = (m: Mapping) => queryClient.setQueryData(keys.mapping(projectId), m);

  const change = useMutation({
    mutationFn: async (vars: { base: Mapping; column: string; role: Role }) =>
      (await intakePutMapping({
        path: { project_id: projectId },
        body: {
          expected_version: vars.base.version,
          roles: vars.base.roles.map((r) => ({ column: r.column, role: r.column === vars.column ? vars.role : r.role })),
        },
        throwOnError: true,
      })).data,
    onSuccess: setMapping,
    onError: (error) => {
      if (error.code === 'stale_version') void queryClient.invalidateQueries({ queryKey: keys.mapping(projectId) });
    },
  });

  const confirm = useMutation({
    mutationFn: async (version: number) =>
      (await intakeConfirmMapping({ path: { project_id: projectId }, body: { version }, throwOnError: true })).data,
    onSuccess: (m) => {
      setMapping(m);
      // exact: the project's own record only; a prefix match would refetch and overwrite this mapping.
      void queryClient.invalidateQueries({ queryKey: keys.project(projectId), exact: true });
    },
    onError: (error) => {
      if (error.code === 'stale_version') void queryClient.invalidateQueries({ queryKey: keys.mapping(projectId) });
    },
  });

  if (mapping.error) return <ErrorNotice error={mapping.error} title="The column roles could not be loaded." />;
  if (!mapping.data) return <p className="text-muted-foreground">Loading column roles…</p>;

  const m = mapping.data;
  const groundTruth = new Set(profile.data?.columns.filter((c) => c.ground_truth_excluded).map((c) => c.name));
  const invalid = m.roles.filter((r) => !r.ok).length;
  const busy = change.isPending || confirm.isPending;
  const confirmed = m.status === 'confirmed';
  const canConfirm = invalid === 0 && !busy && !confirmed;

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader icon={Columns3}>
          <CardTitle>Check what each column means</CardTitle>
          <CardDescription>
            truelift checks every role against your data. Fix anything marked not valid, then confirm.
          </CardDescription>
        </CardHeader>
        <div className="overflow-x-auto rounded-xl border border-border" tabIndex={0} role="region" aria-label="Column roles">
          <table className="w-full type-body-md">
            <caption className="sr-only">Column roles and their checks</caption>
            <thead>
              <tr className="border-b border-border text-left">
                <th scope="col" className="h-9 px-3 type-label-md text-muted-foreground">
                  Column
                </th>
                <th scope="col" className="h-9 px-3 type-label-md text-muted-foreground">
                  Role
                </th>
                <th scope="col" className="h-9 px-3 type-label-md text-muted-foreground">
                  Check
                </th>
              </tr>
            </thead>
            <tbody>
              {m.roles.map((check) => (
                <RoleRow
                  key={check.column}
                  check={check}
                  groundTruth={groundTruth.has(check.column)}
                  disabled={busy || confirmed}
                  onChange={(role) => change.mutate({ base: m, column: check.column, role })}
                />
              ))}
            </tbody>
          </table>
        </div>
        <p className="type-body-sm text-muted-foreground" aria-live="polite">
          {confirmed
            ? 'The mapping is confirmed.'
            : invalid === 0
              ? 'Every role is valid.'
              : `${invalid} ${invalid === 1 ? 'role needs' : 'roles need'} fixing before you can confirm.`}
        </p>
        {change.error ? <ErrorNotice error={change.error} title="The change was not saved." /> : null}
        {confirm.error ? <ErrorNotice error={confirm.error} title="The mapping was not confirmed." /> : null}
        {confirmed ? (
          <Notice variant="success">
            <CircleCheck aria-hidden />
            <NoticeBody>
              <NoticeTitle>Mapping confirmed</NoticeTitle>
              <p className="tabular-nums">Version {m.version}. A new data file sends it back for review.</p>
            </NoticeBody>
          </Notice>
        ) : null}
        <CardFooter sticky>
          <Button disabled={!canConfirm} onClick={() => confirm.mutate(m.version)}>
            {confirm.isPending ? 'Confirming…' : confirmed ? 'Confirmed' : 'Confirm roles'}
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
