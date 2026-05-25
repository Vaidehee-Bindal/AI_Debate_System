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

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

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
  const [topic, setTopic] = useState("AI will replace software engineers");
  const [rounds, setRounds] = useState(3);
  const [debate, setDebate] = useState<Debate | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [facts, setFacts] = useState<FactCheck[]>([]);
  const [scores, setScores] = useState<Score[]>([]);
  const [history, setHistory] = useState<Debate[]>([]);
  const [view, setView] = useState<"dashboard" | "history" | "about">("dashboard");
  const [summary, setSummary] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState("");
  const roundsRef = useRef<HTMLDivElement | null>(null);
  const rightScrollRef = useRef<HTMLDivElement | null>(null);
  const liveRef = useRef<HTMLDivElement | null>(null);
  const [rightMaxHeight, setRightMaxHeight] = useState<number | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/api/debates`).then((r) => r.json()).then(setHistory).catch(() => setHistory([]));
  }, []);

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
    setError("");
    setMessages([]);
    setFacts([]);
    setScores([]);
    setSummary("");
    setIsRunning(true);

    try {
      const health = await fetch(`${API_BASE}/api/health`).catch(() => null);
      if (!health || !health.ok) throw new Error("Backend unreachable");
      const created = await fetch(`${API_BASE}/api/debates`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ topic, rounds, stance_style: "balanced" }),
      }).then((r) => {
        if (!r.ok) throw new Error("Unable to create debate");
        return r.json();
      });

      setDebate(created);
      const stream = new EventSource(`${API_BASE}/api/debates/${created.id}/stream`);
      stream.onerror = () => {
        setError(`Failed to open stream to ${API_BASE}`);
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
        fetch(`${API_BASE}/api/debates`).then((r) => r.json()).then(setHistory).catch(() => undefined);
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setIsRunning(false);
    }
  }

  async function loadDebate(id: string) {
    const detail = await fetch(`${API_BASE}/api/debates/${id}`).then((r) => r.json());
    setDebate(detail);
    setTopic(detail.topic);
    setMessages(detail.messages ?? []);
    setFacts(detail.fact_checks ?? []);
    setScores(detail.scores ?? []);
    setSummary(detail.final_summary ?? "");
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
          {view === "dashboard" && (
            <div>
              <section className="rounded-lg border border-[#efcc93] bg-vellum/85 p-5 shadow-panel">
                <form onSubmit={startDebate} className="grid gap-4 xl:grid-cols-[1fr_auto] xl:items-end">
                  <div>
                    <p className="text-sm font-medium text-copper">Current Topic</p>
                    <input value={topic} onChange={(e) => setTopic(e.target.value)} className="mt-2 w-full bg-transparent text-2xl font-bold outline-none md:text-3xl" aria-label="Debate topic" />
                    <div className="mt-4 flex flex-wrap gap-3">
                      <label className="rounded-md border border-[#e8c790] bg-white/55 px-4 py-2 text-sm">
                        Rounds
                        <input type="number" min={1} max={5} value={rounds} onChange={(e) => setRounds(Number(e.target.value))} className="ml-3 w-12 bg-transparent font-semibold outline-none" />
                      </label>
                      <div className="rounded-md border border-[#e8c790] bg-white/55 px-4 py-2 text-sm">Model: Llama 3.3 70B (Groq)</div>
                    </div>
                  </div>

                  <button className="inline-flex items-center justify-center gap-3 rounded-md bg-[#ffc94d] px-8 py-4 font-bold text-ink shadow-sm hover:bg-[#ffbd2f]" disabled={isRunning}>
                    {isRunning ? <Loader2 className="h-5 w-5 animate-spin" /> : <Square className="h-4 w-4 fill-ink" />}
                    {isRunning ? "Debating" : "Start Debate"}
                  </button>
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
                        <article key={`${message.speaker}-${message.round}-${idx}`} className="rounded-lg border border-[#efcc93] bg-vellum p-5 shadow-panel">
                          <div className="flex items-start gap-4">
                            <div className={`grid h-14 w-14 shrink-0 place-items-center rounded-md ${message.speaker === "Con Agent" ? "bg-[#a76b38] text-white" : "bg-[#ffd769] text-ink"}`}>
                              {message.speaker === "Moderator" ? <UserRound /> : <Bot />}
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center justify-between gap-3">
                                <h2 className="text-lg font-bold">{message.speaker}</h2>
                                <span className="rounded-md bg-[#ffe28a] px-3 py-1 text-xs font-bold">{message.speaker === "Moderator" ? `Round ${message.round}` : message.speaker.split(" ")[0]}</span>
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
                    onClick={async () => {
                      if (!confirm("Clear all debate history? This cannot be undone.")) return;
                      try {
                        await fetch(`${API_BASE}/api/debates`, { method: "DELETE" });
                        setHistory([]);
                      } catch (e) {
                        console.error(e);
                        alert("Failed to clear history");
                      }
                    }}
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
                      <div className="text-sm text-[#6e5846]">{item.status} • {new Date(item.created_at).toLocaleString()}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => loadDebate(item.id)} className="rounded-md border border-[#efcc93] bg-white/55 px-3 py-2 text-sm">Open</button>
                      <button
                        onClick={async () => {
                          if (!confirm("Delete this debate?")) return;
                          try {
                            await fetch(`${API_BASE}/api/debates/${item.id}`, { method: "DELETE" });
                            setHistory((h) => h.filter((d) => d.id !== item.id));
                          } catch (e) {
                            console.error(e);
                            alert("Failed to delete debate");
                          }
                        }}
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
              <p className="mt-3 text-sm text-[#6e5846]">AI Debate System — demo UI.</p>
            </section>
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
