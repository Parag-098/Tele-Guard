import { expect, test } from '@playwright/test';

test('administrator can inspect delayed labels and controlled model serving', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Set TEST_ADMIN_USERNAME and TEST_ADMIN_PASSWORD for local acceptance.');
  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();
  await expect(page.getByText('Fraud intelligence overview')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Delayed-label monitoring' })).toBeVisible();
  await page.getByRole('button', { name: 'MLOps lifecycle' }).click();
  await expect(page.getByRole('heading', { name: 'Delayed label monitoring' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Serving deployment' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Location and travel scenarios' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start shadow' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Start canary' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Compare registered candidate' })).toBeVisible();
});

test('event explorer exposes delayed ground-truth label action', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Set TEST_ADMIN_USERNAME and TEST_ADMIN_PASSWORD for local acceptance.');
  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();
  await page.getByRole('button', { name: 'Event explorer' }).click();
  await expect(page.getByRole('columnheader', { name: 'LABEL' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Add label' }).first()).toBeVisible();
  await expect(page.getByText(/Page 1.*100 shown/)).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText(/Page 2.*100 shown/)).toBeVisible();
});

test('administrator can inspect persisted datasets and service health', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Set TEST_ADMIN_USERNAME and TEST_ADMIN_PASSWORD for local acceptance.');
  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();
  await page.getByRole('button', { name: 'Data observatory' }).click();
  await expect(page.getByRole('heading', { name: 'Versioned datasets' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Initial dataset generation' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'CSV event ingestion' })).toBeVisible();
  await expect(page.getByText('synthetic-v2-150000-20261119')).toBeVisible();
  await expect(page.getByText('150,000 / 150,000')).toBeVisible();
  await page.getByRole('button', { name: 'Investigations' }).click();
  await expect(page.getByText(/Page 1.*100 shown/)).toBeVisible();
  await page.getByRole('button', { name: 'Next' }).click();
  await expect(page.getByText(/Page 2.*100 shown/)).toBeVisible();
  await page.getByRole('button', { name: 'Live monitoring' }).click();
  await expect(page.getByText('Overall status:')).toBeVisible();
  await expect(page.getByText('healthy', { exact: true }).first()).toBeVisible();
});
