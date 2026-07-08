import { test, expect } from '@playwright/test';
import { authenticatePage } from './helpers.js';

test('detection page opens and mode dropdown works without covering the sidebar content', async ({ page, request }) => {
  await authenticatePage(page, request);

  await page.goto('/detection');
  await expect(page.getByText(/Processing Mode|Mod procesare/i)).toBeVisible();

  const modeButton = page.locator('button[aria-haspopup="listbox"]').first();
  await modeButton.click();

  const listbox = page.getByRole('listbox');
  await expect(listbox).toBeVisible();
  await expect(listbox.getByRole('option')).toHaveCount(3);

  await listbox.getByRole('option').nth(1).click();
  await expect(listbox).toBeHidden();
  await expect(page.getByText(/Heatmap|opacitate|opacity/i)).toBeVisible();
});
