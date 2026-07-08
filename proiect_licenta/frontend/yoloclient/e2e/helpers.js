import { expect } from '@playwright/test';

export const apiURL = process.env.E2E_API_URL || 'http://127.0.0.1:5000';

export function uniqueEmail(prefix = 'e2e') {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 100000)}@example.com`;
}

export async function registerViaApi(request, email, password = 'E2ePass123!') {
  const response = await request.post(`${apiURL}/auth/register`, {
    data: {
      firstName: 'E2E',
      lastName: 'Operator',
      email,
      password,
    },
  });

  expect([201, 409]).toContain(response.status());
  return { email, password, body: await response.json().catch(() => ({})) };
}

export async function authenticatePage(page, request, email = uniqueEmail('auth-page')) {
  const response = await request.post(`${apiURL}/auth/register`, {
    data: {
      firstName: 'E2E',
      lastName: 'Operator',
      email,
      password: 'E2ePass123!',
    },
  });
  expect(response.status()).toBe(201);
  const body = await response.json();

  await page.context().addInitScript(({ token, user }) => {
    window.localStorage.setItem('token', token);
    window.localStorage.setItem('user', user);
  }, {
    token: body.access_token,
    user: body.user?.username || email,
  });

  return { email, password: 'E2ePass123!' };
}


export async function fillLoginForm(page, email, password) {
  await page.locator('input[type="text"]').fill(email);
  await page.locator('input[type="password"]').fill(password);
  await page.getByRole('button', { name: /ACCES SISTEM/i }).click();
  await expect(page).toHaveURL(/\/dashboard/);
}
