"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type View = "dashboard" | "candidates" | "settings";
type Status = "pending" | "needs_edit" | "registered" | "ignored";
type Filter = "all" | Status;

type Analysis = {
  is_schedule: boolean;
  type: string;
  title: string | null;
  date: string | null;
  start_time: string | null;
  end_time: string | null;
  confidence: number;
  ambiguities: string[];
  source_summary: string | null;
};

type Candidate = {
  id: number;
  status: Status;
  google_event_id: string | null;
  created_at: string;
  updated_at: string;
  message: {
    room_type: string | null;
    sender_person_id: string | null;
    created_at: string | null;
    source_text?: string | null;
  };
  analysis: Analysis;
};

type Session = {
  authenticated: boolean;
  user: {
    id: number;
    email: string | null;
    display_name: string | null;
  };
};

type Dashboard = {
  counts: Record<Status, number>;
  recent: Candidate[];
  connections: Connections;
};

type Connections = {
  webex_connected: boolean;
  google_connected: boolean;
};

type Settings = {
  connections: Connections;
  health: { ok: boolean; service: string };
  webhooks: Array<Record<string, string | null>>;
  missing_env: string[];
};

const statusLabels: Record<Filter, string> = {
  all: "전체",
  pending: "승인 대기",
  needs_edit: "수정 필요",
  registered: "등록 완료",
  ignored: "무시됨"
};

const nav = [
  { href: "/dashboard", label: "대시보드", view: "dashboard" },
  { href: "/candidates", label: "스케줄 후보", view: "candidates" },
  { href: "/settings", label: "설정", view: "settings" }
] as const;

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(apiUrl(path), {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    }
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new Error(detail.detail || `Request failed: ${response.status}`);
  }
  return response.json();
}

export function ConsolePage({ view }: { view: View }) {
  const [session, setSession] = useState<Session | null>(null);
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [correction, setCorrection] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    void boot();
  }, [view]);

  useEffect(() => {
    if (view === "candidates" && session) {
      void loadCandidates(filter);
    }
  }, [filter]);

  async function boot() {
    setLoading(true);
    setError(null);
    try {
      const claimed = await claimRedirectSession();
      if (claimed) {
        window.history.replaceState({}, "", window.location.pathname);
      }
      const current = await apiFetch<Session>("/api/session");
      setSession(current);
      if (view === "dashboard") {
        setDashboard(await apiFetch<Dashboard>("/api/dashboard"));
      }
      if (view === "candidates") {
        await loadCandidates(filter);
      }
      if (view === "settings") {
        setSettings(await apiFetch<Settings>("/api/settings"));
      }
    } catch (err) {
      setSession(null);
      setError(err instanceof Error ? err.message : "요청을 처리하지 못했습니다.");
    } finally {
      setLoading(false);
    }
  }

  async function claimRedirectSession() {
    const token = new URLSearchParams(window.location.search).get("session_token");
    if (!token) return false;
    await apiFetch<Session>("/api/session/claim", {
      method: "POST",
      body: JSON.stringify({ session_token: token })
    });
    return true;
  }

  async function loadCandidates(nextFilter: Filter) {
    const query = nextFilter === "all" ? "" : `?status=${nextFilter}`;
    const data = await apiFetch<{ candidates: Candidate[] }>(`/api/candidates${query}`);
    setCandidates(data.candidates);
    const first = data.candidates[0];
    setSelected(first ? (await apiFetch<{ candidate: Candidate }>(`/api/candidates/${first.id}`)).candidate : null);
  }

  async function selectCandidate(candidateId: number) {
    setSelected((await apiFetch<{ candidate: Candidate }>(`/api/candidates/${candidateId}`)).candidate);
    setCorrection("");
    setNotice(null);
  }

  async function runCandidateAction(action: "approve" | "ignore" | "edit") {
    if (!selected) return;
    setNotice(null);
    if (action === "edit" && !correction.trim()) {
      setNotice("수정할 내용을 입력한 뒤 다시 분석할 수 있습니다.");
      return;
    }
    try {
      const payload =
        action === "edit"
          ? { method: "POST", body: JSON.stringify({ correction: correction.trim() }) }
          : { method: "POST" };
      const result = await apiFetch<Record<string, string>>(`/api/candidates/${selected.id}/${action}`, payload);
      setNotice(actionNotice(result.status));
      if (action === "edit") setCorrection("");
      await loadCandidates(filter);
    } catch (error) {
      setError(error instanceof Error ? error.message : "요청 처리 중 문제가 발생했습니다.");
    }
  }

  async function logout() {
    await apiFetch("/api/logout", { method: "POST" });
    setSession(null);
  }

  const title = useMemo(() => {
    if (view === "dashboard") return "대시보드";
    if (view === "candidates") return "스케줄 후보";
    return "설정";
  }, [view]);

  if (!session && !loading) {
    return <LoginScreen error={error} />;
  }

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">AI</div>
          <div>
            <strong>AI Soma</strong>
            <span>Secretary</span>
          </div>
        </div>
        <nav className="nav">
          {nav.map((item) => (
            <Link key={item.href} className={view === item.view ? "active" : ""} href={item.href}>
              {item.label}
            </Link>
          ))}
        </nav>
      </aside>

      <main className="main">
        <header className="topbar">
          <div>
            <p className="eyebrow">Webex 기반 AI 일정 승인 콘솔</p>
            <h1>{title}</h1>
          </div>
          <div className="userbox">
            <span>{session?.user.display_name || session?.user.email || "Webex User"}</span>
            <button className="ghost" onClick={logout}>로그아웃</button>
          </div>
        </header>

        {loading && <div className="empty">불러오는 중입니다.</div>}
        {!loading && error && session && <div className="alert">{error}</div>}
        {!loading && notice && <div className="notice">{notice}</div>}
        {!loading && view === "dashboard" && dashboard && <DashboardView data={dashboard} />}
        {!loading && view === "candidates" && (
          <CandidatesView
            candidates={candidates}
            selected={selected}
            filter={filter}
            correction={correction}
            onFilter={setFilter}
            onSelect={selectCandidate}
            onCorrection={setCorrection}
            onAction={runCandidateAction}
          />
        )}
        {!loading && view === "settings" && settings && <SettingsView data={settings} />}
      </main>
    </div>
  );
}

function LoginScreen({ error }: { error: string | null }) {
  return (
    <main className="login">
      <section className="login-card">
        <div className="brand-mark large">AI</div>
        <p className="eyebrow">AI Soma Secretary</p>
        <h1>Webex로 로그인하고 일정 후보를 승인하세요.</h1>
        <p>
          Webex DM에서 감지된 메시지는 그대로 유지하고, 웹에서는 승인과 수정만 처리합니다.
        </p>
        {error && error !== "Not authenticated" && <div className="alert">{error}</div>}
        <button className="primary wide" onClick={() => (window.location.href = apiUrl("/auth/webex/login"))}>
          Webex로 로그인
        </button>
      </section>
    </main>
  );
}

function DashboardView({ data }: { data: Dashboard }) {
  return (
    <div className="stack">
      <section className="metrics">
        {(Object.keys(statusLabels).filter((key) => key !== "all") as Status[]).map((status) => (
          <article key={status} className="metric-card">
            <p>{statusLabels[status]}</p>
            <strong>{data.counts[status] || 0}</strong>
          </article>
        ))}
      </section>
      <section className="grid two">
        <div className="panel">
          <h2>연결 상태</h2>
          <div className="connection-stack">
            <div className="status-box">
              <StatusChip active={data.connections.webex_connected} label="Webex connected" />
              <StatusChip active={data.connections.google_connected} label="Google Calendar connected" />
            </div>
          </div>
        </div>
        <div className="panel">
          <h2>최근 감지 후보</h2>
          <CandidateMiniList candidates={data.recent} />
        </div>
      </section>
    </div>
  );
}

function CandidatesView(props: {
  candidates: Candidate[];
  selected: Candidate | null;
  filter: Filter;
  correction: string;
  onFilter: (filter: Filter) => void;
  onSelect: (candidateId: number) => void;
  onCorrection: (value: string) => void;
  onAction: (action: "approve" | "ignore" | "edit") => void;
}) {
  return (
    <div className="candidate-layout">
      <section className="panel list-panel">
        <div className="panel-head">
          <h2>스케줄 후보</h2>
          <span>{props.candidates.length}건</span>
        </div>
        <div className="filters">
          {(Object.keys(statusLabels) as Filter[]).map((status) => (
            <button
              key={status}
              className={props.filter === status ? "filter active" : "filter"}
              onClick={() => props.onFilter(status)}
            >
              {statusLabels[status]}
            </button>
          ))}
        </div>
        <div className="candidate-list">
          {props.candidates.map((candidate) => (
            <button
              key={candidate.id}
              className={props.selected?.id === candidate.id ? "candidate-card selected" : "candidate-card"}
              onClick={() => props.onSelect(candidate.id)}
            >
              <span className={`badge ${candidate.status}`}>{statusLabels[candidate.status]}</span>
              <strong>{candidate.analysis.title || "제목 미정"}</strong>
              <span>{formatWhen(candidate.analysis)}</span>
              <small>{candidate.analysis.source_summary || "요약이 없습니다."}</small>
            </button>
          ))}
          {!props.candidates.length && <div className="empty">표시할 후보가 없습니다.</div>}
        </div>
      </section>

      <section className="panel detail-panel">
        {props.selected ? (
          <>
            <div className="panel-head">
              <h2>AI 분석 결과</h2>
              <span className={`badge ${props.selected.status}`}>{statusLabels[props.selected.status]}</span>
            </div>
            <div className="source-box">
              <p>원본 Webex 메시지</p>
              <strong>{props.selected.message.source_text || props.selected.analysis.source_summary || "원문을 불러올 수 없습니다."}</strong>
            </div>
            <dl className="analysis-grid">
              <div><dt>제목</dt><dd>{props.selected.analysis.title || "제목 미정"}</dd></div>
              <div><dt>날짜</dt><dd>{props.selected.analysis.date || "미정"}</dd></div>
              <div><dt>시작 시간</dt><dd>{props.selected.analysis.start_time || "미정"}</dd></div>
              <div><dt>종료 시간</dt><dd>{props.selected.analysis.end_time || "자동 1시간"}</dd></div>
              <div><dt>유형</dt><dd>{props.selected.analysis.type}</dd></div>
            </dl>
            <div className="ambiguity">
              <p>확인 필요</p>
              {props.selected.analysis.ambiguities.length ? (
                props.selected.analysis.ambiguities.map((item) => <span key={item}>{item}</span>)
              ) : (
                <span>추가 확인 사항 없음</span>
              )}
            </div>
            <textarea
              value={props.correction}
              onChange={(event) => props.onCorrection(event.target.value)}
              placeholder="예: 오후 3시가 아니라 오후 4시, 제목은 소마 멘토링"
            />
            <div className="actions">
              <button className="primary" onClick={() => props.onAction("approve")}>Google Calendar에 등록</button>
              <button className="secondary" disabled={!props.correction.trim()} onClick={() => props.onAction("edit")}>수정 후 다시 분석</button>
              <button className="ghost danger" onClick={() => props.onAction("ignore")}>무시</button>
            </div>
          </>
        ) : (
          <div className="empty">후보를 선택하세요.</div>
        )}
      </section>
    </div>
  );
}

function SettingsView({ data }: { data: Settings }) {
  const webexActionLabel = data.connections.webex_connected ? "Webex 재연결" : "Webex 연결";
  const googleActionLabel = data.connections.google_connected ? "Google 재연결" : "Google 연결";

  return (
    <div className="settings-grid">
      <section className="panel">
        <h2>연결 상태</h2>
        <div className="connection-stack">
          <div className="status-box">
            <StatusChip active={data.connections.webex_connected} label="Webex connected" />
            <StatusChip active={data.connections.google_connected} label="Google Calendar connected" />
          </div>
          <div className="actions compact">
            <button className="secondary" onClick={() => (window.location.href = apiUrl("/auth/webex/login"))}>
              {webexActionLabel}
            </button>
            <button className="secondary" onClick={() => (window.location.href = apiUrl("/auth/google/login"))}>
              {googleActionLabel}
            </button>
          </div>
        </div>
      </section>
      <section className="panel">
        <h2>환경 변수</h2>
        {data.missing_env.length ? (
          <div className="missing-list">
            {data.missing_env.map((item) => <span key={item}>{item}</span>)}
          </div>
        ) : (
          <p className="muted">필수 환경 변수가 모두 설정되어 있습니다.</p>
        )}
      </section>
    </div>
  );
}

function CandidateMiniList({ candidates }: { candidates: Candidate[] }) {
  if (!candidates.length) return <div className="empty small">최근 후보가 없습니다.</div>;
  return (
    <div className="mini-list">
      {candidates.map((candidate) => (
        <div key={candidate.id}>
          <span className={`badge ${candidate.status}`}>{statusLabels[candidate.status]}</span>
          <strong>{candidate.analysis.title || "제목 미정"}</strong>
          <small>{formatWhen(candidate.analysis)}</small>
        </div>
      ))}
    </div>
  );
}

function StatusChip({ active, label }: { active: boolean; label: string }) {
  return <span className={active ? "chip connected" : "chip disconnected"}>{active ? label : label.replace("connected", "not connected")}</span>;
}

function formatWhen(analysis: Analysis) {
  const date = analysis.date || "날짜 미정";
  const start = analysis.start_time || "시간 미정";
  const end = analysis.end_time ? ` - ${analysis.end_time}` : "";
  return `${date} ${start}${end}`;
}

function actionNotice(status?: string) {
  if (status === "registered") return "Google Calendar에 등록했습니다.";
  if (status === "reanalyzed") return "수정 내용을 반영해 다시 분석했습니다.";
  if (status === "ignored") return "일정 후보를 무시했습니다.";
  if (status === "needs_google") return "Google Calendar 연결이 필요합니다.";
  if (status === "needs_edit") return "날짜/시간이 아직 불명확합니다.";
  return "요청을 처리했습니다.";
}
