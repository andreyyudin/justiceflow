"use client";

import { useEffect, useMemo, useState } from "react";

type Priority = "urgent" | "high" | "standard";
type CaseStatus = "needs_review" | "approved" | "escalated";

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
};

type TriageResult = {
  case_id: string;
  recommendation: Priority;
  rationale: string;
  evidence: string[];
  confidence: number;
  requires_human_review: boolean;
  model: string;
  latency_ms: number;
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
  const [cases, setCases] = useState<Case[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [triage, setTriage] = useState<TriageResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    fetch(`${API_URL}/api/cases`)
      .then((response) => {
        if (!response.ok) throw new Error("API unavailable");
        return response.json() as Promise<Case[]>;
      })
      .then((data) => {
        setCases(data);
        setSelectedId(data[0]?.id ?? "");
      })
      .catch(() => setMessage("FastAPI is unavailable. Start the API on port 8000."))
      .finally(() => setLoading(false));
  }, []);

  const selected = useMemo(
    () => cases.find((item) => item.id === selectedId),
    [cases, selectedId],
  );

  async function runTriage() {
    if (!selected) return;
    setAiLoading(true);
    setMessage("");
    setTriage(null);
    try {
      const response = await fetch(`${API_URL}/api/triage`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ case_id: selected.id }),
      });
      const body = await response.json();
      if (!response.ok) throw new Error(body.detail ?? "Triage failed");
      setTriage(body);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Triage failed");
    } finally {
      setAiLoading(false);
    }
  }

  async function recordDecision() {
    if (!selected || !triage) return;
    const response = await fetch(`${API_URL}/api/decisions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        case_id: selected.id,
        outcome: triage.recommendation,
        reason: "Reviewed the source evidence and accepted the advisory queue priority.",
        reviewer: "Demo caseworker",
      }),
    });
    if (response.ok) setMessage("Decision recorded with a human audit trail.");
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
          <div className="flex items-center gap-3 text-sm">
            <span className="size-2 rounded-full bg-[#d2e65b]" />
            Local AI · Human controlled
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
                      </div>
                      <p className="line-clamp-2 text-sm leading-6 text-[#39433d]">
                        {item.summary}
                      </p>
                      <p className="mt-2 text-xs text-[#748078]">
                        {item.service} · {item.region}
                      </p>
                    </div>
                    <div className="text-right">
                      <p className="text-2xl font-semibold">{item.days_waiting}</p>
                      <p className="text-[11px] uppercase tracking-wide text-[#748078]">
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
                <button
                  onClick={runTriage}
                  disabled={aiLoading}
                  className="w-full rounded-md bg-[#253e2e] px-4 py-3 text-sm font-semibold text-white transition hover:bg-[#1c3023] disabled:opacity-60"
                >
                  {aiLoading ? "Running local model…" : "Generate AI recommendation"}
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
                    <div className="flex justify-between border-t border-[#dce2bd] pt-3 text-xs text-[#65705f]">
                      <span>{Math.round(triage.confidence * 100)}% model confidence</span>
                      <span>{triage.model} · {triage.latency_ms} ms</span>
                    </div>
                    <button
                      onClick={recordDecision}
                      className="w-full rounded-md border border-[#253e2e] bg-white px-4 py-2 text-sm font-semibold text-[#253e2e] hover:bg-[#f0f4e1]"
                    >
                      Accept after human review
                    </button>
                  </div>
                )}
                {message && (
                  <p role="status" className="rounded-md bg-[#edf0eb] p-3 text-sm">
                    {message}
                  </p>
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
