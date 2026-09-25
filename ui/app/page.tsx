"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this case is not queued for review.",
  off: "Review routing is off in this deployment; this case is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// Questions the local profile answers against its fictional warehouse, one per outcome the service
// can produce: a certified answer, a conditionally certified answer that escalates and is routed
// for review, and a refusal naming the certified metrics to ask instead. The service exposes no
// question list, so these are the eval set's own cases (eval/datasets/golden_cases.jsonl).
const EXAMPLE_QUESTIONS = [
  "What was total revenue by region?",
  "How many active customers by segment?",
  "Show me profit margin by region",
];

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [question, setQuestion] = useState(EXAMPLE_QUESTIONS[0]);
  const [result, setResult] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed(false);
    try {
      // The question is the whole of `AskRequest`: the tenant that scopes the rows comes from the
      // resolved principal, never from this body.
      const response = await fetch(API + "/v1/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Dev-Persona": persona },
        body: JSON.stringify({ question: question }),
      });
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Ask a governed question. The SQL is composed from the certified semantic layer, the answer is cited, and an escalation is routed to a human reviewer."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The question</legend>
          <label>
            Example question
            <select
              value={EXAMPLE_QUESTIONS.includes(question) ? question : ""}
              onChange={(event) => setQuestion(event.target.value)}
            >
              <option value="" disabled>
                Your own question
              </option>
              {EXAMPLE_QUESTIONS.map((example) => (
                <option key={example} value={example}>
                  {example}
                </option>
              ))}
            </select>
          </label>
          <label>
            Question
            <textarea value={question} onChange={(event) => setQuestion(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || !question.trim()}>
            {busy ? "Working" : "Ask this question"}
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
