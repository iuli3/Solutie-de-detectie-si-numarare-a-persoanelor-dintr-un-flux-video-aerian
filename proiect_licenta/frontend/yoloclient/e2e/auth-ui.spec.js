import { test, expect } from '@playwright/test';
import { fillLoginForm, uniqueEmail } from './helpers.js';

test('register and login through the real UI, then loads dashboard', async ({ page }) => {
  const email = uniqueEmail('register-login-ui');
  const password = 'E2ePass123!';

  await page.goto('/register');
  await page.locator('input[name="firstName"]').fill('Ana');
  await page.locator('input[name="lastName"]').fill('Test');
  await page.locator('input[name="email"]').fill(email);
  await page.locator('input[name="password"]').fill(password);
  await page.getByRole('button', { name: /CREARE PROFIL/i }).click();

  await expect(page.getByText(/Cont creat cu succes/i)).toBeVisible();
  await expect(page).toHaveURL(/\/login/, { timeout: 5000 });

  await fillLoginForm(page, email, password);

  await expect(page.getByText(/Server Online/i)).toBeVisible();
  await expect(page.getByRole('link', { name: /Upload Video/i })).toBeVisible();
  await expect(page.getByText(/Recent Activity/i)).toBeVisible();
});
