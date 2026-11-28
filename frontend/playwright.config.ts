import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  // Browser cases share a seeded PostgreSQL stack with >100k rows; limiting
  // workers avoids turning concurrent list scans into test-only overload.
  workers: 2,
  use: { baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173', headless: true, channel: 'chrome' },
  reporter: 'list',
});
