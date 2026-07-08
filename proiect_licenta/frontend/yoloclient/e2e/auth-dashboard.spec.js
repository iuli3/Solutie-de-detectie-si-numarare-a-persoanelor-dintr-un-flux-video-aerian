import { test, expect } from '@playwright/test';
import { authenticatePage } from './helpers.js';

test('dashboard opens for an authenticated browser session', async ({ page, request }) => {
  await authenticatePage(page, request);

  await page.goto('/dashboard');

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText(/Server Online/i)).toBeVisible();
  await expect(page.getByRole('link', { name: /Upload Video/i })).toBeVisible();
});
