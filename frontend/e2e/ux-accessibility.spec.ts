import { expect, test } from '@playwright/test';

test('mobile layout and keyboard paths expose chart summaries and open investigations', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Requires the isolated authenticated acceptance stack.');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();
  await expect(page.getByRole('img', { name: /Risk distribution by saved risk band/ })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);

  await page.getByRole('button', { name: 'Overview', exact: true }).focus();
  await page.keyboard.press('Tab');
  await expect(page.getByRole('button', { name: 'Fraud alerts', exact: true })).toBeFocused();

  await page.getByRole('button', { name: 'Investigations', exact: true }).click();
  const openCase = page.getByRole('button', { name: /Open investigation/ }).first();
  await expect(openCase).toBeVisible();
  await openCase.focus();
  await page.keyboard.press('Enter');
  await expect(page.getByRole('heading', { name: /^Investigation #/ })).toBeVisible();
});

test('partial API failure keeps available dashboard data and redacts server details', async ({ page }) => {
  const username = process.env.TEST_ADMIN_USERNAME;
  const password = process.env.TEST_ADMIN_PASSWORD;
  test.skip(!username || !password, 'Requires the isolated authenticated local acceptance stack.');
  await page.route('**/api/graph**', route => route.fulfill({
    status: 503,
    contentType: 'application/json',
    body: JSON.stringify({ detail: 'postgres://admin:secret-password@internal-db/private' }),
  }));
  await page.goto('/');
  await page.getByPlaceholder('admin').fill(username!);
  await page.locator('input[name="password"]').fill(password!);
  await page.getByRole('button', { name: /Secure sign in/ }).click();
  await expect(page.getByRole('heading', { name: 'Fraud intelligence overview' })).toBeVisible();
  await expect(page.getByText(/Some workspace data is unavailable \(network graph\)/)).toBeVisible();
  await expect(page.getByText(/secret-password|internal-db/)).toHaveCount(0);
  await expect(page.getByText('Persisted synthetic events', { exact: true })).toBeVisible();
});
