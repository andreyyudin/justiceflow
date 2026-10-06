import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

const CASEWORKER = {
  username: "caseworker",
  password: "local-caseworker-password",
  displayName: "Casey Worker",
};

const AUDITOR = {
  username: "auditor",
  password: "local-auditor-password",
  displayName: "Avery Auditor",
};

async function expectNoAccessibilityViolations(page: Page) {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();

  expect(results.violations).toEqual([]);
}

async function signIn(
  page: Page,
  credentials: {
    username: string;
    password: string;
    displayName: string;
  },
) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page).toHaveURL(/\/realms\/justiceflow\/protocol\/openid-connect\/auth/);
  await page.getByLabel("Username or email").fill(credentials.username);
  await page.getByLabel("Password", { exact: true }).fill(credentials.password);
  await page.getByRole("button", { name: "Sign In" }).click();

  await expect(page).toHaveURL("http://localhost:3000/");
  await expect(
    page.getByText(credentials.displayName, { exact: true }),
  ).toBeVisible();
}

test("unauthenticated sign-in page has no detected WCAG A or AA violations", async ({
  page,
}) => {
  await page.goto("/");

  await expect(
    page.getByRole("heading", { name: "Sign in to JusticeFlow" }),
  ).toBeVisible();
  await expectNoAccessibilityViolations(page);
});

test("caseworker completes real OIDC PKCE login and can access triage controls", async ({
  page,
}) => {
  await signIn(page, CASEWORKER);

  await expect(
    page.getByRole("heading", { name: "Triage review queue" }),
  ).toBeVisible();
  await expect(page.getByText("caseworker · Local AI")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Generate AI recommendation" }),
  ).toBeEnabled();
  await expectNoAccessibilityViolations(page);
});

test("auditor completes real OIDC login and is restricted to read-only access", async ({
  page,
}) => {
  await signIn(page, AUDITOR);

  await expect(page.getByText("auditor · Local AI")).toBeVisible();
  const readOnlyButton = page.getByRole("button", {
    name: "Auditor access is read-only",
  });
  await expect(readOnlyButton).toBeDisabled();
  await expectNoAccessibilityViolations(page);
});

test("authenticated user can sign out through the OIDC provider", async ({
  page,
}) => {
  await signIn(page, CASEWORKER);

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(
    page.getByRole("heading", { name: "Sign in to JusticeFlow" }),
  ).toBeVisible();
});
