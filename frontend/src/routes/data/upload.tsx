// Upload (A3; C12): send a weekly CSV through the generated client with progress, show every
// rejection reason in plain language, then the data profile. The backend decides what is valid.

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { ChartPie, CircleAlert, CircleCheck, FileUp } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { Link } from 'react-router';

import { ErrorNotice } from '@/app/components/error-notice';
import { StatTile, StatTiles } from '@/app/components/stat-tile';
import { Badge } from '@/app/components/ui/badge';
import { Button } from '@/app/components/ui/button';
import { Card, CardDescription, CardHeader, CardTitle } from '@/app/components/ui/card';
import { Notice, NoticeBody, NoticeTitle } from '@/app/components/ui/notice';
import { Progress } from '@/app/components/ui/progress';
import { ApiError, INTAKE_REJECTIONS, isIntakeRejection } from '@/app/errors';
import { useProjectId } from '@/app/project-layout';
import { profileQuery } from '@/app/queries';
import { uploadData, type Progress as UploadProgress } from '@/app/upload';
import type { DataProfile, DataVersion } from '@/client';

export const handle = { title: 'Data' };

const numberFormat = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
const pctFormat = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 });

function Rejection({ error }: { error: ApiError | Error }) {
  if (error instanceof ApiError && isIntakeRejection(error.code)) {
    const reason = INTAKE_REJECTIONS[error.code];
    return (
      <Notice variant="destructive" role="alert">
        <CircleAlert aria-hidden />
        <NoticeBody>
          <NoticeTitle>The file was not accepted. {reason.title}</NoticeTitle>
          <p>{reason.hint}</p>
        </NoticeBody>
      </Notice>
    );
  }
  return <ErrorNotice error={error} title="The file was not accepted." />;
}

export function ProfileTable({ profile }: { profile: DataProfile }) {
  return (
    <div className="flex flex-col gap-3">
      <StatTiles label="Data summary">
        <StatTile label="Rows" value={profile.rows.toLocaleString()} />
        <StatTile label="Weeks" value={profile.weeks.toLocaleString()} />
        <StatTile label="Regions" value={profile.regions.toLocaleString()} />
      </StatTiles>
      <div className="overflow-x-auto rounded-xl border border-border" tabIndex={0} role="region" aria-label="Column profile">
        <table className="w-full type-data-md">
          <caption className="sr-only">What truelift found in each column</caption>
          <thead>
            <tr className="border-b border-border text-left">
              {['Column', 'Kind', 'Lowest', 'Highest', 'Missing'].map((h, i) => (
                <th key={h} scope="col" className={`h-9 px-3 type-label-md text-muted-foreground ${i >= 2 ? 'text-right' : ''}`}>
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {profile.columns.map((c) => (
              <tr key={c.name} className="h-9 border-b border-border last:border-0">
                <th scope="row" className="px-3 text-left font-normal">
                  <span className="type-code-sm">{c.name}</span>
                  {c.ground_truth_excluded ? (
                    <Badge variant="outline" className="ml-2">
                      ground truth: excluded
                    </Badge>
                  ) : null}
                </th>
                <td className="px-3">{c.semantic_type}</td>
                <td className="px-3 text-right tabular-nums">{c.min === null ? '–' : numberFormat.format(c.min)}</td>
                <td className="px-3 text-right tabular-nums">{c.max === null ? '–' : numberFormat.format(c.max)}</td>
                <td className="px-3 text-right tabular-nums">{pctFormat.format(c.missing_share)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {profile.observations.length ? (
        <ul className="flex list-disc flex-col gap-1 pl-5 text-muted-foreground marker:text-muted-foreground">
          {profile.observations.map((o) => (
            <li key={o}>{o}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export function Component() {
  const projectId = useProjectId();
  const queryClient = useQueryClient();
  const inputId = useId();
  const hintId = useId();
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState<UploadProgress | null>(null);
  const [uploaded, setUploaded] = useState<DataVersion | null>(null);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const upload = useMutation({
    mutationFn: async (f: File) => {
      abort.current = new AbortController();
      setProgress({ loaded: 0, total: f.size });
      return uploadData(projectId, f, setProgress, abort.current.signal);
    },
    onSuccess: (version) => {
      setUploaded(version);
      void queryClient.invalidateQueries({ queryKey: ['project', projectId] });
    },
    onSettled: () => setProgress(null),
  });

  const profile = useQuery({ ...profileQuery(projectId), enabled: uploaded !== null });

  return (
    <div className="flex flex-col gap-6">
      <Card>
        <CardHeader icon={FileUp}>
          <CardTitle>Upload your sales data</CardTitle>
          <CardDescription>
            A CSV with one row per week and region: the week, the region, sales, the discount and anything else you
            track. The file stays on this computer.
          </CardDescription>
        </CardHeader>
        <form
          className="flex flex-col gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (file) upload.mutate(file);
          }}
        >
          <label htmlFor={inputId} className="type-label-md">
            CSV file
          </label>
          <input
            id={inputId}
            type="file"
            accept=".csv,text/csv"
            aria-describedby={hintId}
            onChange={(e) => {
              setFile(e.target.files?.[0] ?? null);
              upload.reset();
            }}
            className="type-body-md file:mr-3 file:h-8 file:cursor-pointer file:rounded-lg file:border file:border-input file:bg-card file:px-3 file:type-label-md file:text-foreground hover:file:bg-accent"
          />
          <p id={hintId} className="type-caption text-muted-foreground">
            Weekly data only. Daily or monthly data must be summed to weeks first.
          </p>
          <div className="flex gap-2">
            <Button type="submit" disabled={!file || upload.isPending}>
              <FileUp aria-hidden />
              {upload.isPending ? 'Uploading…' : 'Upload'}
            </Button>
            {upload.isPending ? (
              <Button variant="outline" onClick={() => abort.current?.abort()}>
                Cancel
              </Button>
            ) : null}
          </div>
          {progress ? <Progress value={progress.loaded} max={progress.total || 1} label="Uploading" /> : null}
        </form>
        {upload.error && !(upload.error instanceof DOMException) ? <Rejection error={upload.error} /> : null}
        {uploaded && !upload.isPending ? (
          <Notice variant="success">
            <CircleCheck aria-hidden />
            <NoticeBody>
              <NoticeTitle>Uploaded {uploaded.filename}</NoticeTitle>
              <p className="tabular-nums">
                Version {uploaded.version} · {uploaded.rows.toLocaleString()} rows · {uploaded.columns} columns
              </p>
            </NoticeBody>
          </Notice>
        ) : null}
      </Card>
      {uploaded ? (
        <Card>
          <CardHeader icon={ChartPie}>
            <CardTitle>What truelift found</CardTitle>
          </CardHeader>
          {profile.error ? <ErrorNotice error={profile.error} title="The profile could not be loaded." /> : null}
          {profile.data ? <ProfileTable profile={profile.data} /> : <p className="text-muted-foreground">Reading the file…</p>}
          <div className="flex justify-end gap-2">
            <Link to="../consent" className="inline-flex h-8 items-center rounded-lg border border-input bg-card px-3 type-label-md hover:bg-accent">
              Review what is shared
            </Link>
            <Link to="../mapping" className="inline-flex h-8 items-center rounded-lg bg-primary px-3 type-label-md text-primary-foreground hover:bg-primary-hover">
              Review column roles
            </Link>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
