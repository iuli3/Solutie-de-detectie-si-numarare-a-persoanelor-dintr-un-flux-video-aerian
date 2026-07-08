import { test, expect } from '@playwright/test';
import path from 'node:path';
import { authenticatePage } from './helpers.js';

test('upload video reaches the real processing flow when E2E_VIDEO_PATH is set', async ({ page, request }) => {
  test.setTimeout(180_000);
  const videoPath = process.env.E2E_VIDEO_PATH;
  test.skip(!videoPath, 'Set E2E_VIDEO_PATH=/path/to/small-video.mp4 to run the real cluster upload E2E test.');

  await authenticatePage(page, request);

  await page.goto('/detection');

  const uploadResponsePromise = page.waitForResponse(
    response => response.url().includes('/upload') && response.request().method() === 'POST',
    { timeout: 160_000 }
  );

  await page.locator('input[type="file"]').setInputFiles(path.resolve(videoPath));
  await expect(page.getByText(/Uploading video to GPU Cluster|Se incarca|Se încarcă/i).first()).toBeVisible({ timeout: 10_000 });

  const uploadResponse = await uploadResponsePromise;
  expect(uploadResponse.status()).toBe(201);

  await expect(page.getByText(/processing|proces|gpu cluster|complete|finalizat/i).first()).toBeVisible({ timeout: 30_000 });
});
