import { expect, test } from '@playwright/test';

const apiBase = process.env.TEST_API_URL || 'http://localhost:8000/api';
const roles = ['Administrator', 'Fraud Analyst', 'Investigator', 'ML Engineer', 'Auditor'] as const;

test('role controls match the backend permissions for analyst workflows', async ({ page }) => {
  const adminUsername = process.env.TEST_ADMIN_USERNAME;
  const adminPassword = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!adminUsername || !adminPassword, 'Requires the isolated authenticated local acceptance stack.');

  const login = await page.request.post(`${apiBase}/auth/login`, {
    data: { username: adminUsername, password: adminPassword },
  });
  expect(login.ok()).toBeTruthy();
  const adminToken = (await login.json()).access_token as string;
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
  const eventId = `e2e-feedback-${suffix}`;
  const eventCreated = await page.request.post(`${apiBase}/events`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { event_id: eventId, event_type: 'CALL', event_time: new Date().toISOString(),
      subscriber_id: `e2e-subscriber-${suffix}`, duration_seconds: 73 },
  });
  expect(eventCreated.status(), 'create a synthetic unlabeled feedback fixture').toBe(201);
  const credentials = new Map<string, { username: string; password: string }>();
  for (const [index, role] of roles.entries()) {
    const username = `e2e-${index}-${suffix}`;
    const password = `Test-only-${suffix}-${index}!`;
    const created = await page.request.post(`${apiBase}/auth/users`, {
      headers: { Authorization: `Bearer ${adminToken}` },
      data: { username, password, role },
    });
    expect(created.status(), `create isolated ${role} user`).toBe(201);
    credentials.set(role, { username, password });
  }

  await page.addInitScript(() => { localStorage.removeItem('tg-token'); localStorage.removeItem('tg-user'); });
  for (const role of roles) {
    const account = credentials.get(role)!;
    await page.goto('/');
    await page.getByPlaceholder('admin').fill(account.username);
    await page.locator('input[name="password"]').fill(account.password);
    await page.getByRole('button', { name: /Secure sign in/ }).click();
    await expect(page.getByText(role, { exact: true }).first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Administration', exact: true }))
      .toHaveCount(role === 'Administrator' || role === 'Auditor' ? 1 : 0);
    await expect(page.getByRole('button', { name: 'Scenario lab', exact: true }))
      .toHaveCount(role === 'Auditor' ? 0 : 1);
    await expect(page.getByRole('button', { name: 'Live simulator', exact: true }))
      .toHaveCount(role === 'Auditor' ? 0 : 1);

    const canCreateEvents = role !== 'Auditor';
    const canLabelEvents = role === 'Administrator' || role === 'Fraud Analyst' || role === 'Investigator';
    const canReviewCases = role === 'Administrator' || role === 'Fraud Analyst' || role === 'Investigator';
    const canTakeAction = role === 'Administrator' || role === 'Investigator';
    const canTrain = role === 'Administrator' || role === 'ML Engineer';

    await expect(page.getByRole('button', { name: 'Run scenario' })).toHaveCount(canCreateEvents ? 1 : 0);
    await page.getByRole('button', { name: 'Event explorer', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Add label' }).first()).toHaveCount(canLabelEvents ? 1 : 0);
    if (role === 'ML Engineer' || role === 'Auditor') {
      const roleLogin = await page.request.post(`${apiBase}/auth/login`, { data: credentials.get(role)! });
      expect(roleLogin.ok()).toBeTruthy();
      const roleToken = (await roleLogin.json()).access_token as string;
      const denied = await page.request.post(`${apiBase}/predictions/${eventId}/label`, {
        headers: { Authorization: `Bearer ${roleToken}` },
        data: { label: 0, reason: 'Role-boundary regression check' },
      });
      expect(denied.status(), `${role} cannot adjudicate an event`).toBe(403);
    }
    if (role === 'Fraud Analyst') {
      await page.getByPlaceholder('Filter event ID, subscriber, or type').fill(eventId);
      const row = page.getByRole('row').filter({ hasText: eventId });
      await expect(row).toBeVisible();
      const rationale = `Reviewed with synthetic fixture evidence ${suffix}`;
      let promptIndex = 0;
      const answers = ['confirmed_fraud', rationale];
      const acceptPrompt = (dialog: import('@playwright/test').Dialog) => { void dialog.accept(answers[promptIndex++]); };
      page.on('dialog', acceptPrompt);
      const savedReview = page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes(`/predictions/${eventId}/adjudications`));
      await row.getByRole('button', { name: 'Add label' }).click();
      page.off('dialog', acceptPrompt);
      const reviewResponse = await savedReview;
      expect(reviewResponse.status(), await reviewResponse.text()).toBe(201);
      const reviews = await page.request.get(`${apiBase}/predictions/${eventId}/adjudications`, {
        headers: { Authorization: `Bearer ${adminToken}` },
      });
      expect(reviews.ok()).toBeTruthy();
      const history = await reviews.json();
      expect(history[0]).toMatchObject({ reviewer: account.username, outcome: 'confirmed_fraud', reason: rationale });
      expect(history[0].reviewed_at).toBeTruthy();
    }

    await page.getByRole('button', { name: 'Model intelligence', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Train candidate' })).toHaveCount(canTrain ? 1 : 0);

    await page.getByRole('button', { name: 'Investigations', exact: true }).click();
    await page.getByPlaceholder('Search subscriber or incident').fill('');
    await expect(page.getByRole('button', { name: 'Note', exact: true }).first()).toHaveCount(canReviewCases ? 1 : 0);
    await expect(page.getByRole('button', { name: 'Simulate', exact: true }).first()).toHaveCount(canTakeAction ? 1 : 0);
  }
});

test('stored display role cannot override the authenticated backend role', async ({ page }) => {
  const adminUsername = process.env.TEST_ADMIN_USERNAME;
  const adminPassword = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!adminUsername || !adminPassword, 'Requires the isolated authenticated local acceptance stack.');
  const adminLogin = await page.request.post(`${apiBase}/auth/login`, {
    data: { username: adminUsername, password: adminPassword },
  });
  expect(adminLogin.ok()).toBeTruthy();
  const adminToken = (await adminLogin.json()).access_token as string;
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 10_000)}`;
  const username = `e2e-authoritative-${suffix}`;
  const password = `Test-only-${suffix}-Authority!`;
  const created = await page.request.post(`${apiBase}/auth/users`, {
    headers: { Authorization: `Bearer ${adminToken}` },
    data: { username, password, role: 'Fraud Analyst' },
  });
  expect(created.status()).toBe(201);
  const analystLogin = await page.request.post(`${apiBase}/auth/login`, { data: { username, password } });
  expect(analystLogin.ok()).toBeTruthy();
  const analystToken = (await analystLogin.json()).access_token as string;

  await page.goto('/');
  await page.evaluate(token => {
    localStorage.setItem('tg-token', token);
    localStorage.setItem('tg-user', JSON.stringify({ username: 'forged-admin', role: 'Administrator' }));
  }, analystToken);
  await page.reload();
  await expect(page.getByText('Fraud Analyst', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('forged-admin', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Administration', exact: true })).toHaveCount(0);
});
