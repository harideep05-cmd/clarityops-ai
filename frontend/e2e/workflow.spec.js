import { test, expect } from "@playwright/test";
import path from "node:path";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";

const token = "browser-test-only-token-" + "x".repeat(32);
const sample = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../samples/Meridian_Works_Handbook.pdf",
);

async function unlock(page) {
  await page.goto("/");
  await page.getByLabel("Workspace access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(
    page.getByRole("heading", { name: "Company knowledge", exact: true }),
  ).toBeVisible();
}

test("upload, real retrieval, test answer, citations, refusal, download, delete", async ({
  page,
}) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await unlock(page);
  await expect(
    page.getByRole("button", { name: "Ask question" }),
  ).toBeDisabled();
  await page.getByLabel("Upload a PDF").setInputFiles(sample);
  await expect(page.getByRole("status")).toContainText("ready for questions");
  await page
    .getByLabel("Company question")
    .fill("How many casual leave days do employees receive?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.locator(".answer-text")).toContainText(
    "12 casual leave days",
  );
  await expect(page.locator(".source")).toContainText("Page 1");
  await expect(page.locator(".source blockquote")).toContainText(
    "Employees receive 12 casual leave days per calendar year.",
  );
  await page.screenshot({
    path: "test-results/knowledge-workflow-desktop.png",
    fullPage: true,
  });
  const downloading = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download source PDF" }).click();
  expect((await downloading).suggestedFilename()).toBe(
    "Meridian_Works_Handbook.pdf",
  );
  await page.getByLabel("Company question").fill("How many casual leave days? Simulate provider outage");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.getByRole("alert")).toContainText("temporarily unavailable");
  await expect(page.getByRole("alert")).toContainText("Reference:");
  await expect(page.locator(".source")).toHaveCount(0);
  await page
    .getByLabel("Company question")
    .fill("What is our parental leave allowance?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await expect(page.locator(".answer-text")).toContainText(
    "couldn't find enough information",
  );
  await expect(page.locator(".source")).toHaveCount(0);
  await page.getByLabel("Upload a PDF").setInputFiles(sample);
  await expect(page.getByRole("status")).toContainText(
    "already in your workspace",
  );
  await expect(page.locator(".document")).toHaveCount(1);
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Remove Meridian_Works_Handbook.pdf" })
    .click();
  await expect(page.locator(".document")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Ask question" }),
  ).toBeDisabled();
  expect(errors).toEqual([]);
});

test("authentication and invalid upload feedback", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Workspace access token").fill("wrong");
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("alert")).toContainText("access token");
  await page.getByLabel("Workspace access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await page
    .getByLabel("Upload a PDF")
    .setInputFiles({
      name: "invalid.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("not a pdf"),
    });
  await expect(page.getByRole("alert")).toContainText("valid PDF signature");
  await page.getByRole("button", { name: "Lock workspace" }).click();
  await expect(page.getByLabel("Workspace access token")).toHaveValue("");
});

test("mobile layout and suggested-question workflow", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await unlock(page);
  await page.getByLabel("Upload a PDF").setInputFiles(sample);
  await expect(page.getByRole("status")).toContainText("ready for questions");
  await page
    .getByRole("button", {
      name: "How many casual leave days do employees receive?",
    })
    .click();
  await page
    .getByRole("button", { name: "Ask question", exact: false })
    .click();
  await expect(page.locator(".answer-text")).toContainText(
    "12 casual leave days",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: "test-results/knowledge-workflow-mobile.png",
    fullPage: true,
  });
  page.once("dialog", (dialog) => dialog.accept());
  await page
    .getByRole("button", { name: "Remove Meridian_Works_Handbook.pdf" })
    .click();
  await expect(page.locator(".document")).toHaveCount(0);
});
