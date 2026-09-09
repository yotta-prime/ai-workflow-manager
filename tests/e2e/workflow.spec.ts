/**
 * Document Reference: tests/e2e/workflow.spec.ts
 * System: Enterprise AI Workflow Manager
 * Branch: A.14.12
 * Description: Automated end-to-end user path and accessibility tests.
 */

import { test, expect } from '@playwright/test';
const { AxeBuilder } = require('@axe-core/playwright');

test.describe('Enterprise AI Workflow Manager E2E Suites', () => {

  // ==========================================
  // CLIENT INJECTIONS (TC-FE-VAL-001)
  // ==========================================
  test('should render escaped sanitizations on user console inputs', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const input = page.locator('input[placeholder="Enter a task..."]');
    const submitBtn = page.locator('button:has-text("Run")');

    const maliciousInput = '<script>alert("XSS")</script>**Strong text**';
    await input.fill(maliciousInput);
    await submitBtn.click();

    const rawScript = page.locator('script');
    await expect(rawScript).toHaveCount(0);

    const boldText = page.locator('strong');
    await expect(boldText).toBeVisible();
  });

  // ==========================================
  // SYSTEM ACCESSIBILITIES (TC-FE-VAL-002)
  // ==========================================
  test('should pass strict WCAG accessibility regulations', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .analyze();

    expect(results.violations).toEqual([]);
  });

  // ==========================================
  // MOBILE DYNAMIC RESPONSIVENESS (TC-FE-VAL-003)
  // ==========================================
  test('should scale touch target interfaces cleanly on mobile viewports', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await page.goto('http://localhost:3000');

    const submitBtn = page.locator('button:has-text("Run")');
    await expect(submitBtn).toBeVisible();

    const boundingBox = await submitBtn.boundingBox();
    expect(boundingBox).not.toBeNull();
    if (boundingBox) {
      expect(boundingBox.width).toBeGreaterThanOrEqual(44);
      expect(boundingBox.height).toBeGreaterThanOrEqual(44);
    }
  });
});
