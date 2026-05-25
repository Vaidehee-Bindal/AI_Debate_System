import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  FileText,
  History,
  Home,
  Info,
  ListChecks,
  Loader2,
  MessageSquare,
  ShieldCheck,
  Square,
  Trophy,
  UserRound,
} from "lucide-react";

// Prefer `VITE_API_URL` (used in .env). Fall back to `VITE_API_BASE` for compatibility.
// Use `API_URL` variable name to match deployment examples.
const API_URL = import.meta.env.VITE_API_URL ?? import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";
const DEVICE_ID_STORAGE_KEY = "ai-debate-system-device-id";

function getOrCreateDeviceId() {
  if (typeof window === "undefined") return "server";
  const existing = window.sessionStorage.getItem(DEVICE_ID_STORAGE_KEY);
  if (existing) return existing;
  const deviceId = typeof crypto !== "undefined" && typeof crypto.randomUUID === "function" ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  window.sessionStorage.setItem(DEVICE_ID_STORAGE_KEY, deviceId);
  return deviceId;
}

type Message = {
  id?: string;
  debate_id?: string;
  round: number;
  speaker: "Moderator" | "Pro Agent" | "Con Agent";
  content: string;
  created_at?: string;
};

type Source = { title: string; url: string; snippet: string };

type FactCheck = {
  id?: string;
  claim_id: string;
  claim?: string;
  speaker?: string;
  verdict: string;
  confidence: number;
  rationale: string;
  sources?: Source[];
};

type Score = { round: number; pro_score: number; con_score: number; breakdown?: any };

type Debate = {
  id: string;
  topic: string;
  status: string;
  rounds: number;
  current_round: number;
  pro_score: number;
  con_score: number;
  winner?: string;
  final_summary?: string;
  created_at: string;
  messages?: Message[];
  fact_checks?: FactCheck[];
  scores?: Score[];
};

const nav = [["Dashboard", Home], ["Debate History", History], ["About", Info]] as const;

export function App() {
  const deviceId = useMemo(() => getOrCreateDeviceId(), []);
  const [topic, setTopic] = useState("");
  const [rounds, setRounds] = useState(3);
  const [debate, setDebate] = useState<Debate | null>(null);
  const [isReadOnlyDebate, setIsReadOnlyDebate] = useState(false);
  const [deletePrompt, setDeletePrompt] = useState<{
    scope: "single" | "all";
    debateId?: string;
    title: string;
    message: string;
  } | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [facts, setFacts] = useState<FactCheck[]>([]);
  const [scores, setScores] = useState<Score[]>([]);
  const [history, setHistory] = useState<Debate[]>([]);
  const [view, setView] = useState<"dashboard" | "history" | "about">("dashboard");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [summary, setSummary] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const roundsRef = useRef<HTMLDivElement | null>(null);
  const rightScrollRef = useRef<HTMLDivElement | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);
  const [rightMaxHeight, setRightMaxHeight] = useState<number | null>(null);

  function deviceFetch(input: RequestInfo | URL, init: RequestInit = {}) {
    const headers = new Headers(init.headers ?? {});
    headers.set("X-Device-Id", deviceId);
    return fetch(input, { ...init, headers });
  }

  useEffect(() => {
    deviceFetch(`${API_URL}/api/debates`).then((r) => r.json()).then(setHistory).catch(() => setHistory([]));
  }, [deviceId]);

  useEffect(() => {
    let raf = 0;
    function updateMax() {
      if (!roundsRef.current || !rightScrollRef.current) return;
      const roundsRect = roundsRef.current.getBoundingClientRect();
      const rightRect = rightScrollRef.current.getBoundingClientRect();
      // compute available height so the right column (scroller + live) ends at the bottom of rounds card
      const padding = 16; // small gap
      // account for padding/borders in the two elements to avoid small mismatch
      const roundsStyle = window.getComputedStyle(roundsRef.current);
      const rightStyle = window.getComputedStyle(rightScrollRef.current);
      const roundsPadBottom = parseInt(roundsStyle.paddingBottom || "0") || 0;
      const rightPadTop = parseInt(rightStyle.paddingTop || "0") || 0;
      const extraFudge = roundsPadBottom + rightPadTop + 8; // extra safety margin
      const containerHeight = Math.floor(roundsRect.bottom - rightRect.top - padding - extraFudge);
      const liveHeight = liveRef.current ? liveRef.current.getBoundingClientRect().height : 0;
      const max = Math.max(120, containerHeight - liveHeight - 8);
      setRightMaxHeight(max);
    }

    function schedule() {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(updateMax);
    }

    schedule();
    window.addEventListener("resize", schedule);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", schedule);
    };
  }, [messages, summary, facts, scores, debate]);

  const latestScore = scores.length > 0 ? scores[scores.length - 1] : undefined;
  const proScore = latestScore?.pro_score ?? debate?.pro_score ?? 0;
  const conScore = latestScore?.con_score ?? debate?.con_score ?? 0;
  const leader = proScore >= conScore ? "Pro Agent" : "Con Agent";

  const scoreRows = useMemo(() => {
    const bd = latestScore?.breakdown;
    if (!bd) return [];
    return Object.keys(bd.pro || {}).map((k) => ({ label: k[0].toUpperCase() + k.slice(1), pro: bd.pro[k], con: bd.con[k] }));
  }, [latestScore]);

  async function startDebate(e: FormEvent) {
    e.preventDefault();
    if (isReadOnlyDebate) return;
    setError("");
    setMessages([]);
    setFacts([]);
    setScores([]);
    setSummary("");
    setIsRunning(true);

    try {
      const health = await fetch(`${API_URL}/api/health`).catch(() => null);
      if (!health || !health.ok) throw new Error("Backend unreachable");
      const created = await deviceFetch(`${API_URL}/api/debates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, rounds, stance_style: "balanced" }),
      }).then((r) => {
        if (!r.ok) throw new Error("Unable to create debate");
        return r.json();
      });

      setDebate(created);
      setIsReadOnlyDebate(false);
      const stream = new EventSource(`${API_URL}/api/debates/${created.id}/stream?device_id=${encodeURIComponent(deviceId)}`);
      stream.onerror = () => {
        setError(`Failed to open stream to ${API_URL}`);
        setIsRunning(false);
        stream.close();
      };
      stream.addEventListener("moderator_message", (ev) => setMessages((m) => [...m, JSON.parse((ev as MessageEvent).data)]));
      stream.addEventListener("agent_message", (ev) => setMessages((m) => [...m, JSON.parse((ev as MessageEvent).data)]));
      stream.addEventListener("fact_check_result", (ev) => setFacts((f) => [JSON.parse((ev as MessageEvent).data), ...f].slice(0, 8)));
      stream.addEventListener("score_update", (ev) => setScores((s) => [...s, JSON.parse((ev as MessageEvent).data)]));
      stream.addEventListener("debate_complete", (ev) => {
        const data = JSON.parse((ev as MessageEvent).data);
        setSummary(data.final_summary);
        setDebate((c) => (c ? { ...c, winner: data.winner, status: "complete", final_summary: data.final_summary } : c));
        setIsRunning(false);
        stream.close();
        deviceFetch(`${API_URL}/api/debates`).then((r) => r.json()).then(setHistory).catch(() => undefined);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setIsRunning(false);
    }
  }

  function startNewDebate() {
    setDebate(null);
    setTopic("");
    setRounds(3);
    setMessages([]);
    setFacts([]);
    setScores([]);
    setSummary("");
    setError("");
    setIsRunning(false);
    setIsReadOnlyDebate(false);
    setView("dashboard");
  }

  async function confirmDeletePrompt() {
    if (!deletePrompt) return;

    try {
      if (deletePrompt.scope === "all") {
        await deviceFetch(`${API_URL}/api/debates`, { method: "DELETE" });
        setHistory([]);
        startNewDebate();
      } else if (deletePrompt.debateId) {
        await deviceFetch(`${API_URL}/api/debates/${deletePrompt.debateId}`, { method: "DELETE" });
        setHistory((items) => items.filter((item) => item.id !== deletePrompt.debateId));
        if (debate?.id === deletePrompt.debateId) {
          startNewDebate();
        }
      }
      setDeletePrompt(null);
    } catch (error) {
      console.error(error);
      alert("Failed to delete debate");
    }
  }

  async function loadDebate(id: string) {
    const detail = await deviceFetch(`${API_URL}/api/debates/${id}`).then((r) => r.json());
    setDebate(detail);
    setTopic(detail.topic);
    setRounds(detail.rounds);
    setIsReadOnlyDebate(true);
    setMessages(detail.messages ?? []);
    setFacts(detail.fact_checks ?? []);
    setScores(detail.scores ?? []);
    setSummary(detail.final_summary ?? "");
    setView("dashboard");
  }

  function handleViewChange(nextView: "dashboard" | "history" | "about") {
    setView(nextView);
    setMobileNavOpen(false);
  }

  return (
    <div className="min-h-screen bg-[#f8efe0] text-ink">
      <div className="grid min-h-screen lg:grid-cols-[270px_1fr]">
        <aside className="relative hidden overflow-hidden bg-[linear-gradient(155deg,#352313,#6f4718)] p-6 text-white lg:block">
          <div className="flex items-center gap-3 text-2xl font-bold">
            <MessageSquare className="h-10 w-10 text-[#ffd56c]" />
            <span>AI Debate<br />System</span>
          </div>

          <nav className="mt-12 space-y-3">
            {nav.map(([label, Icon]) => (
              <button
                key={label}
                onClick={() => setView(label === "Debate History" ? "history" : label === "About" ? "about" : "dashboard")}
                className={`flex w-full items-center gap-4 rounded-md px-4 py-3 text-left ${
                  view === (label === "Debate History" ? "history" : label === "About" ? "about" : "dashboard") ? "bg-[#ffe68c] text-ink" : "text-white/90 hover:bg-white/10"
                }`}>
                <Icon className="h-5 w-5 text-[#ffd35c]" />
                <span className="font-medium">{label}</span>
              </button>
            ))}
          </nav>

          <div className="absolute bottom-8 left-6 right-6 border-t border-white/15 pt-6">
            <p className="font-semibold">AI Debate System</p>
            <p className="mt-2 text-sm text-white/80">Intelligent debates. Smarter decisions.</p>
            <p className="mt-10 text-sm text-white/70">© 2026</p>
          </div>
        </aside>

        <main className="p-4 md:p-6">
          <div className="mb-4 flex items-center justify-between rounded-lg border border-[#efcc93] bg-vellum/90 p-3 shadow-panel lg:hidden">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-copper">AI Debate System</p>
              <p className="text-sm text-[#6e5846]">{view === "dashboard" ? "Dashboard" : view === "history" ? "Debate History" : "About"}</p>
            </div>
            <button
              type="button"
              onClick={() => setMobileNavOpen((open) => !open)}
              className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-[#e8c790] bg-white/70 text-ink shadow-sm"
              aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
            >
              <MessageSquare className="h-5 w-5 text-amberline" />
            </button>
          </div>

          <div
            className={`fixed inset-0 z-40 bg-black/45 transition-opacity lg:hidden ${mobileNavOpen ? "opacity-100" : "pointer-events-none opacity-0"}`}
            onClick={() => setMobileNavOpen(false)}
            aria-hidden="true"
          />

          <aside
            className={`fixed right-0 top-0 z-50 h-full w-[82vw] max-w-[320px] border-l border-[#efcc93] bg-[linear-gradient(155deg,#352313,#6f4718)] p-5 text-white shadow-2xl transition-transform duration-300 lg:hidden ${mobileNavOpen ? "translate-x-0" : "translate-x-full"}`}
          >
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 text-xl font-bold">
                <MessageSquare className="h-9 w-9 text-[#ffd56c]" />
                <span>AI Debate<br />System</span>
              </div>
              <button
                type="button"
                onClick={() => setMobileNavOpen(false)}
                className="rounded-md border border-white/20 px-3 py-2 text-sm font-semibold text-white/90"
              >
                Close
              </button>
            </div>

            <nav className="mt-8 space-y-3">
              {nav.map(([label, Icon]) => {
                const targetView = label === "Debate History" ? "history" : label === "About" ? "about" : "dashboard";
                const active = view === targetView;
                return (
                  <button
                    key={label}
                    onClick={() => handleViewChange(targetView)}
                    className={`flex w-full items-center gap-4 rounded-md px-4 py-3 text-left ${
                      active ? "bg-[#ffe68c] text-ink" : "text-white/90 hover:bg-white/10"
                    }`}
                  >
                    <Icon className="h-5 w-5 text-[#ffd35c]" />
                    <span className="font-medium">{label}</span>
                  </button>
                );
              })}
            </nav>

            <div className="absolute bottom-6 left-5 right-5 border-t border-white/15 pt-5">
              <p className="font-semibold">AI Debate System</p>
              <p className="mt-2 text-sm text-white/80">Intelligent debates. Smarter decisions.</p>
            </div>
          </aside>

          {view === "dashboard" && (
            <div>
              {isReadOnlyDebate && (
                <section className="mb-5 rounded-lg border border-[#efcc93] bg-vellum/90 p-5 shadow-panel">
                  <div className="flex flex-wrap items-center justify-between gap-4">
                    <div>
                      <p className="text-sm font-medium text-copper">New Debate</p>
                      <h2 className="mt-1 text-2xl font-bold">Open a fresh debate from the placeholder</h2>
                      <p className="mt-2 text-sm text-[#6e5846]">Use this to return to the editable dashboard and enter a new topic.</p>
                    </div>
                    <button
                      type="button"
                      onClick={startNewDebate}
                      className="rounded-md bg-[#ffc94d] px-4 py-2 text-sm font-bold text-ink shadow-sm hover:bg-[#ffbd2f]"
                    >
                      New Debate
                    </button>
                  </div>
                </section>
              )}

              <section className="rounded-lg border border-[#efcc93] bg-vellum/85 p-5 shadow-panel">
                <form onSubmit={startDebate} className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-end">
                  <div>
                    <p className="text-sm font-medium text-copper">Current Topic</p>
                    {isReadOnlyDebate ? (
                      <div className="mt-2 text-2xl font-bold md:text-3xl text-[#8b6a4c]">{topic}</div>
                    ) : (
                      <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Enter your debate topic here" className="mt-2 w-full bg-transparent text-2xl font-bold outline-none md:text-3xl" aria-label="Debate topic" />
                    )}
                    <div className="mt-4 flex flex-wrap gap-3">
                      <label className="rounded-md border border-[#e8c790] bg-white/55 px-4 py-2 text-sm">
                        Rounds
                        {isReadOnlyDebate ? (
                          <span className="ml-3 font-semibold">{rounds}</span>
                        ) : (
                          <input type="number" min={1} max={5} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} className="ml-3 w-12 bg-transparent font-semibold outline-none" />
                        )}
                      </label>
                      <div className="rounded-md border border-[#e8c790] bg-white/55 px-4 py-2 text-sm">Model: Llama 3.3 70B (Groq)</div>
                    </div>
                    {isReadOnlyDebate && <p className="mt-3 text-xs font-semibold uppercase tracking-wide text-copper">Historical debate is read-only</p>}
                  </div>

                  {!isReadOnlyDebate ? (
                    <button className="inline-flex items-center justify-center gap-3 rounded-md bg-[#ffc94d] px-8 py-4 font-bold text-ink shadow-sm hover:bg-[#ffbd2f]" disabled={isRunning}>
                      {isRunning ? <Loader2 className="h-5 w-5 animate-spin" /> : <Square className="h-4 w-4 fill-ink" />}
                      {isRunning ? "Debating" : "Start Debate"}
                    </button>
                  ) : (
                    <div className="inline-flex items-center justify-center rounded-md border border-[#e8c790] bg-white/55 px-8 py-4 font-bold text-[#8b6a4c]">
                      Read Only
                    </div>
                  )}
                </form>
                {error && <p className="mt-4 rounded-md bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>}
              </section>

              <div className="mt-5 grid gap-5 xl:grid-cols-[minmax(0,1fr)_380px]">
                <section className="space-y-5">
                  <div className="space-y-4">
                    {messages.length === 0 ? (
                      <div className="rounded-lg border border-[#efcc93] bg-vellum p-8 text-center shadow-panel">
                        <FileText className="mx-auto h-10 w-10 text-amberline" />
                        <h1 className="mt-4 text-2xl font-bold">Start a source-backed debate</h1>
                        <p className="mx-auto mt-2 max-w-xl text-[#6e5846]">The moderator, Pro Agent, Con Agent, fact checker, and scoring engine will update live as the debate runs.</p>
                      </div>
                    ) : (
                      messages.map((message, idx) => (
                        <article
                          key={`${message.speaker}-${message.round}-${idx}`}
                          className={`rounded-lg border p-5 shadow-panel ${message.speaker === "Con Agent" ? "border-[#efd9b7] bg-[#fff7ea]" : "border-[#efcc93] bg-vellum"}`}
                        >
                          <div className="flex items-start gap-4">
                            <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-md ${message.speaker === "Con Agent" ? "bg-[#c98a4a] text-white" : "bg-[#ffd769] text-ink"}`}>
                              {message.speaker === "Moderator" ? <UserRound /> : <Bot />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <h2 className="text-lg font-bold">{message.speaker}</h2>
                                <span className={`rounded-md px-3 py-1 text-xs font-bold ${message.speaker === "Con Agent" ? "bg-[#efd0a1] text-[#6a4215]" : "bg-[#ffe28a]"}`}>{message.speaker === "Moderator" ? `Round ${message.round}` : message.speaker.split(" ")[0]}</span>
                              </div>
                              <p className="mt-4 whitespace-pre-wrap leading-7">{message.content}</p>
                            </div>
                          </div>
                        </article>
                      ))
                    )}
                    <section className="rounded-lg border border-[#efcc93] bg-vellum p-5 shadow-panel">
                      <div className="flex items-center justify-between">
                        <h2 className="text-lg font-bold">Debate Summary</h2>
                        {!isReadOnlyDebate && (
                          <div className="flex items-center gap-2">
                          <button
                            onClick={async () => {
                              try {
                                await navigator.clipboard.writeText(summary || "");
                                alert("Summary copied to clipboard");
                              } catch (e) {
                                console.error(e);
                                alert("Unable to copy summary");
                              }
                            }}
                            className="rounded-md bg-[#ffd769] px-3 py-1 text-sm font-semibold"
                          >
                            Copy
                          </button>
                          </div>
                        )}
                      </div>

                      <div className="mt-4">
                        {summary ? (
                          <SummaryRenderer summary={summary} />
                        ) : (
                          <div className="text-sm text-[#6e5846]">The final debate summary will appear here after the debate completes.</div>
                        )}

                        {/* Final result block removed per request */}
                      </div>
                    </section>
                  </div>

                  <section ref={roundsRef as any} id="debate-progress" className="rounded-lg border border-[#efcc93] bg-vellum p-5 shadow-panel">
                    <h2 className="font-bold">Debate Progress</h2>
                    <div className="mt-6 grid grid-cols-3 gap-3">
                      {Array.from({ length: debate?.rounds ?? rounds }, (_, i) => i + 1).map((r) => (
                        <div key={r} className="text-center">
                          <div className={`mx-auto grid h-12 w-12 place-items-center rounded-full border-2 font-bold ${r <= (latestScore?.round ?? 0) ? "border-amberline bg-[#ffd25a]" : "border-[#efcc93] bg-white"}`}>
                            {r}
                          </div>
                          <p className="mt-2 text-sm">Round {r}</p>
                        </div>
                      ))}
                    </div>
                  </section>
                </section>

                <aside className="flex flex-col gap-5">
                  <div ref={rightScrollRef as any} className="overflow-y-auto" style={{ scrollBehavior: 'smooth', maxHeight: rightMaxHeight ? `${rightMaxHeight}px` : undefined }}>
                    <section className="rounded-lg border border-[#efcc93] bg-vellum p-5 shadow-panel">
                      <div className="flex items-center gap-3">
                        <ShieldCheck className="h-7 w-7 text-amberline" />
                        <h2 className="text-lg font-bold">Fact Check</h2>
                      </div>
                      <div className="mt-4 space-y-3">
                        {facts.length === 0 && <p className="text-sm text-[#6e5846]">Claims will appear here as the agents make checkable statements.</p>}
                        {facts.map((fact, i) => (
                          <div key={`${fact.claim_id}-${i}`} className="rounded-md border border-[#efcc93] bg-white/55 p-4">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold">{fact.verdict}</p>
                              {fact.speaker && <span className="rounded bg-[#ffe28a] px-2 py-1 text-xs font-semibold">{fact.speaker.replace(" Agent", "")}</span>}
                            </div>
                            {fact.claim && <p className="mt-2 text-sm leading-5 text-[#2f241c]">Claim: {fact.claim}</p>}
                            <p className="mt-2 text-sm text-[#5b4636]">{fact.rationale}</p>
                            <p className="mt-3 text-sm font-medium text-copper">{fact.confidence}% confidence</p>
                            {fact.sources && fact.sources.length > 0 && (
                              <div className="mt-3 border-t border-[#efd7ad] pt-3">
                                <p className="text-xs font-bold uppercase tracking-wide text-copper">References</p>
                                <div className="mt-2 space-y-2">{fact.sources.slice(0, 3).map((s, si) => <ReferenceLink key={`${s.url}-${si}`} source={s} index={si+1} />)}</div>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </section>
                  </div>

                  <div ref={liveRef as any} className="flex-shrink-0">
                    <section className="rounded-lg border border-[#efcc93] bg-vellum p-5 shadow-panel">
                      <div className="flex items-center gap-3">
                        <Trophy className="h-7 w-7 text-amberline" />
                        <h2 className="text-lg font-bold">Live Scores</h2>
                      </div>
                      <div className="mt-4 grid grid-cols-2 gap-3">
                        <ScoreCard label="Pro Agent" value={proScore} accent="bg-amberline" />
                        <ScoreCard label="Con Agent" value={conScore} accent="bg-copper" />
                      </div>
                      {scoreRows.length > 0 && (
                        <table className="mt-4 w-full text-sm">
                          <thead>
                            <tr className="text-left text-copper"><th>Breakdown</th><th>Pro</th><th>Con</th></tr>
                          </thead>
                          <tbody>{scoreRows.map((row) => <tr key={row.label} className="border-t border-[#efd7ad]"><td className="py-2">{row.label}</td><td>{row.pro}</td><td>{row.con}</td></tr>)}</tbody>
                        </table>
                      )}
                      {(proScore > 0 || conScore > 0) && (
                        <div className="mt-4 rounded-md border border-[#efcc93] bg-white/55 p-4">
                          <p className="text-xs font-semibold text-copper">Current Leader</p>
                          <p className="mt-2 text-lg font-bold">{leader}</p>
                        </div>
                      )}
                    </section>
                  </div>
                </aside>
              </div>
            </div>
          )}

          {view === "history" && (
            <section className="rounded-lg border border-[#efcc93] bg-vellum/85 p-5 shadow-panel">
              <div className="flex items-center justify-between">
                <h2 className="text-lg font-bold">Debate History</h2>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() =>
                      setDeletePrompt({
                        scope: "all",
                        title: "Delete all debate history?",
                        message: "This will permanently remove every debate, and it cannot be restored.",
                      })
                    }
                    className="rounded-md bg-red-500 px-3 py-2 text-sm font-semibold text-white"
                  >
                    Clear History
                  </button>
                </div>
              </div>

              <div className="mt-4 space-y-2">
                {history.length === 0 && <p className="text-sm text-[#6e5846]">No past debates found.</p>}
                {history.map((item) => (
                  <div key={item.id} className="flex items-center justify-between rounded-md border border-[#efcc93] bg-white/55 p-3">
                    <div>
                      <div className="font-semibold">{item.topic}</div>
                      <div className="text-sm text-[#6e5846]">
                        {item.status} • {item.rounds} rounds • {new Date(item.created_at).toLocaleString()}
                      </div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => loadDebate(item.id)} className="rounded-md border border-[#efcc93] bg-white/55 px-3 py-2 text-sm">Open</button>
                      <button
                        onClick={() =>
                          setDeletePrompt({
                            scope: "single",
                            debateId: item.id,
                            title: "Delete this debate permanently?",
                            message: "This debate will be deleted forever and cannot be restored.",
                          })
                        }
                        className="rounded-md bg-red-500 px-3 py-2 text-sm font-semibold text-white"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {view === "about" && (
            <section className="rounded-lg border border-[#efcc93] bg-vellum/85 p-5 shadow-panel">
              <h2 className="text-lg font-bold">About</h2>
              <div className="mt-4 space-y-4 text-sm leading-6 text-[#6e5846]">
                <p>
                  AI Debate System is a structured argument platform where two sides debate a topic while the system
                  moderates the exchange, extracts checkable claims, gathers references, and scores the strength of each
                  side in real time.
                </p>
                <p>
                  It is designed to make disagreements easier to understand by presenting both perspectives side by side.
                  Instead of reading a single opinion, you can see how the Pro Agent and Con Agent build their arguments,
                  what evidence supports them, and where the strongest counterpoints appear.
                </p>
                <p>
                  The system is useful for many topics, including technology, education, science, policy, business, and
                  everyday decision-making. It can be used for classroom learning, discussion practice, research
                  comparison, critical thinking exercises, and exploring complex issues from multiple angles.
                </p>
                <p>
                  It is especially helpful when you want to compare both sides practically, because the debate flow shows
                  the arguments, the references, and the scoring together in one place. That makes it easier to judge the
                  quality of the reasoning instead of relying on a quick summary alone.
                </p>
                <div className="rounded-md border border-[#efd7ad] bg-white/60 p-4">
                  <p className="font-semibold text-[#2f241c]">Features</p>
                  <ul className="mt-2 list-disc space-y-2 pl-5">
                    <li>Live moderated debates with clear round-by-round structure.</li>
                    <li>Claim extraction and fact checking with saved source references.</li>
                    <li>Scoring that compares both sides using reasoning and evidence quality.</li>
                    <li>Debate history so past discussions can be reviewed later.</li>
                    <li>Read-only historical debates with clickable reference links.</li>
                  </ul>
                </div>
                <p className="font-semibold text-[#2f241c]">
                  Security note: your debate data is not leaked or shared outside the system, and the stored history is
                  meant to stay on this device for review and reference.
                </p>
                <p className="font-bold text-[#2f241c]">
                  NOTE: This system may occasionally make mistakes, so please review all data and references carefully and apply your own judgment as well.
                </p>
              </div>
            </section>
          )}

          {deletePrompt && (
            <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4">
              <div className="w-full max-w-md rounded-2xl border border-[#efcc93] bg-[#fff8ee] p-6 shadow-2xl">
                <p className="text-sm font-semibold uppercase tracking-wide text-copper">Confirm Deletion</p>
                <h3 className="mt-2 text-2xl font-bold text-ink">{deletePrompt.title}</h3>
                <p className="mt-3 text-sm leading-6 text-[#6e5846]">{deletePrompt.message}</p>
                <div className="mt-6 flex items-center justify-end gap-3">
                  <button
                    type="button"
                    onClick={() => setDeletePrompt(null)}
                    className="rounded-md border border-[#efcc93] bg-white/70 px-4 py-2 text-sm font-semibold text-ink"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={confirmDeletePrompt}
                    className="rounded-md bg-red-500 px-4 py-2 text-sm font-semibold text-white hover:bg-red-600"
                  >
                    Confirm
                  </button>
                </div>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}

function ScoreCard({ label, value, accent }: { label: string; value: number; accent: string }) {
  return (
    <div className="rounded-md border border-[#efcc93] bg-white/60 p-4 text-center">
      <p className="text-sm font-semibold">{label}</p>
      <p className="mt-2 text-4xl font-bold">{value}<span className="text-base font-medium"> /100</span></p>
      <div className="mt-3 h-2 rounded-full bg-[#ead9bf]">
        <div className={`h-2 rounded-full ${accent}`} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}

function SummaryRenderer({ summary }: { summary: string }) {
  const lines = summary.split(/\r?\n/);
  return (
    <div className="mt-4 text-sm leading-6 text-[#4f3d30]">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (/^\d+\./.test(trimmed)) return <p key={idx} className="font-bold mt-2">{trimmed}</p>;
        const bulletMatch = trimmed.match(/^[-–]\s*([^:]+:\s*)(.*)$/);
        if (bulletMatch) {
          const heading = bulletMatch[1];
          const rest = bulletMatch[2];
          return (
            <div key={idx} className="mt-2 mb-2">
              <p><span className="font-semibold">{heading}</span>{rest}</p>
            </div>
          );
        }
        if (/^[-–]\s+/.test(trimmed)) return <p key={idx} className="mt-2 mb-2">{trimmed}</p>;
        return <p key={idx} className="mt-2">{trimmed}</p>;
      })}
    </div>
  );
}

function ReferenceLink({ source, index }: { source: Source; index: number }) {
  const isExternal = source.url.startsWith("http://") || source.url.startsWith("https://");
  const label = `[${index}] ${source.title}`;
  if (!isExternal) {
    return (
      <div className="rounded border border-[#efd7ad] bg-white/60 px-2 py-2 text-xs leading-5 text-[#5b4636]">
        <span className="font-semibold text-copper">{label}</span>
        {source.snippet && <p className="mt-1">{source.snippet}</p>}
      </div>
    );
  }
  return (
    <a className="block rounded border border-[#efd7ad] bg-white/60 px-2 py-2 text-xs leading-5 text-copper underline" href={source.url} target="_blank" rel="noreferrer">{label}</a>
  );
}
