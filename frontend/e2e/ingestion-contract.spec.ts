import { expect, test } from '@playwright/test';

const apiBase = process.env.TEST_API_URL || 'http://localhost:8000/api';

test('PostgreSQL event IDs are idempotent, conflict-safe and atomic across ingress', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Requires the isolated PostgreSQL acceptance stack.');
  const login = await page.request.post(`${apiBase}/auth/login`, { data: { username, password } });
  expect(login.ok()).toBeTruthy();
  const token = (await login.json()).access_token as string;
  const headers = { Authorization: `Bearer ${token}` };
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const base = {
    event_type: 'CALL', event_time: new Date().toISOString(),
    subscriber_id: `ingest-subscriber-${suffix}`, duration_seconds: 37,
  };
  const submit = (event_id: string, subscriber_id = base.subscriber_id) => page.request.post(`${apiBase}/events`, {
    headers, data: { ...base, event_id, subscriber_id },
  });

  const repeatedId = `ingest-repeat-${suffix}`;
  expect((await submit(repeatedId)).status()).toBe(201);
  const retry = await submit(repeatedId);
  expect(retry.status()).toBe(201);
  expect((await retry.json()).duplicate).toBe(true);
  expect((await submit(repeatedId, `different-subscriber-${suffix}`)).status()).toBe(409);

  const simultaneousId = `ingest-race-${suffix}`;
  const simultaneous = await Promise.all([submit(simultaneousId), submit(simultaneousId)]);
  expect(simultaneous.map(response => response.status())).toEqual([201, 201]);
  const simultaneousBodies = await Promise.all(simultaneous.map(response => response.json()));
  expect(simultaneousBodies.filter(body => body.duplicate)).toHaveLength(1);
  const simultaneousRead = await page.request.get(`${apiBase}/events?${new URLSearchParams({ q: simultaneousId })}`, { headers });
  expect((await simultaneousRead.json()).map((row: { event_id: string }) => row.event_id)).toEqual([simultaneousId]);

  const conflictingRaceId = `ingest-conflict-race-${suffix}`;
  const conflictRace = await Promise.all([
    submit(conflictingRaceId, `race-subscriber-a-${suffix}`),
    submit(conflictingRaceId, `race-subscriber-b-${suffix}`),
  ]);
  expect(conflictRace.map(response => response.status()).sort()).toEqual([201, 409]);

  const csvConflictId = `ingest-csv-conflict-${suffix}`;
  expect((await submit(csvConflictId)).status()).toBe(201);
  const csv = [
    'event_id,event_type,event_time,subscriber_id,duration_seconds',
    `${csvConflictId},CALL,${base.event_time},csv-conflicting-subscriber-${suffix},37`,
    `ingest-csv-atomic-${suffix},CALL,${base.event_time},csv-new-subscriber-${suffix},42`,
  ].join('\n');
  const rejected = await page.request.post(`${apiBase}/events/upload-csv`, {
    headers: { ...headers, 'Content-Type': 'text/csv' }, data: csv,
  });
  expect(rejected.status()).toBe(409);
  const atomicCheck = await page.request.get(`${apiBase}/events?${new URLSearchParams({ q: `ingest-csv-atomic-${suffix}` })}`, { headers });
  expect(await atomicCheck.json()).toHaveLength(0);
});
