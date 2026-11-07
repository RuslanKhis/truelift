// Generates src/client from the committed OpenAPI dump (G02, contract C16).
// Run through `make client`; `make check` regenerates into build/ and fails on drift.
// OPENAPI_INPUT and OPENAPI_OUTPUT exist only so the drift check can write elsewhere.
import { defineConfig } from '@hey-api/openapi-ts';

export default defineConfig({
  input: process.env.OPENAPI_INPUT ?? '../openapi.json',
  output: process.env.OPENAPI_OUTPUT ?? 'src/client',
  plugins: ['@hey-api/client-fetch', '@hey-api/typescript', '@hey-api/sdk'],
});
