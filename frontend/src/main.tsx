import './app/theme.css';

import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { RouterProvider } from 'react-router/dom';

import { configureApi } from './app/api';
import { createQueryClient } from './app/queries';
import { createRouter } from './app/router';
import { captureLaunchToken } from './app/token';

// Order matters: take the token out of the fragment before anything renders or fetches (D12).
captureLaunchToken();
configureApi();

const queryClient = createQueryClient();
const router = createRouter();

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root element');

createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
