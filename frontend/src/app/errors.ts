// One error type for the whole app, built from the API's ErrorBody (code, message, request_id,
// fields). Server messages are plain language and are always rendered as text (SB10).

import type { ErrorBody, FieldError } from '@/client';

/**
 * The backend's IntakeErrorCode (src/truelift/api/schemas.py). It is not in openapi.json because
 * no response model references it, so it is listed here; tests/stub-api.contract.test.ts uploads
 * `<code>.csv` for each one against the G02 stub and fails if a code is missing or renamed.
 */
export const INTAKE_ERROR_CODES = [
  'not_csv',
  'empty_file',
  'missing_date',
  'not_weekly',
  'duplicate_keys',
  'malformed_rows',
] as const;
export type IntakeErrorCode = (typeof INTAKE_ERROR_CODES)[number];

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly fields: FieldError[];

  constructor(status: number, code: string, message: string, requestId: string | null, fields: FieldError[] = []) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fields = fields;
  }
}

function isErrorBody(value: unknown): value is ErrorBody {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as ErrorBody).code === 'string' &&
    typeof (value as ErrorBody).message === 'string'
  );
}

/** Convert whatever the generated client threw into an ApiError. */
export function toApiError(error: unknown, response?: Response): ApiError {
  if (error instanceof ApiError) return error;
  const status = response?.status ?? 0;
  if (isErrorBody(error)) {
    return new ApiError(status, error.code, error.message, error.request_id ?? null, error.fields ?? []);
  }
  if (status === 0) {
    return new ApiError(0, 'network_error', 'truelift is not reachable. Check that the truelift window is still open.', null);
  }
  return new ApiError(status, 'unexpected_response', 'Something went wrong. Try again.', null);
}

/**
 * Upload rejection reasons (C12, G02 stub contract), in plain language with what to do next.
 * G07 keeps these codes; G20/A1 checks the real reasons.
 */
export const INTAKE_REJECTIONS: Record<IntakeErrorCode | 'payload_too_large', { title: string; hint: string }> = {
  not_csv: { title: 'This is not a CSV file.', hint: 'Export the sheet as .csv and upload that file.' },
  empty_file: { title: 'The file is empty.', hint: 'Check that you exported the data, not an empty sheet.' },
  missing_date: {
    title: 'No column holds dates.',
    hint: 'truelift needs one row per week and region, with a date column for the week.',
  },
  not_weekly: {
    title: 'The dates are not weekly.',
    hint: 'truelift needs one row per week and region. Aggregate daily or monthly data to weeks first.',
  },
  duplicate_keys: {
    title: 'Some week and region pairs appear more than once.',
    hint: 'Keep one row for each week and region, then upload again.',
  },
  malformed_rows: {
    title: 'Some rows could not be read.',
    hint: 'Check for broken quotes or a different number of columns in some rows.',
  },
  payload_too_large: { title: 'The file is too large.', hint: 'Upload weekly totals rather than raw transactions.' },
};

export function isIntakeRejection(code: string): code is keyof typeof INTAKE_REJECTIONS {
  return Object.hasOwn(INTAKE_REJECTIONS, code);
}
