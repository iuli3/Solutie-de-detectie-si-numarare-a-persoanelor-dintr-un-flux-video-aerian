import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import axios from "axios";
import {
  Activity, ArrowUpRight, Clock, Crosshair,
  ExternalLink, Search, Trash2, Users, Video,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL;

const fmt = (v) =>
  v
    ? new Date(v).toLocaleString("ro-RO", {
        day: "2-digit", month: "short",
        hour: "2-digit", minute: "2-digit",
      })
    : "–";

const watchPath = (item) => {
  const ext = (item.filename || "").toLowerCase();
  return [".jpg", ".jpeg", ".png", ".webp", ".bmp"].some(e => ext.endsWith(e))
    ? `/watch-image/${item.id}`
    : `/watch/${item.id}`;
};

function StatusPill({ status }) {
  const done = status === "Completed";
  return (
    <span className={`rounded-full px-2 py-0.5 text-[10px] font-black uppercase tracking-[0.12em]
      ${done ? "bg-emerald-500/12 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}>
      {status}
    </span>
  );
}

export default function History() {
  const [loading, setLoading]             = useState(true);
  const [detections, setDetections]       = useState([]);
  const [sessions, setSessions]           = useState([]);
  const [query, setQuery]                 = useState("");
  const [statusFilter, setStatusFilter]   = useState("all");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleting, setDeleting]           = useState(false);

  const handleDeleteSession = async (sessionId) => {
    setDeleting(true);
    try {
      await axios.delete(`${API_URL}/api/tracking-sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      setSessions(prev => prev.filter(s => s.id !== sessionId));
    } catch (err) {
      console.error("[History] Delete session error:", err);
    } finally {
      setDeleting(false);
      setConfirmDeleteId(null);
    }
  };

  useEffect(() => {
    const headers = { Authorization: `Bearer ${localStorage.getItem("token")}` };
    Promise.all([
      axios.get(`${API_URL}/api/dashboard-stats`, { headers }),
      axios.get(`${API_URL}/api/tracking-sessions`, { headers }),
    ])
      .then(([d, t]) => {
        setDetections(d.data?.recent_activity || []);
        setSessions(t.data?.sessions || []);
      })
      .catch(err => console.error("[History]", err))
      .finally(() => setLoading(false));
  }, []);

  const norm = (v) => String(v || "").toLowerCase();

  const filteredDetections = detections.filter(item => {
    const q = norm(query);
    const match = !q || [item.filename, item.status, item.people_count].map(norm).join(" ").includes(q);
    const sf = statusFilter === "all" || norm(item.status) === statusFilter;
    return match && sf;
  });

  const filteredSessions = sessions.filter(s => {
    const camNames = (s.cameras || []).map(c => c.camera_name || c.filename || "").join(" ");
    const q = norm(query);
    const match = !q || [s.id, s.status, s.n_people, camNames].map(norm).join(" ").includes(q);
    const sf = statusFilter === "all" || norm(s.status) === statusFilter;
    return match && sf;
  });

  const totalPeople = detections.reduce((s, i) => s + (Number(i.people_count) || 0), 0);

  return (
    <div className="h-full overflow-y-auto bg-transparent px-4 py-5 text-zinc-100 lg:px-6">
      <div className="mx-auto max-w-[1400px] space-y-5">

        {/* ── page header ─────────────────────────────────── */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-400">
              <Activity size={13} /> History
            </div>
            <h1 className="mt-1.5 text-xl font-bold text-white">Processed media &amp; Re-ID sessions</h1>
          </div>
          {loading && <span className="text-[11px] font-mono text-zinc-600">Loading...</span>}
        </div>

        {/* ── stat chips ──────────────────────────────────── */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            { label: "Detections",       value: detections.length,  accent: "cyan"   },
            { label: "Tracking sessions", value: sessions.length,    accent: "emerald"},
            { label: "People detected",  value: totalPeople,         accent: "violet" },
            { label: "Completed runs",
              value: detections.filter(i => i.status === "Completed").length
                   + sessions.filter(s => s.status === "Completed").length,
              accent: "amber" },
          ].map(({ label, value, accent }) => (
            <div key={label}
              className={`rounded-xl border border-${accent}-500/15 bg-${accent}-500/5 px-4 py-3`}>
              <div className={`text-[10px] font-black uppercase tracking-[0.15em] text-${accent}-400`}>{label}</div>
              <div className="mt-1.5 text-2xl font-bold text-white">{value}</div>
            </div>
          ))}
        </div>

        {/* ── search + filters ────────────────────────────── */}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <label className="flex flex-1 items-center gap-2.5 rounded-xl border border-zinc-800 bg-zinc-950/70 px-4 py-2.5">
            <Search size={14} className="shrink-0 text-zinc-500" />
            <input
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="Search filenames, cameras, IDs…"
              className="w-full bg-transparent text-sm text-zinc-100 outline-none placeholder:text-zinc-600"
            />
          </label>
          <div className="flex gap-1.5 flex-wrap">
            {["all", "completed", "processing", "stopped"].map(opt => (
              <button
                key={opt}
                onClick={() => setStatusFilter(opt)}
                className={`rounded-full border px-3 py-1.5 text-[10px] font-black uppercase tracking-[0.14em] transition
                  ${statusFilter === opt
                    ? "border-emerald-500/30 bg-emerald-500/12 text-emerald-200"
                    : "border-zinc-800 bg-zinc-950/70 text-zinc-500 hover:text-zinc-300"}`}
              >
                {opt}
              </button>
            ))}
          </div>
        </div>

        {/* ── two columns ─────────────────────────────────── */}
        <div className="grid gap-4 xl:grid-cols-2">

          {/* detections */}
          <div className="overflow-hidden rounded-2xl border border-zinc-800/80 bg-zinc-950/40">
            <div className="flex items-center justify-between border-b border-zinc-800/80 px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/10 p-1.5">
                  <Video size={14} className="text-cyan-300" />
                </div>
                <span className="text-sm font-semibold text-white">Detections</span>
              </div>
              <span className="rounded-full border border-cyan-500/15 bg-cyan-500/8 px-2.5 py-0.5 text-[10px] font-mono text-cyan-400">
                {filteredDetections.length} / {detections.length}
              </span>
            </div>

            <div className="max-h-[560px] overflow-y-auto divide-y divide-zinc-900/60">
              {filteredDetections.length === 0 && !loading && (
                <div className="py-14 text-center text-sm text-zinc-600">No detections match.</div>
              )}
              {filteredDetections.map(item => (
                <div key={item.id}
                  className="flex items-center justify-between gap-3 px-5 py-3.5 transition hover:bg-white/[0.025]">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium text-zinc-100">{item.filename}</span>
                      <StatusPill status={item.status} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] font-mono text-zinc-500">
                      <span className="flex items-center gap-1"><Clock size={10} />{fmt(item.created_at)}</span>
                      <span className="flex items-center gap-1"><Users size={10} />{item.people_count ?? 0} people</span>
                      <span className="text-zinc-700">#{item.id}</span>
                    </div>
                  </div>
                  {item.status === "Completed" && (
                    <Link to={watchPath(item)}
                      className="flex-shrink-0 flex items-center gap-1.5 rounded-full border border-cyan-500/20 bg-cyan-500/8
                                 px-3 py-1.5 text-[11px] font-semibold text-cyan-300 transition hover:bg-cyan-500/15">
                      <ExternalLink size={12} /> View
                    </Link>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* tracking sessions */}
          <div className="overflow-hidden rounded-2xl border border-zinc-800/80 bg-zinc-950/40">
            <div className="flex items-center justify-between border-b border-zinc-800/80 px-5 py-3.5">
              <div className="flex items-center gap-2.5">
                <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/10 p-1.5">
                  <Crosshair size={14} className="text-emerald-300" />
                </div>
                <span className="text-sm font-semibold text-white">Tracking sessions</span>
              </div>
              <span className="rounded-full border border-emerald-500/15 bg-emerald-500/8 px-2.5 py-0.5 text-[10px] font-mono text-emerald-400">
                {filteredSessions.length} / {sessions.length}
              </span>
            </div>

            <div className="max-h-[560px] overflow-y-auto divide-y divide-zinc-900/60">
              {filteredSessions.length === 0 && !loading && (
                <div className="py-14 text-center text-sm text-zinc-600">No tracking sessions match.</div>
              )}
              {filteredSessions.map(session => (
                <div key={session.id}
                  className="flex items-start justify-between gap-3 px-5 py-3.5 transition hover:bg-white/[0.025]">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-sm font-semibold text-white">Re-ID Session #{session.id}</span>
                      <StatusPill status={session.status} />
                    </div>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-[10px] font-mono text-zinc-500">
                      <span className="flex items-center gap-1"><Clock size={10} />{fmt(session.started_at)}</span>
                      <span className="flex items-center gap-1"><Users size={10} />{session.n_people ?? 0} global</span>
                      <span className="flex items-center gap-1"><Video size={10} />{session.cameras?.length ?? 0} cameras</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {(session.cameras || []).map(cam => (
                        <span key={cam.id}
                          className="rounded-full border border-zinc-800 bg-zinc-900/60 px-2 py-0.5 text-[9px] font-mono text-zinc-400">
                          {cam.camera_name || cam.filename || `Cam ${cam.camera_order || cam.id}`}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="flex flex-shrink-0 items-center gap-1.5">
                    <Link to={`/tracking-history/${session.id}`}
                      className="flex items-center gap-1.5 rounded-full border border-emerald-500/20 bg-emerald-500/8
                                 px-3 py-1.5 text-[11px] font-semibold text-emerald-300 transition hover:bg-emerald-500/15">
                      Inspect <ArrowUpRight size={12} />
                    </Link>

                    {confirmDeleteId === session.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDeleteSession(session.id)}
                          disabled={deleting}
                          className="rounded-full border border-red-500/40 bg-red-500/15 px-2.5 py-1.5 text-[10px] font-black text-red-300 transition hover:bg-red-500/25 disabled:opacity-50"
                        >
                          {deleting ? "..." : "Confirm"}
                        </button>
                        <button
                          onClick={() => setConfirmDeleteId(null)}
                          className="rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-[10px] font-black text-zinc-400 transition hover:text-white"
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmDeleteId(session.id)}
                        className="rounded-full border border-zinc-800 bg-zinc-900/60 p-1.5 text-zinc-600 transition hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-400"
                        title="Delete session"
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
