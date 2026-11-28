import { expect, test } from '@playwright/test';

test('review a persisted case and compare workload on the same replay', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Requires the authenticated, seeded local acceptance stack.');

  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();

  const impact = page.getByRole('heading', { name: 'Investigation impact' }).locator('xpath=../../..');
  const response = page.waitForResponse(result => result.url().includes('/analytics/impact?review_budget=25'));
  await impact.getByLabel('Review budget').fill('25');
  await impact.getByRole('button', { name: 'Run comparison' }).click();
  expect((await response).ok()).toBe(true);
  await expect(impact.getByText(/scored events/)).toBeVisible({ timeout: 15_000 });
  await expect(impact.getByRole('columnheader', { name: 'One alert per event' })).toBeVisible();
  await expect(impact.getByRole('columnheader', { name: 'Correlated', exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Investigations', exact: true }).click();
  const queue = page.getByRole('heading', { name: 'Priority investigations' }).locator('xpath=../../..');
  await queue.getByRole('row').nth(1).getByRole('cell').first().click();
  await expect(page.getByRole('heading', { name: 'Correlated event timeline' })).toBeVisible();
  const rationale = `Local browser acceptance review ${Date.now()}`;
  await page.getByLabel('Reviewed outcome').selectOption('inconclusive');
  await page.getByLabel('Evidence or rationale').fill(rationale);
  await page.getByRole('button', { name: /Record (adjudication|correction)/ }).click();
  await expect(page.getByText(rationale, { exact: true })).toBeVisible();

  await page.getByRole('button', { name: 'Event explorer', exact: true }).click();
  await page.getByRole('button', { name: 'Load review sample' }).click();
  await expect(page.getByText(/eligible predictions/)).toBeVisible();
});
