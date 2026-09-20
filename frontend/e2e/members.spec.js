import { test, expect } from "@playwright/test";
import path from "node:path";
import fs from "node:fs";
import { fileURLToPath } from "node:url";

const owner = "browser-owner-token-" + "x".repeat(32);
const otherOwner = "browser-other-company-token-" + "y".repeat(32);
const sample = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../samples/Meridian_Works_Handbook.pdf");

async function unlock(page, token) {
  await page.goto("/");
  await page.getByLabel("Workspace access token").fill(token);
  await page.getByRole("button", { name: "Open workspace" }).click();
  await expect(page.getByRole("heading", { name: "Company knowledge", exact: true })).toBeVisible();
}

test("owner issues employee access, scoped sources, and revocation locks the employee", async ({ page, browser, baseURL }) => {
  await unlock(page, owner);
  await page.getByLabel("Upload a PDF").setInputFiles(sample);
  await expect(page.getByRole("status")).toContainText("ready for questions");
  await page.getByRole("button", { name: "Manage member access" }).click();
  await page.getByLabel("Member name").fill("Synthetic employee");
  await page.getByRole("button", { name: "Create 30-day access" }).click();
  const credential = page.getByLabel("New member token");
  await expect(credential).toHaveAttribute("type", "password");
  const employeeToken = await credential.inputValue();
  const employeeContext = await browser.newContext({ baseURL, viewport: { width: 390, height: 844 } });
  const employee = await employeeContext.newPage();
  await unlock(employee, employeeToken);
  await expect(employee.getByRole("button", { name: "Upload PDF", exact: true })).toHaveCount(0);
  await expect(employee.getByLabel("Upload a PDF")).toHaveCount(0);
  await expect(employee.getByRole("button", { name: "Manage member access" })).toHaveCount(0);
  await expect(employee.locator(".remove-button")).toHaveCount(0);
  await employee.getByLabel("Company question").fill("How many casual leave days do employees receive?");
  await employee.getByRole("button", { name: "Ask question" }).click();
  await expect(employee.locator(".answer-text")).toContainText("12 casual leave days");
  await expect(employee.locator(".source")).toContainText("Page 1");
  const download = employee.waitForEvent("download");
  await employee.getByRole("button", { name: "Download source PDF" }).click();
  expect((await download).suggestedFilename()).toBe("Meridian_Works_Handbook.pdf");
  expect(await employee.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await employee.screenshot({ path: "test-results/employee-mobile.png", fullPage: true });
  await page.screenshot({ path: "test-results/owner-members.png", fullPage: true });
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Revoke Synthetic employee", exact: true }).click();
  await expect(page.locator(".members-panel").getByRole("status")).toContainText("Access revoked");
  await employee.getByRole("button", { name: "Ask question" }).click();
  await expect(employee.getByLabel("Workspace access token")).toBeVisible();
  await expect(employee.getByRole("alert")).toContainText("expired or was revoked");
  await expect(employee.locator(".source")).toHaveCount(0);
  await employeeContext.close();
  await page.getByRole("button", { name: "Close member access" }).click();
  await expect(page.getByLabel("New member token")).toHaveCount(0);
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Remove Meridian_Works_Handbook.pdf" }).click();
  await expect(page.locator(".document")).toHaveCount(0);
});

test("a second company starts empty and cannot read the first company's PDF", async ({ page, request }) => {
  const seeded = await request.post("/api/upload", {
    headers: { "X-ClarityOps-Token": owner },
    multipart: { file: { name: path.basename(sample), mimeType: "application/pdf", buffer: fs.readFileSync(sample) } },
  });
  expect([200, 201]).toContain(seeded.status());
  const first = await request.get("/api/documents", { headers: { "X-ClarityOps-Token": owner } });
  const document = (await first.json()).documents[0];
  expect(document).toBeTruthy();
  await unlock(page, otherOwner);
  await expect(page.locator(".eyebrow")).toContainText("Other Company");
  await expect(page.locator(".document")).toHaveCount(0);
  const denied = await request.get(`/api/documents/${document.id}/file`, { headers: { "X-ClarityOps-Token": otherOwner } });
  expect(denied.status()).toBe(404);
  await page.getByLabel("Upload a PDF").setInputFiles(sample);
  await expect(page.getByRole("status")).toContainText("ready for questions");
  const second = await request.get("/api/documents", { headers: { "X-ClarityOps-Token": otherOwner } });
  expect((await second.json()).documents[0].id).not.toBe(document.id);
});

test("a delayed answer from a locked session cannot appear in another company", async ({ page, request }) => {
  const issued = await request.post("/api/members", {
    headers: { "X-ClarityOps-Token": owner },
    data: { name: "Synthetic session owner", role: "owner" },
  });
  expect(issued.status()).toBe(201);
  const member = await issued.json();
  const seeded = await request.post("/api/upload", {
    headers: { "X-ClarityOps-Token": owner },
    multipart: { file: { name: path.basename(sample), mimeType: "application/pdf", buffer: fs.readFileSync(sample) } },
  });
  expect([200, 201]).toContain(seeded.status());

  let releaseAnswer;
  let captureAnswer;
  const held = new Promise((resolve) => { releaseAnswer = resolve; });
  const captured = new Promise((resolve) => { captureAnswer = resolve; });
  await page.route("**/api/ask", async (route) => {
    const response = await route.fetch();
    expect(response.status()).toBe(200);
    captureAnswer();
    await held; // A valid response can be delayed in transit after authorization.
    await route.fulfill({ response });
  });
  await unlock(page, member.access_token);
  await page.getByLabel("Company question").fill("How many casual leave days do employees receive?");
  await page.getByRole("button", { name: "Ask question" }).click();
  await captured;
  try {
    const revoked = await request.delete(`/api/members/${member.member.id}`, {
      headers: { "X-ClarityOps-Token": owner },
    });
    expect(revoked.status()).toBe(204);
    await page.getByRole("button", { name: "Manage member access" }).click();
    await expect(page.getByLabel("Workspace access token")).toBeVisible();
    // Unlock without a page reload, while the old answer is still in flight.
    await page.getByLabel("Workspace access token").fill(otherOwner);
    await page.getByRole("button", { name: "Open workspace" }).click();
    await expect(page.locator(".eyebrow")).toContainText("Other Company");
    const arrived = page.waitForResponse("**/api/ask");
    releaseAnswer();
    await (await arrived).finished();
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await expect(page.locator(".answer-text")).toHaveCount(0);
    await expect(page.locator(".source")).toHaveCount(0);
    await expect(page.locator(".eyebrow")).toContainText("Other Company");
  } finally {
    releaseAnswer();
  }
});
