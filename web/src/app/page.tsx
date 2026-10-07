"use client";

import { type User, type UserManager } from "oidc-client-ts";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  bearerHeaders,
  createUserManager,
  loadAuthenticatedUser,
} from "./oidc";

type Priority = "urgent" | "high" | "standard";
type CaseStatus = "needs_review" | "approved" | "escalated";
type Role = "caseworker" | "auditor";

type Identity = {
  subject: string;
  display_name: string;
  role: Role;
};

type LatestDecision = {
  outcome: Priority;
  reason: string;
  reviewer: string;
  recorded_at: string;
};

type Case = {
  id: string;
  reference: string;
  service: string;
  region: string;
  summary: string;
  received_at: string;
  priority: Priority;
  status: CaseStatus;
  risk_flags: string[];
  days_waiting: number;
  latest_decision: LatestDecision | null;
};

type TriageResult = {
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
  recommendation_id: string | null;
  decision_type: "accepted" | "overridden" | "legacy";
  outcome: Priority;
  reason: string;
  reviewer: string;
  recorded_at: string;
};

type ObservabilityStatus = {
  structured_logs: boolean;
  langfuse_enabled: boolean;
  environment: string;
  release: string;
};

type DecisionAuditEntry = {
  case_id: string;
  recommendation_id: string | null;
  decision_type: "accepted" | "overridden" | "legacy";
  outcome: Priority;
  reason: string;
  reviewer: string;
  recorded_at: string;
  advisory_priority: Priority | null;
  advisory_rationale: string | null;
  advisory_evidence: string[];
  model: string | null;
  recommendation_created_at: string | null;
};

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function priorityStyle(priority: Priority) {
  return {
    urgent: "bg-red-50 text-red-800 border-red-200",
    high: "bg-amber-50 text-amber-800 border-amber-200",
    standard: "bg-sky-50 text-sky-800 border-sky-200",
  }[priority];
}

export default function Home() {
  const userManager = useRef<UserManager | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [identity, setIdentity] = useState<Identity | null>(null);
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("");
  const [triage, setTriage] = useState<TriageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [decisionLoading, setDecisionLoading] = useState(false);
  const [finalPriority, setFinalPriority] = useState<Priority>("standard");
  const [decisionReason, setDecisionReason] = useState("");
  const [recordedDecision, setRecordedDecision] = useState<Decision | null>(null);
  const [observability, setObservability] = useState<ObservabilityStatus | null>(
    null,
  );
  const [decisionHistory, setDecisionHistory] = useState<DecisionAuditEntry[]>([]);
  const [message, setMessage] = useState("");
  const [messageKind, setMessageKind] = useState<"success" | "error">("success");

  useEffect(() => {
    const manager = createUserManager();
    userManager.current = manager;

    loadAuthenticatedUser(manager)
      .then(async (authenticatedUser) => {
        if (!authenticatedUser || authenticatedUser.expired) {
          setLoading(false);
          return;
        }

        setUser(authenticatedUser);
        const headers = bearerHeaders(authenticatedUser.access_token);
        const [identityResponse, casesResponse] = await Promise.all([
          fetch(`${API_URL}/api/identity`, { headers }),
          fetch(`${API_URL}/api/cases`, { headers }),
        ]);
        if (!identityResponse.ok || !casesResponse.ok) {
          throw new Error("Authenticated API request failed");
        }

        const currentIdentity = (await identityResponse.json()) as Identity;
        const queue = (await casesResponse.json()) as Case[];
        setIdentity(currentIdentity);
        setCases(queue);
        setSelectedId(queue[0]?.id ?? "");

        if (currentIdentity.role === "caseworker") {
          const modelsResponse = await fetch(`${API_URL}/api/models`, { headers });
          if (!modelsResponse.ok) {
            throw new Error("AI model inventory request failed");
          }
          const availableModels = (await modelsResponse.json()) as string[];
          setModels(availableModels);
          setSelectedModel(availableModels[0] ?? "");
        }

        if (currentIdentity.role === "auditor") {
          const [observabilityResponse, historyResponse] = await Promise.all([
            fetch(`${API_URL}/api/observability`, { headers }),
            fetch(`${API_URL}/api/decisions/history`, { headers }),
          ]);
          if (!observabilityResponse.ok || !historyResponse.ok) {
            throw new Error("Auditor data request failed");
          }
          setObservability(
            (await observabilityResponse.json()) as ObservabilityStatus,
          );
          setDecisionHistory(
            (await historyResponse.json()) as DecisionAuditEntry[],
          );
        }
      })
      .catch((error: unknown) => {
        setMessageKind("error");
        setMessage(
          error instanceof Error
            ? error.message
            : "Authentication failed.",
        );
      })
      .finally(() => setLoading(false));
  }, []);

  async function signIn() {
    await userManager.current?.signinRedirect();
  }

  async function signOut() {
    await userManager.current?.signoutRedirect();
  }

  const selected = useMemo(
    () => cases.find((item) => item.id === selectedId),
    [cases, selectedId],
  );

  async function runTriage() {
    if (
      !selected ||
      !selectedModel ||
      identity?.role !== "caseworker"
    ) return;
    setAiLoading(true);
    setMessage("");
    setTriage(null);
    setRecordedDecision(null);
    try {
      if (!user) return;
      const response = await fetch(`${API_URL}/api/triage`, {
        method: "POST",
        headers: bearerHeaders(user.access_token, true),
        body: JSON.stringify({
          case_id: selected.id,
          model: selectedModel,
        }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Triage failed");
      const result = body as TriageResult;
      setTriage(result);
      setFinalPriority(result.recommendation);
      setDecisionReason("");
    } catch (error) {
      setMessageKind("error");
      setMessage(error instanceof Error ? error.message : "Triage failed");
    } finally {
      setAiLoading(false);
    }
  }

  async function recordDecision() {
    if (
      !selected ||
      !triage ||
      identity?.role !== "caseworker" ||
      !user ||
      decisionLoading ||
      recordedDecision
    ) {
      return;
    }

    const reason = decisionReason.trim();
    if (reason.length < 10) {
      setMessageKind("error");
      setMessage("Enter at least 10 characters explaining the human decision.");
      return;
    }

    setDecisionLoading(true);
    setMessage("");
    try {
      const response = await fetch(`${API_URL}/api/decisions`, {
        method: "POST",
        headers: bearerHeaders(user.access_token, true),
        body: JSON.stringify({
          case_id: selected.id,
          recommendation_id: triage.recommendation_id,
          outcome: finalPriority,
          reason,
        }),
      });
      const body = await response.json();
      if (!response.ok) {
        throw new Error(body.detail ?? "Decision could not be recorded.");
      }

      const decision = body as Decision;
      setRecordedDecision(decision);
      setCases((currentCases) =>
        currentCases.map((item) =>
          item.id === decision.case_id
            ? {
              ...item,
              priority: decision.outcome,
              status: "approved",
              latest_decision: {
                outcome: decision.outcome,
                reason: decision.reason,
                reviewer: decision.reviewer,
                recorded_at: decision.recorded_at,
              },
            }
            : item,
        ),
      );
      setMessageKind("success");
      setMessage(
        finalPriority === triage.recommendation
          ? "Human decision recorded. The advisory recommendation was accepted."
          : "Human decision recorded. The advisory recommendation was overridden.",
      );
    } catch (error) {
      setMessageKind("error");
      setMessage(
        error instanceof Error
          ? error.message
          : "Decision could not be recorded.",
      );
    } finally {
      setDecisionLoading(false);
    }
  }

  if (!loading && !identity) {
    return (
      <main className="grid min-h-screen place-items-center bg-[#f3f4f0] px-6 text-[#18201c]">
        <section className="w-full max-w-md rounded-lg border border-[#cbd1c8] bg-white p-8 shadow-sm">
          <div className="mb-6 grid size-12 place-items-center bg-[#d2e65b] font-bold text-[#17251d]">
            JF
          </div>
          <h1 className="text-2xl font-semibold">Sign in to JusticeFlow</h1>
          <p className="mt-3 text-sm leading-6 text-[#5f6962]">
            Use the same OpenID Connect and role-based access flow locally and
            in deployed environments.
          </p>
          <button
            onClick={signIn}
            className="mt-6 w-full rounded-md bg-[#253e2e] px-4 py-3 text-sm font-semibold text-white hover:bg-[#1c3023]"
          >
            Sign in
          </button>
          {message && (
            <p role="alert" className="mt-4 rounded-md bg-red-50 p-3 text-sm text-red-800">
              {message}
            </p>
          )}
        </section>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-[#f3f4f0] text-[#18201c]">
      <header className="border-b border-[#cfd5cc] bg-[#17251d] text-white">
        <div className="mx-auto flex max-w-[1500px] items-center justify-between px-6 py-4">
          <div className="flex items-center gap-4">
            <div className="grid size-10 place-items-center bg-[#d2e65b] font-bold text-[#17251d]">
              JF
            </div>
            <div>
              <p className="text-lg font-semibold">JusticeFlow</p>
              <p className="text-xs text-[#c8d3cc]">Casework operations workspace</p>
            </div>
          </div>
          <div className="flex items-center gap-4 text-right text-sm">
            <div>
              <p className="font-semibold">
                {identity?.display_name ?? "Loading identity…"}
              </p>
              <p className="text-xs capitalize text-[#c8d3cc]">
                {identity?.role ?? "unknown"} · AI-assisted
              </p>
            </div>
            {identity && (
              <button
                onClick={signOut}
                className="rounded border border-[#708078] px-3 py-1.5 text-xs font-semibold hover:bg-[#25382d]"
              >
                Sign out
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="mx-auto max-w-[1500px] px-6 py-7">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="mb-2 text-xs font-semibold uppercase tracking-[0.18em] text-[#58645d]">
              Operational overview
            </p>
            <h1 className="text-3xl font-semibold tracking-tight">Triage review queue</h1>
            <p className="mt-2 max-w-2xl text-sm text-[#5f6962]">
              Prioritise synthetic casework with explainable AI recommendations. Every
              recommendation requires a named human decision.
            </p>
          </div>
          <div className="rounded-md border border-[#cbd1c8] bg-white px-4 py-3 text-sm shadow-sm">
            <span className="font-semibold">{cases.length}</span> open cases
            <span className="mx-3 text-[#b1b8b2]">|</span>
            <span className="font-semibold text-red-700">
              {cases.filter((item) => item.priority === "urgent").length}
            </span>{" "}
            urgent
          </div>
        </div>

        {identity?.role === "auditor" && observability && (
          <section
            aria-labelledby="operational-observability-heading"
            className="mb-5 rounded-lg border border-[#cbd1c8] bg-white p-5 shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#69756d]">
                  Restricted operational view
                </p>
                <h2
                  id="operational-observability-heading"
                  className="mt-1 text-lg font-semibold"
                >
                  AI service observability
                </h2>
                <p className="mt-2 max-w-3xl text-sm leading-6 text-[#58645d]">
                  Runtime status belongs outside the caseworker decision flow.
                  Detailed traces are reviewed in the configured observability
                  platform and correlated through request IDs in structured logs.
                </p>
              </div>
              <span className="rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold text-sky-800">
                Auditor access
              </span>
            </div>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
              <div className="rounded-md bg-[#f3f5f1] p-3">
                <dt className="text-xs font-semibold uppercase text-[#58645d]">
                  Structured logs
                </dt>
                <dd className="mt-1 font-semibold">
                  {observability.structured_logs ? "Enabled" : "Unavailable"}
                </dd>
              </div>
              <div className="rounded-md bg-[#f3f5f1] p-3">
                <dt className="text-xs font-semibold uppercase text-[#58645d]">
                  Trace export
                </dt>
                <dd className="mt-1 font-semibold">
                  {observability.langfuse_enabled
                    ? `Langfuse enabled · ${observability.environment}`
                    : "Langfuse not configured"}
                </dd>
              </div>
              <div className="rounded-md bg-[#f3f5f1] p-3">
                <dt className="text-xs font-semibold uppercase text-[#58645d]">
                  Release
                </dt>
                <dd className="mt-1 font-semibold">
                  {observability.release}
                </dd>
              </div>
            </dl>
            <p className="mt-4 text-xs leading-5 text-[#69756d]">
              Prompts, case summaries, rationales, and evidence are deliberately
              excluded from exported telemetry.
            </p>
          </section>
        )}

        {identity?.role === "auditor" && (
          <section
            aria-labelledby="decision-history-heading"
            className="mb-5 overflow-hidden rounded-lg border border-[#cbd1c8] bg-white shadow-sm"
          >
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[#dbe0d8] px-5 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#69756d]">
                  Append-only audit trail
                </p>
                <h2
                  id="decision-history-heading"
                  className="mt-1 text-lg font-semibold"
                >
                  Decision history
                </h2>
                <p className="mt-2 text-sm leading-6 text-[#58645d]">
                  Human outcomes appear newest first. Linked records preserve the
                  advisory recommendation reviewed by the caseworker.
                </p>
              </div>
              <span className="rounded-full border border-[#cbd1c8] bg-[#f3f5f1] px-3 py-1 text-xs font-semibold">
                {decisionHistory.length} records
              </span>
            </div>
            {decisionHistory.length ? (
              <ol className="divide-y divide-[#e3e6e1]">
                {decisionHistory.map((entry, index) => (
                  <li
                    key={`${entry.case_id}-${entry.recorded_at}-${index}`}
                    className="grid gap-4 px-5 py-4 lg:grid-cols-[0.8fr_1.2fr]"
                  >
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold">
                          {entry.case_id}
                        </span>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase ${priorityStyle(entry.outcome)}`}
                        >
                          {entry.outcome}
                        </span>
                        <span className="rounded-full border border-[#cbd1c8] bg-[#f3f5f1] px-2 py-0.5 text-[11px] font-semibold uppercase text-[#48534c]">
                          {entry.decision_type}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-[#58645d]">
                        {entry.reviewer} ·{" "}
                        {new Date(entry.recorded_at).toLocaleString()}
                      </p>
                      <p className="mt-2 text-sm leading-6">{entry.reason}</p>
                    </div>
                    <div className="rounded-md bg-[#f7f8f5] p-3 text-xs">
                      {entry.recommendation_id ? (
                        <>
                          <p className="font-semibold text-[#253e2e]">
                            Reviewed recommendation
                          </p>
                          <p className="mt-1 leading-5">
                            {entry.advisory_priority} · {entry.model}
                          </p>
                          <p className="mt-2 leading-5">
                            {entry.advisory_rationale}
                          </p>
                          <ul className="mt-2 list-disc space-y-1 pl-5 text-[#58645d]">
                            {entry.advisory_evidence.map((evidence) => (
                              <li key={evidence}>{evidence}</li>
                            ))}
                          </ul>
                        </>
                      ) : (
                        <>
                          <p className="font-semibold text-[#48534c]">
                            Legacy decision
                          </p>
                          <p className="mt-1 leading-5 text-[#58645d]">
                            Recorded before recommendation provenance was
                            introduced.
                          </p>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="px-5 py-6 text-sm text-[#68736c]">
                No human decisions have been recorded.
              </p>
            )}
          </section>
        )}

        <section className="grid gap-5 lg:grid-cols-[1.4fr_0.9fr]">
          <div className="overflow-hidden rounded-lg border border-[#cbd1c8] bg-white shadow-sm">
            <div className="flex items-center justify-between border-b border-[#dbe0d8] px-5 py-4">
              <h2 className="font-semibold">Cases requiring review</h2>
              <span className="text-xs text-[#68736c]">Synthetic demonstration data</span>
            </div>
            {loading ? (
              <p className="p-6 text-sm text-[#68736c]">Loading casework…</p>
            ) : (
              <div className="divide-y divide-[#e3e6e1]">
                {cases.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      setSelectedId(item.id);
                      setTriage(null);
                      setRecordedDecision(null);
                      setDecisionReason("");
                      setMessage("");
                    }}
                    className={`grid w-full grid-cols-[1fr_auto] gap-4 px-5 py-4 text-left transition ${selectedId === item.id ? "bg-[#f4f7df]" : "hover:bg-[#f7f8f5]"
                      }`}
                  >
                    <div>
                      <div className="mb-2 flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold">{item.reference}</span>
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase ${priorityStyle(item.priority)}`}
                        >
                          {item.priority}
                        </span>
                        {item.latest_decision && (
                          <span className="rounded-full border border-emerald-300 bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold uppercase text-emerald-800">
                            Human reviewed
                          </span>
                        )}
                      </div>
                      <p className="line-clamp-2 text-sm leading-6 text-[#39433d]">
                        {item.summary}
                      </p>
                      <p className="mt-2 text-xs text-[#58645d]">
                        {item.service} · {item.region}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-semibold">{item.days_waiting}</p>
                      <p className="text-[11px] uppercase tracking-wide text-[#58645d]">
                        days waiting
                      </p>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>

          <aside className="rounded-lg border border-[#cbd1c8] bg-white shadow-sm">
            <div className="border-b border-[#dbe0d8] px-5 py-4">
              <p className="text-xs font-semibold uppercase tracking-[0.15em] text-[#69756d]">
                Human review
              </p>
              <h2 className="mt-1 text-lg font-semibold">
                {selected?.reference ?? "Select a case"}
              </h2>
            </div>
            {selected && (
              <div className="space-y-5 p-5">
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase text-[#69756d]">
                    Source summary
                  </p>
                  <p className="text-sm leading-6">{selected.summary}</p>
                </div>

                {selected.latest_decision && (
                  <section
                    aria-label="Latest human decision"
                    className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-950"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-semibold">Latest human decision</p>
                      <span
                        className={`rounded-full border px-2 py-0.5 text-[11px] font-semibold uppercase ${priorityStyle(selected.latest_decision.outcome)}`}
                      >
                        {selected.latest_decision.outcome}
                      </span>
                    </div>
                    <p className="mt-2">
                      {selected.latest_decision.reviewer} recorded this decision at{" "}
                      {new Date(
                        selected.latest_decision.recorded_at,
                      ).toLocaleString()}.
                    </p>
                    <p className="mt-1 leading-5">
                      {selected.latest_decision.reason}
                    </p>
                  </section>
                )}

                <div className="flex flex-wrap gap-2">
                  {selected.risk_flags.length ? (
                    selected.risk_flags.map((flag) => (
                      <span
                        key={flag}
                        className="rounded bg-[#edf0eb] px-2 py-1 text-xs text-[#48534c]"
                      >
                        {flag.replaceAll("_", " ")}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-[#69756d]">No rule-based flags</span>
                  )}
                </div>
                {identity?.role === "caseworker" && (
                  <div>
                    <label
                      htmlFor="recommendation-model"
                      className="mb-2 block text-xs font-semibold uppercase text-[#69756d]"
                    >
                      Model for recommendation
                    </label>
                    <select
                      id="recommendation-model"
                      value={selectedModel}
                      onChange={(event) => {
                        setSelectedModel(event.target.value);
                        setTriage(null);
                        setRecordedDecision(null);
                        setDecisionReason("");
                        setMessage("");
                      }}
                      disabled={aiLoading || models.length === 0}
                      className="w-full rounded-md border border-[#aeb8b0] bg-white px-3 py-2 text-sm text-[#253e2e] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {models.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                    <p className="mt-2 text-xs leading-5 text-[#69756d]">
                      Only models approved for the configured AI provider are
                      shown.
                    </p>
                  </div>
                )}
                <button
                  onClick={runTriage}
                  disabled={
                    aiLoading ||
                    identity?.role !== "caseworker" ||
                    !selectedModel
                  }
                  className="w-full rounded-md bg-[#253e2e] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1c3023] disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {identity?.role === "auditor"
                    ? "Auditor access is read-only"
                    : aiLoading
                      ? "Running AI model…"
                      : "Generate AI recommendation"}
                </button>

                {triage && (
                  <div className="space-y-4 rounded-md border border-[#cfd7af] bg-[#f7f9e9] p-4">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold uppercase tracking-wide">
                        Advisory result
                      </span>
                      <span
                        className={`rounded-full border px-2 py-1 text-xs font-bold uppercase ${priorityStyle(triage.recommendation)}`}
                      >
                        {triage.recommendation}
                      </span>
                    </div>
                    <p className="text-sm leading-6">{triage.rationale}</p>
                    <ul className="list-disc space-y-1 pl-5 text-xs text-[#4e5a52]">
                      {triage.evidence.map((item) => (
                        <li key={item}>{item}</li>
                      ))}
                    </ul>
                    <div className="border-t border-[#dce2bd] pt-3 text-xs text-[#65705f]">
                      <span>{triage.model} · {triage.latency_ms} ms</span>
                    </div>
                    <fieldset
                      disabled={Boolean(recordedDecision) || decisionLoading}
                      className="space-y-3 border-t border-[#dce2bd] pt-4"
                    >
                      <legend className="text-sm font-semibold">
                        Human decision
                      </legend>
                      <p className="text-xs leading-5 text-[#58645d]">
                        Review the evidence, choose the final queue priority, and
                        explain your decision. A different priority records an
                        explicit override of the advisory result.
                      </p>

                      <label
                        className="block text-xs font-semibold"
                        htmlFor="final-priority"
                      >
                        Final priority
                      </label>
                      <select
                        id="final-priority"
                        value={finalPriority}
                        onChange={(event) =>
                          setFinalPriority(event.target.value as Priority)
                        }
                        className="w-full rounded-md border border-[#aeb8af] bg-white px-3 py-2 text-sm"
                      >
                        <option value="urgent">Urgent</option>
                        <option value="high">High</option>
                        <option value="standard">Standard</option>
                      </select>

                      {finalPriority !== triage.recommendation && (
                        <p className="rounded-md bg-amber-50 p-2 text-xs font-semibold text-amber-900">
                          Override: model recommended {triage.recommendation}.
                        </p>
                      )}

                      <label
                        className="block text-xs font-semibold"
                        htmlFor="decision-reason"
                      >
                        Decision rationale
                      </label>
                      <textarea
                        id="decision-reason"
                        value={decisionReason}
                        onChange={(event) => setDecisionReason(event.target.value)}
                        maxLength={500}
                        rows={4}
                        placeholder="Explain what evidence you reviewed and why this is the final priority."
                        className="w-full rounded-md border border-[#aeb8af] bg-white px-3 py-2 text-sm leading-5"
                      />
                      <div className="flex justify-between text-xs text-[#65705f]">
                        <span>Minimum 10 characters</span>
                        <span>{decisionReason.length}/500</span>
                      </div>

                      <button
                        onClick={recordDecision}
                        type="button"
                        disabled={
                          identity?.role !== "caseworker" ||
                          decisionReason.trim().length < 10 ||
                          Boolean(recordedDecision) ||
                          decisionLoading
                        }
                        className="w-full rounded-md border border-[#253e2e] bg-white px-4 py-2 text-sm font-semibold text-[#253e2e] hover:bg-[#f0f4e1] disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        {recordedDecision
                          ? "Decision recorded"
                          : decisionLoading
                            ? "Recording decision…"
                            : finalPriority === triage.recommendation
                              ? "Record acceptance"
                              : "Record override"}
                      </button>
                    </fieldset>

                    {recordedDecision && (
                      <section
                        aria-label="Recorded decision receipt"
                        className="rounded-md border border-emerald-300 bg-emerald-50 p-3 text-xs text-emerald-950"
                      >
                        <p className="font-semibold">Audit receipt</p>
                        <p className="mt-1">
                          {recordedDecision.reviewer} recorded{" "}
                          <strong>{recordedDecision.outcome}</strong> at{" "}
                          {new Date(
                            recordedDecision.recorded_at,
                          ).toLocaleString()}.
                        </p>
                        <p className="mt-1">{recordedDecision.reason}</p>
                      </section>
                    )}
                  </div>
                )}
                {message && (
                  <p
                    role={messageKind === "error" ? "alert" : "status"}
                    className={`rounded-md p-3 text-sm ${messageKind === "error"
                        ? "bg-red-50 text-red-800"
                        : "bg-emerald-50 text-emerald-900"
                      }`}
                  >
                    {message}
                  </p>
                )}

                {triage && (
                  <section className="rounded-md border border-[#d8ddd6] bg-[#f7f8f5] p-3 text-xs text-[#58645d]">
                    <p className="font-semibold text-[#253e2e]">
                      AI-assisted recommendation
                    </p>
                    <p className="mt-1 leading-5">
                      Generated by {triage.model}. This advisory result does not
                      change the case until a named caseworker records a human
                      decision.
                    </p>
                  </section>
                )}

                <div className="border-t border-[#e0e4de] pt-4 text-xs leading-5 text-[#69756d]">
                  The model cannot make legal decisions, infer protected characteristics, or
                  update case priority without human approval.
                </div>
              </div>
            )}
          </aside>
        </section>
      </div>
    </main>
  );
}
