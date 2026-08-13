"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type Phase = "idle" | "loading" | "recalling" | "searching" | "planning" | "approval" | "reserving" | "complete" | "killed";

type TimelineItem = {
  id: string;
  label: string;
  detail: string;
  time: string;
  status: "done" | "active" | "queued" | "warning";
};

type ApiState = "offline" | "connecting" | "connected" | "checkpointed" | "completed" | "fallback";

const apiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");

const phaseOrder: Phase[] = ["loading", "recalling", "searching", "planning", "approval", "reserving", "complete"];

const baseTimeline: TimelineItem[] = [
  { id: "event", label: "Disruption received", detail: "UA 1847 · mechanical cancellation", time: "09:42:01", status: "done" },
  { id: "profile", label: "Passenger memory loaded", detail: "3 preferences · 1 prior recovery", time: "09:42:02", status: "done" },
  { id: "recall", label: "Similar cases recalled", detail: "3 matches via distributed vector search", time: "09:42:03", status: "done" },
  { id: "search", label: "Alternatives searched", detail: "3 viable itineraries from LetsFG", time: "09:42:05", status: "done" },
  { id: "plan", label: "Recovery plan generated", detail: "Preference-aware policy with recalled memory", time: "09:42:07", status: "done" },
  { id: "reserve", label: "Seat held transactionally", detail: "Window seat · idempotency key verified", time: "09:42:09", status: "done" },
];

const flightOptions = [
  {
    id: "BA286",
    airline: "British Airways",
    route: "SFO 13:15  →  LHR 07:40+1",
    duration: "10h 25m · nonstop",
    price: "+$184",
    reliability: "91%",
    tags: ["No red-eye departure", "Window available", "Meeting protected"],
    score: 96,
    badge: "Best memory match",
  },
  {
    id: "UA930",
    airline: "United",
    route: "SFO 19:45  →  LHR 14:10+1",
    duration: "10h 25m · nonstop",
    price: "+$42",
    reliability: "84%",
    tags: ["Red-eye", "Aisle only", "Arrives after meeting"],
    score: 58,
    badge: "Lowest fare",
  },
  {
    id: "AC742",
    airline: "Air Canada",
    route: "SFO 12:05  →  YYZ  →  LHR",
    duration: "14h 35m · 1 stop",
    price: "+$96",
    reliability: "78%",
    tags: ["Tight connection", "Window available", "Weather exposure"],
    score: 73,
    badge: "Backup",
  },
];

const phaseCopy: Record<Phase, { eyebrow: string; title: string; body: string }> = {
  idle: { eyebrow: "DISRUPTION READY", title: "A cancelled flight. A plan that remembers.", body: "Trigger the scenario to watch RouteRecall recover Maya’s journey with durable, preference-aware memory." },
  loading: { eyebrow: "CASE RR-104", title: "Loading the journey state…", body: "The agent is reconstructing the cancelled itinerary and the downstream connection at risk." },
  recalling: { eyebrow: "MEMORY ONLINE", title: "Maya is more than a booking reference.", body: "RouteRecall remembers her window-seat preference, meeting deadline and prior recovery choices." },
  searching: { eyebrow: "LIVE SEARCH", title: "Three viable ways forward.", body: "Flight search results are filtered against hard constraints before the recovery policy ranks the trade-offs." },
  planning: { eyebrow: "MEMORY-AWARE PLANNING", title: "The cheapest answer is not the best answer.", body: "The agent balances price, reliability, arrival time and the recalled memories that matter for this trip." },
  approval: { eyebrow: "HUMAN GATE", title: "Recovery plan ready for approval.", body: "BA286 protects the meeting, avoids Maya’s red-eye departure preference and has a window seat available." },
  reserving: { eyebrow: "SERIALIZABLE COMMIT", title: "Holding the last matching seat…", body: "CockroachDB is committing inventory and the action ledger atomically with an idempotency key." },
  complete: { eyebrow: "RECOVERY COMPLETE", title: "Maya will make the meeting.", body: "The action is durable, auditable and ready to resume without duplication if the agent is restarted." },
  killed: { eyebrow: "WORKER TERMINATED", title: "The agent stopped. Its memory did not.", body: "The latest checkpoint is safe in CockroachDB. A fresh worker will resume without repeating completed actions." },
};

function statusForStep(stepIndex: number, currentIndex: number, killed: boolean): TimelineItem["status"] {
  if (killed && stepIndex === currentIndex) return "warning";
  if (stepIndex < currentIndex) return "done";
  if (stepIndex === currentIndex) return "active";
  return "queued";
}

export default function Home() {
  const [phase, setPhase] = useState<Phase>("idle");
  const [phaseIndex, setPhaseIndex] = useState(-1);
  const [memoryOn, setMemoryOn] = useState(true);
  const [raceOpen, setRaceOpen] = useState(false);
  const [raceState, setRaceState] = useState<"ready" | "running" | "done">("ready");
  const [resumeCount, setResumeCount] = useState(0);
  const [remoteCaseId, setRemoteCaseId] = useState<string | null>(null);
  const [apiState, setApiState] = useState<ApiState>(apiUrl ? "connecting" : "offline");
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const remoteRunStarted = useRef(false);
  const remoteCrashStarted = useRef(false);

  const clearTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current);
    timerRef.current = null;
  };

  const advance = (index: number) => {
    clearTimer();
    const safeIndex = Math.min(index, phaseOrder.length - 1);
    setPhaseIndex(safeIndex);
    setPhase(phaseOrder[safeIndex]);
    if (safeIndex < phaseOrder.length - 1) {
      timerRef.current = setTimeout(() => advance(safeIndex + 1), safeIndex === 4 ? 1350 : 900);
    }
  };

  useEffect(() => () => clearTimer(), []);

  useEffect(() => {
    if (phase !== "reserving" || !apiUrl || !remoteCaseId || remoteRunStarted.current || remoteCrashStarted.current) return;
    remoteRunStarted.current = true;
    void fetch(`${apiUrl}/v1/cases/${remoteCaseId}/run`, { method: "POST" })
      .then((response) => {
        if (!response.ok) throw new Error(`Recovery API returned ${response.status}`);
        setApiState("completed");
      })
      .catch(() => setApiState("fallback"));
  }, [phase, remoteCaseId]);

  const createRemoteCase = async () => {
    if (!apiUrl) return;
    setApiState("connecting");
    try {
      const response = await fetch(`${apiUrl}/v1/demo/cases?memory_enabled=${memoryOn}`, { method: "POST" });
      if (!response.ok) throw new Error(`Recovery API returned ${response.status}`);
      const payload = (await response.json()) as { id: string };
      setRemoteCaseId(payload.id);
      setApiState("connected");
    } catch {
      setApiState("fallback");
    }
  };

  const trigger = () => {
    setRaceOpen(false);
    setResumeCount(0);
    setRemoteCaseId(null);
    remoteRunStarted.current = false;
    remoteCrashStarted.current = false;
    void createRemoteCase();
    advance(0);
  };

  const killAgent = () => {
    if (phase === "idle" || phase === "killed") return;
    clearTimer();
    const checkpoint = Math.max(phaseIndex, 3);
    setPhaseIndex(checkpoint);
    setPhase("killed");
    if (apiUrl && remoteCaseId && !remoteRunStarted.current) {
      remoteCrashStarted.current = true;
      void fetch(`${apiUrl}/v1/cases/${remoteCaseId}/run?crash_after=WAIT_FOR_APPROVAL`, { method: "POST" })
        .then((response) => {
          if (!response.ok) throw new Error(`Recovery API returned ${response.status}`);
          setApiState("checkpointed");
          return new Promise<void>((resolve) => setTimeout(resolve, 1250));
        })
        .then(() => fetch(`${apiUrl}/v1/cases/${remoteCaseId}/resume`, { method: "POST" }))
        .then((response) => {
          if (!response.ok) throw new Error(`Recovery API returned ${response.status}`);
          setApiState("completed");
          setResumeCount((value) => value + 1);
          advance(Math.min(checkpoint + 1, phaseOrder.length - 1));
        })
        .catch(() => {
          setApiState("fallback");
          timerRef.current = setTimeout(() => advance(Math.min(checkpoint + 1, phaseOrder.length - 1)), 600);
        });
      return;
    }
    timerRef.current = setTimeout(() => {
      setResumeCount((value) => value + 1);
      advance(Math.min(checkpoint + 1, phaseOrder.length - 1));
    }, 1700);
  };

  const runRace = () => {
    setRaceOpen(true);
    setRaceState("running");
    setTimeout(() => setRaceState("done"), 1450);
  };

  const activeStep = Math.max(0, Math.min(phaseIndex, baseTimeline.length - 1));
  const selectedFlight = memoryOn ? flightOptions[0] : flightOptions[1];
  const timeline = useMemo(
    () => baseTimeline.map((item, index) => ({ ...item, status: statusForStep(index, activeStep, phase === "killed") })),
    [activeStep, phase],
  );
  const copy = phaseCopy[phase];
  const progress = phase === "idle" ? 0 : phase === "killed" ? Math.max(18, phaseIndex * 15) : Math.round(((phaseIndex + 1) / phaseOrder.length) * 100);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="RouteRecall home">
          <span className="brand-mark">RR</span>
          <span>RouteRecall</span>
        </a>
        <div className="topbar-meta">
          <span className="live-dot" />
          <span>{apiState === "offline" ? "Interactive local demo" : apiState === "fallback" ? "Demo fallback active" : "CockroachDB API linked"}</span>
          <span className="divider" />
          <span>{apiState === "checkpointed" ? "Checkpoint durable" : apiState === "completed" ? "Cloud run complete" : apiUrl ? "Persistent runtime" : "Cloud-ready"}</span>
        </div>
        <button className="audit-button" type="button" onClick={() => document.getElementById("audit")?.scrollIntoView({ behavior: "smooth" })}>
          Open audit trail <span aria-hidden="true">↗</span>
        </button>
      </header>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow"><span />{copy.eyebrow}</div>
          <h1>{copy.title}</h1>
          <p>{copy.body}</p>
          <div className="hero-actions">
            <button className="primary-button" type="button" onClick={trigger}>
              {phase === "idle" ? "Trigger disruption" : "Restart scenario"}
              <span aria-hidden="true">→</span>
            </button>
            <button className="secondary-button" type="button" onClick={killAgent} disabled={phase === "idle" || phase === "killed"}>
              Kill agent
            </button>
          </div>
        </div>

        <div className="journey-card" aria-label="Disrupted journey">
          <div className="journey-card-head">
            <div>
              <span className="small-label">MAYA CHEN · CASE RR-104</span>
              <strong>San Francisco to London</strong>
            </div>
            <span className="status-pill">RECOVERING</span>
          </div>
          <div className="route-line">
            <div className="airport"><strong>SFO</strong><span>San Francisco</span></div>
            <div className="route-segment cancelled"><span>UA 1847</span><i /><b>Cancelled</b></div>
            <div className="airport muted"><strong>JFK</strong><span>Connection lost</span></div>
            <div className="route-segment at-risk"><span>BA 112</span><i /><b>At risk</b></div>
            <div className="airport"><strong>LHR</strong><span>London</span></div>
          </div>
          <div className="progress-row">
            <span>Recovery progress</span>
            <strong>{progress}%</strong>
          </div>
          <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
          <div className="journey-stats">
            <div><span>Meeting deadline</span><strong>08:30 BST</strong></div>
            <div><span>Eligible offers</span><strong>{phaseIndex >= 2 ? "3 found" : "—"}</strong></div>
            <div><span>Checkpoint</span><strong>{phase === "idle" ? "Not started" : phase === "killed" ? "Preserved" : "Durable"}</strong></div>
          </div>
        </div>
      </section>

      <section className="control-strip" aria-label="Scenario controls">
        <div className="memory-toggle-copy">
          <span className="control-icon">✦</span>
          <div><strong>Persistent memory</strong><span>Compare preference-aware recovery with a stateless agent.</span></div>
        </div>
        <button
          type="button"
          className={`switch ${memoryOn ? "on" : ""}`}
          onClick={() => setMemoryOn((value) => !value)}
          aria-pressed={memoryOn}
          aria-label="Toggle persistent memory"
        >
          <span>{memoryOn ? "ON" : "OFF"}</span><i />
        </button>
        <div className="control-result">
          <span>Selected by agent</span>
          <strong>{selectedFlight.id} · {memoryOn ? "96% memory match" : "lowest fare"}</strong>
        </div>
        <button type="button" className="race-button" onClick={runRace}>Race for last seat <span>↗</span></button>
      </section>

      <section className="workspace-grid">
        <div className="panel timeline-panel">
          <div className="panel-heading">
            <div><span className="small-label">LIVE WORKFLOW</span><h2>Agent action timeline</h2></div>
            <span className={`worker-status ${phase === "killed" ? "error" : ""}`}>
              <i />{phase === "killed" ? "Worker offline" : phase === "idle" ? "Ready" : "Worker active"}
            </span>
          </div>
          <div className="timeline-list">
            {timeline.map((item, index) => (
              <div className={`timeline-item ${item.status}`} key={item.id}>
                <div className="timeline-rail"><span>{item.status === "done" ? "✓" : item.status === "warning" ? "!" : index + 1}</span><i /></div>
                <div className="timeline-content"><strong>{item.label}</strong><span>{item.detail}</span></div>
                <time>{index <= activeStep ? item.time : "—"}</time>
              </div>
            ))}
          </div>
          {resumeCount > 0 && <div className="resume-note"><strong>↻ Recovery verified</strong><span>New worker resumed from checkpoint. Duplicate actions prevented: {resumeCount}</span></div>}
        </div>

        <aside className="panel memory-panel">
          <div className="panel-heading">
            <div><span className="small-label">RECALLED CONTEXT</span><h2>Why this plan fits Maya</h2></div>
            <span className="memory-count">4 memories</span>
          </div>
          <div className="memory-stack">
            <article><span className="memory-type preference">PREFERENCE</span><strong>Avoid red-eye departures</strong><p>“I can handle an overnight arrival, but not an overnight departure.”</p><footer><span>Confidence 0.96</span><span>Updated 18d ago</span></footer></article>
            <article><span className="memory-type constraint">CONSTRAINT</span><strong>Protect the London meeting</strong><p>Arrival before 08:30 BST is more important than minimizing fare difference.</p><footer><span>Importance 1.00</span><span>Trip context</span></footer></article>
            <article><span className="memory-type experience">EXPERIENCE</span><strong>Reliability beat price last time</strong><p>Accepted a +$160 nonstop recovery after a missed connection in March.</p><footer><span>Vector match 0.89</span><span>Case RR-078</span></footer></article>
          </div>
          <div className="vector-proof">
            <div><span>Vector recall</span><strong>3.8 ms</strong></div>
            <div><span>Index</span><strong>C-SPANN</strong></div>
            <div><span>Memory store</span><strong>CockroachDB</strong></div>
          </div>
        </aside>
      </section>

      <section className="options-section">
        <div className="section-heading">
          <div><span className="small-label">RECOVERY OPTIONS</span><h2>Memory changes the recommendation.</h2></div>
          <p>The same search results produce a different decision when the agent knows what matters.</p>
        </div>
        <div className="option-grid">
          {flightOptions.map((flight) => {
            const isSelected = flight.id === selectedFlight.id;
            return (
              <article className={`flight-card ${isSelected ? "selected" : ""}`} key={flight.id}>
                <div className="flight-card-head"><div><span className="flight-number">{flight.id}</span><strong>{flight.airline}</strong></div><span className="offer-badge">{isSelected ? "SELECTED" : flight.badge}</span></div>
                <div className="flight-route"><strong>{flight.route}</strong><span>{flight.duration}</span></div>
                <div className="flight-metrics"><div><span>Fare difference</span><strong>{flight.price}</strong></div><div><span>On-time history</span><strong>{flight.reliability}</strong></div><div><span>Fit score</span><strong>{flight.score}/100</strong></div></div>
                <ul>{flight.tags.map((tag) => <li key={tag}><span>{tag.includes("Red-eye") || tag.includes("Tight") || tag.includes("after") ? "×" : "✓"}</span>{tag}</li>)}</ul>
                <div className="score-track"><span style={{ width: `${flight.score}%` }} /></div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="audit-section" id="audit">
        <div>
          <span className="small-label">MCP AUDIT PROMPT</span>
          <h2>Every decision can explain itself.</h2>
          <p>Ask CockroachDB Managed MCP why the agent selected BA286, which memories influenced it, and whether any action was repeated after restart.</p>
        </div>
        <div className="terminal-card">
          <div className="terminal-head"><span /><span /><span /><b>read-only memory auditor</b></div>
          <code><span>›</span> Explain CASE RR-104 and list the memories that changed the outcome.</code>
          <p><strong>BA286 was selected</strong> because it satisfies 3 high-priority memories: avoid red-eye departures, preserve the 08:30 meeting, and prefer reliability over price during disruption.</p>
          <footer><span>4 memories read</span><span>0 writes permitted</span><span>audit logged</span></footer>
        </div>
      </section>

      {raceOpen && (
        <div className="modal-backdrop" role="dialog" aria-modal="true" aria-labelledby="race-title">
          <div className="race-modal">
            <button className="modal-close" onClick={() => setRaceOpen(false)} aria-label="Close race simulation">×</button>
            <span className="small-label">RELIABILITY LAB</span>
            <h2 id="race-title">Two agents. One window seat.</h2>
            <p>CockroachDB serializable transactions prevent both recovery workers from claiming seat 1A.</p>
            <div className="race-lanes">
              <div className={raceState === "done" ? "winner" : ""}><span>Agent A · Maya</span><strong>{raceState === "ready" ? "Ready" : raceState === "running" ? "Committing…" : "COMMITTED"}</strong><small>{raceState === "done" ? "Seat 1A reserved" : "idempotency: rr104-ba286-1a"}</small></div>
              <div className={raceState === "done" ? "retry" : ""}><span>Agent B · Alex</span><strong>{raceState === "ready" ? "Ready" : raceState === "running" ? "Contending…" : "REPLANNED"}</strong><small>{raceState === "done" ? "Serialization retry → seat 2F" : "idempotency: rr105-ba286-1a"}</small></div>
            </div>
            <div className="race-proof"><span>Seats oversold</span><strong>{raceState === "done" ? "0" : "—"}</strong><span>Duplicate actions</span><strong>{raceState === "done" ? "0" : "—"}</strong></div>
            {raceState === "ready" && <button className="primary-button full" type="button" onClick={runRace}>Run concurrent commit <span>→</span></button>}
          </div>
        </div>
      )}
    </main>
  );
}
