import { expect, test, type Page, type Request } from "@playwright/test";

type Priority = "urgent" | "high" | "standard";

type Recommendation = {
  recommendation_id: string;
  case_id: string;
  recommendation: Priority;
  rationale: string;
  evidence: string[];
  requires_human_review: boolean;
  model: string;
  latency_ms: number;
};

type Decision = {
  case_id: string;
  recommendation_id: string;
  decision_type: "accepted" | "overridden";
  outcome: Priority;
  reason: string;
  reviewer: string;
  recorded_at: string;
};

const CASEWORKER = {
  username: "caseworker",
  password: "local-caseworker-password",
};

const CASE_ID = "case-1027";
const CASE_REFERENCE = /JF-2026-1027/;
const DECISION_REASON =
  "Reviewed the grounded source evidence and accepted the latest priority.";

async function signIn(page: Page) {
  await page.goto("/");
  await page.getByRole("button", { name: "Sign in" }).click();
  await page.getByLabel("Username or email").fill(CASEWORKER.username);
  await page
    .getByLabel("Password", { exact: true })
    .fill(CASEWORKER.password);
  await page.getByRole("button", { name: "Sign In" }).click();

  await expect(page).toHaveURL("http://localhost:3000/");
  await expect(page.getByText("caseworker · AI-assisted")).toBeVisible();
}

async function generateRecommendation(page: Page) {
  const responsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/triage"),
    { timeout: 130_000 },
  );

  await expect(page.getByLabel("Model for recommendation")).toHaveValue(
    "qwen3:4b",
  );
  await page
    .getByRole("button", { name: "Generate AI recommendation" })
    .click();

  const response = await responsePromise;
  expect(response.status()).toBe(200);

  const recommendation = (await response.json()) as Recommendation;
  expect(recommendation.recommendation_id).toBeTruthy();
  expect(recommendation.case_id).toBe(CASE_ID);
  expect(recommendation.requires_human_review).toBe(true);
  expect(recommendation.evidence.length).toBeGreaterThan(0);
  expect(recommendation).not.toHaveProperty("confidence");

  return recommendation;
}

function protectedRequest(request: Request) {
  return (
    request.method() === "POST" &&
    request.url().endsWith("/api/triage")
  );
}

test("@real-model preserves recommendation provenance and decision integrity", async ({
  page,
}) => {
  test.setTimeout(300_000);

  let authorization = "";
  let apiOrigin = "";

  page.on("request", (request) => {
    if (!protectedRequest(request)) return;

    authorization = request.headers().authorization ?? "";
    apiOrigin = new URL(request.url()).origin;
  });

  await signIn(page);
  await page.getByRole("button", { name: CASE_REFERENCE }).click();

  const first = await generateRecommendation(page);
  const second = await generateRecommendation(page);

  expect(first.recommendation_id).not.toBe(second.recommendation_id);
  expect(authorization).toMatch(/^Bearer /);
  expect(apiOrigin).toBeTruthy();

  const headers = {
    authorization,
    "content-type": "application/json",
  };

  const staleResponse = await page.request.post(
    `${apiOrigin}/api/decisions`,
    {
      headers,
      data: {
        case_id: CASE_ID,
        recommendation_id: first.recommendation_id,
        outcome: first.recommendation,
        reason: DECISION_REASON,
      },
    },
  );

  expect(staleResponse.status()).toBe(409);
  await expect(staleResponse.json()).resolves.toEqual({
    detail: "Recommendation is stale. Generate a new recommendation.",
  });

  await page.getByLabel("Decision rationale").fill(DECISION_REASON);

  const createdResponsePromise = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      response.url().endsWith("/api/decisions"),
  );

  await page.getByRole("button", { name: "Record acceptance" }).click();

  const createdResponse = await createdResponsePromise;
  expect(createdResponse.status()).toBe(201);

  const created = (await createdResponse.json()) as Decision;
  expect(created.case_id).toBe(CASE_ID);
  expect(created.recommendation_id).toBe(second.recommendation_id);
  expect(created.decision_type).toBe("accepted");
  expect(created.outcome).toBe(second.recommendation);
  expect(created.reviewer).toBe("Casey Worker");

  await expect(
    page.getByRole("region", { name: "Recorded decision receipt" }),
  ).toContainText(DECISION_REASON);

  const exactReplay = await page.request.post(
    `${apiOrigin}/api/decisions`,
    {
      headers,
      data: {
        case_id: CASE_ID,
        recommendation_id: second.recommendation_id,
        outcome: second.recommendation,
        reason: DECISION_REASON,
      },
    },
  );

  expect(exactReplay.status()).toBe(200);
  await expect(exactReplay.json()).resolves.toEqual(created);

  const conflictingOutcome: Priority =
    second.recommendation === "standard" ? "high" : "standard";
  const conflictingReplay = await page.request.post(
    `${apiOrigin}/api/decisions`,
    {
      headers,
      data: {
        case_id: CASE_ID,
        recommendation_id: second.recommendation_id,
        outcome: conflictingOutcome,
        reason: DECISION_REASON,
      },
    },
  );

  expect(conflictingReplay.status()).toBe(409);
  await expect(conflictingReplay.json()).resolves.toEqual({
    detail: "Recommendation already has a different human decision.",
  });

  await page.reload();
  await page.getByRole("button", { name: CASE_REFERENCE }).click();

  const persistedDecision = page.getByRole("region", {
    name: "Latest human decision",
  });
  await expect(persistedDecision).toBeVisible();
  await expect(persistedDecision).toContainText("Casey Worker");
  await expect(persistedDecision).toContainText(DECISION_REASON);
  await expect(persistedDecision).toContainText(second.recommendation);

  console.log(`first_recommendation_id=${first.recommendation_id}`);
  console.log(`second_recommendation_id=${second.recommendation_id}`);
  console.log("stale_recommendation_status=409");
  console.log("created_decision_status=201");
  console.log("decision_type=accepted");
  console.log("exact_replay_status=200");
  console.log("conflicting_replay_status=409");
  console.log("decision_survives_refresh=true");
});
