import { test, expect } from '@playwright/test';
test('protected routes redirect unauthenticated users to login', async ({ page }) => {
  await page.goto('/dashboard');

  await expect(page).toHaveURL(/\/login/);
  await expect(page.getByRole('button', { name: /ACCES SISTEM/i })).toBeVisible();
});
