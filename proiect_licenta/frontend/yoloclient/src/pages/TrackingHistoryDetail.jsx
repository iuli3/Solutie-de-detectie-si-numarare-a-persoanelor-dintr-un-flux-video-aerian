import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import axios from "axios";
import {
  ArrowLeft, CheckCircle, Clock, Crosshair,
  Loader2, Settings, Trash2, Users, Video, X, Camera,
} from "lucide-react";

const API_URL = import.meta.env.VITE_API_URL;

const CONFIG_LABELS = {
  preset:                  "Preset",
  reid_threshold:          "Re-ID Threshold",
  intra_threshold:         "Intra Threshold",
  max_embeddings:          "Max Embeddings",
  embedding_every_seen:    "Embed Every N Seen",
  min_embeddings_to_match: "Min Embeds to Match",
  recheck_interval:        "Re-Check Interval (s)",
  min_crop_h:              "Min Crop H",
  min_crop_w:              "Min Crop W",
  min_crop_area:           "Min Crop Area",
};

const fmt = (v, opts) =>
  v ? new Date(v).toLocaleString("ro-RO", opts || { dateStyle: "medium", timeStyle: "short" }) : "–";

// ── Person detail modal ───────────────────────────────────────────────────────
function PersonModal({ gid, info, onClose }) {
  if (!gid || !info) return null;

  const color    = info.color || "#888888";
  const cameras  = info.cameras || [];
  const nGallery = info.n_gallery_updates ?? info.n_embeddings ?? 0;
  const nTrack   = info.n_track_embeddings ?? 0;

  const cropHistory = Array.isArray(info.crop_history) && info.crop_history.length > 0
    ? info.crop_history
    : info.best_crop
      ? [{ image: info.best_crop, camera_name: cameras[0], frame_number: null, timestamp_s: null, match_score: null, is_new_person: null }]
      : [];

  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/80 backdrop-blur-md p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        className="relative w-full max-w-3xl overflow-hidden rounded-t-3xl sm:rounded-2xl border border-white/[0.08] bg-[#0f0f12] shadow-[0_32px_80px_rgba(0,0,0,0.7)]"
        style={{ maxHeight: "92vh" }}
        onClick={e => e.stopPropagation()}
      >
        {/* colored top bar */}
        <div className="h-1 w-full" style={{ background: `linear-gradient(90deg, ${color}80, ${color}20)` }} />

        {/* header */}
        <div className="flex items-center justify-between px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-base font-black shadow-lg"
              style={{ background: color, color: "#000", boxShadow: `0 0 20px ${color}50` }}
            >
              {gid}
            </div>
            <div>
              <div className="text-base font-bold text-white">Global Person G{gid}</div>
              <div className="mt-0.5 text-[10px] font-mono text-zinc-500">
                {cameras.length} {cameras.length === 1 ? "camera" : "cameras"}&nbsp;&middot;&nbsp;
                {nGallery} gallery updates&nbsp;&middot;&nbsp;
                {nTrack} track embeddings
              </div>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-full border border-zinc-800 bg-zinc-900 p-2 text-zinc-400 transition hover:border-zinc-600 hover:text-white"
          >
            <X size={14} />
          </button>
        </div>

        {/* body */}
        <div className="overflow-y-auto border-t border-white/[0.06]" style={{ maxHeight: "calc(92vh - 84px)" }}>
          <div className="grid gap-0 md:grid-cols-[200px_1fr]">

            {/* left panel — stats + cameras */}
            <div className="border-b border-white/[0.06] bg-white/[0.02] p-5 space-y-4 md:border-b-0 md:border-r">
              {/* stat list */}
              <div className="space-y-2">
                {[
                  { label: "Global ID",       value: `G${gid}`,   highlight: color },
                  { label: "Gallery updates",  value: nGallery },
                  { label: "Track embeddings", value: nTrack },
                  { label: "Crops saved",      value: cropHistory.length },
                  { label: "Cameras",          value: cameras.length },
                ].map(({ label, value, highlight }) => (
                  <div key={label} className="flex items-center justify-between py-1.5 border-b border-white/[0.04] last:border-0">
                    <span className="text-[11px] text-zinc-500">{label}</span>
                    <span
                      className="text-[11px] font-mono font-bold"
                      style={highlight ? { color: highlight } : { color: "#e4e4e7" }}
                    >
                      {value}
                    </span>
                  </div>
                ))}
              </div>

              {/* cameras */}
              <div>
                <div className="mb-2 text-[9px] font-black uppercase tracking-[0.18em] text-zinc-600">Appeared in</div>
                <div className="flex flex-wrap gap-1.5">
                  {cameras.length > 0 ? cameras.map(cam => (
                    <span
                      key={cam}
                      className="rounded-full px-2.5 py-1 text-[10px] font-semibold"
                      style={{ background: `${color}15`, color, border: `1px solid ${color}30` }}
                    >
                      {cam}
                    </span>
                  )) : <span className="text-[11px] text-zinc-600">–</span>}
                </div>
              </div>
            </div>

            {/* right panel — crop grid */}
            <div className="p-5">
              <div className="mb-4 flex items-center justify-between">
                <span className="text-[10px] font-black uppercase tracking-[0.16em] text-zinc-500">
                  Crop history
                </span>
                <span className="rounded-full bg-white/[0.05] px-2.5 py-0.5 text-[10px] font-mono text-zinc-400">
                  {cropHistory.length} crops
                </span>
              </div>

              {cropHistory.length > 0 ? (
                <div className="grid grid-cols-3 gap-2 sm:grid-cols-4 md:grid-cols-4">
                  {cropHistory.map((crop, idx) => {
                    const score    = Number(crop.match_score);
                    const hasScore = Number.isFinite(score) && score > 0;
                    const isFirst  = crop.is_new_person === true;
                    return (
                      <div
                        key={idx}
                        className="group relative overflow-hidden rounded-xl border bg-black/40 transition hover:scale-[1.02]"
                        style={{ borderColor: `${color}25` }}
                      >
                        <div className="relative" style={{ aspectRatio: "1/2.2" }}>
                          <img
                            src={`data:image/jpeg;base64,${crop.image}`}
                            alt={`G${gid} crop ${idx + 1}`}
                            className="h-full w-full object-cover object-top"
                          />
                          {/* gradient overlay */}
                          <div className="absolute inset-x-0 bottom-0 h-2/5 bg-gradient-to-t from-black/90 to-transparent" />
                          {/* NEW badge */}
                          {isFirst && (
                            <span className="absolute left-1.5 top-1.5 rounded-full bg-emerald-400 px-1.5 py-0.5 text-[8px] font-black text-black">
                              NEW
                            </span>
                          )}
                          {/* bottom meta */}
                          <div className="absolute inset-x-0 bottom-0 p-1.5 space-y-0.5">
                            <div className="truncate text-[9px] font-semibold text-white">
                              {crop.camera_name || `#${idx + 1}`}
                              {crop.track_id != null ? ` T${crop.track_id}` : ""}
                            </div>
                            <div className="flex items-center justify-between text-[8px] font-mono text-zinc-300">
                              {crop.frame_number != null
                                ? <span>F{crop.frame_number}</span>
                                : <span />}
                              {hasScore && (
                                <span style={{ color }}>{Math.round(score * 100)}%</span>
                              )}
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-zinc-800 text-center">
                  <div className="text-xs leading-7 text-zinc-600">
                    No crops saved.<br />
                    <span className="text-zinc-700">Available from next Re-ID session.</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────
export default function TrackingHistoryDetail() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [session, setSession]           = useState(null);
  const [loading, setLoading]           = useState(true);
  const [selectedGid, setSelectedGid]   = useState(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting]         = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await axios.delete(`${API_URL}/api/tracking-sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      });
      navigate("/history");
    } catch (err) {
      console.error("[TrackingHistoryDetail] Delete error:", err);
      setDeleting(false);
      setConfirmDelete(false);
    }
  };

  useEffect(() => {
    axios
      .get(`${API_URL}/api/tracking-sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
      })
      .then(res => setSession(res.data))
      .catch(err => console.error("[TrackingHistoryDetail]", err))
      .finally(() => setLoading(false));
  }, [sessionId]);

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center bg-transparent">
        <Loader2 size={22} className="animate-spin text-zinc-500" />
      </div>
    );
  }
  if (!session) {
    return (
      <div className="h-full bg-transparent p-6 text-sm text-zinc-500">Session not found.</div>
    );
  }

  const people  = Object.entries(session.global_people_summary || {});
  const config  = session.reid_config || {};
  const cfgRows = Object.entries(CONFIG_LABELS)
    .filter(([k]) => config[k] != null)
    .map(([k, label]) => ({ k, label, value: config[k] }));
  const done    = session.status === "Completed";

  return (
    <div className="h-full overflow-y-auto bg-transparent text-zinc-100">

      {/* ── HERO HEADER ─────────────────────────────────── */}
      <div className="relative overflow-hidden border-b border-white/[0.06] bg-gradient-to-br from-[#111116] to-[#0c0c0f] px-6 py-8">
        {/* glow */}
        <div className="pointer-events-none absolute -left-20 -top-20 h-64 w-64 rounded-full bg-emerald-500/10 blur-3xl" />
        <div className="pointer-events-none absolute right-0 top-0 h-40 w-80 rounded-full bg-emerald-500/5 blur-3xl" />

        <div className="relative mx-auto max-w-[1400px]">
          <Link
            to="/history"
            className="mb-5 inline-flex items-center gap-1.5 text-[11px] font-mono text-zinc-500 transition hover:text-emerald-400"
          >
            <ArrowLeft size={12} /> Back to History
          </Link>

          <div className="flex flex-wrap items-end justify-between gap-5">
            <div>
              <div className="flex items-center gap-2 text-[10px] font-black uppercase tracking-[0.22em] text-emerald-400">
                <Crosshair size={13} /> Re-ID Session
              </div>
              <h1 className="mt-2 text-3xl font-black text-white">
                Session&nbsp;
                <span className="bg-gradient-to-r from-emerald-300 to-emerald-500 bg-clip-text text-transparent">
                  #{session.id}
                </span>
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] font-mono text-zinc-400">
                  <Clock size={11} /> {fmt(session.started_at)}
                </span>
                {session.completed_at && (
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.08] bg-white/[0.04] px-3 py-1.5 text-[11px] font-mono text-zinc-400">
                    <Clock size={11} /> {fmt(session.completed_at)}
                  </span>
                )}
              </div>
            </div>

            {/* right stat pills + delete */}
            <div className="flex flex-wrap items-start gap-3">
              <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-5 py-3 text-center">
                <div className="text-2xl font-black text-emerald-300">{session.n_people}</div>
                <div className="mt-0.5 text-[10px] font-mono text-emerald-500">people identified</div>
              </div>
              <div className="rounded-2xl border border-cyan-500/20 bg-cyan-500/8 px-5 py-3 text-center">
                <div className="text-2xl font-black text-cyan-300">{(session.cameras || []).length}</div>
                <div className="mt-0.5 text-[10px] font-mono text-cyan-500">cameras</div>
              </div>
              <div className={`rounded-2xl border px-5 py-3 text-center ${
                done
                  ? "border-emerald-500/25 bg-emerald-500/10"
                  : "border-yellow-500/20 bg-yellow-500/8"
              }`}>
                <div className={`flex items-center gap-1.5 text-sm font-black ${done ? "text-emerald-300" : "text-yellow-300"}`}>
                  {done ? <CheckCircle size={15} /> : <Loader2 size={15} className="animate-spin" />}
                  {session.status}
                </div>
                <div className={`mt-0.5 text-[10px] font-mono ${done ? "text-emerald-600" : "text-yellow-600"}`}>status</div>
              </div>

              {/* delete button */}
              {confirmDelete ? (
                <div className="flex flex-col items-center gap-1.5 rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3">
                  <span className="text-[10px] font-black text-red-300 uppercase tracking-widest">Delete session?</span>
                  <div className="flex gap-1.5">
                    <button
                      onClick={handleDelete}
                      disabled={deleting}
                      className="rounded-lg border border-red-500/40 bg-red-500/20 px-3 py-1 text-[10px] font-black text-red-300 transition hover:bg-red-500/30 disabled:opacity-50"
                    >
                      {deleting ? "Deleting..." : "Confirm"}
                    </button>
                    <button
                      onClick={() => setConfirmDelete(false)}
                      className="rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-1 text-[10px] font-black text-zinc-400 transition hover:text-white"
                    >
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDelete(true)}
                  className="self-start rounded-2xl border border-zinc-800 bg-zinc-900/60 px-4 py-3 text-zinc-600 transition hover:border-red-500/30 hover:bg-red-500/8 hover:text-red-400"
                  title="Delete session"
                >
                  <Trash2 size={18} />
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      <div className="mx-auto max-w-[1400px] space-y-8 px-6 py-7">

        {/* ── IDENTIFIED PEOPLE ───────────────────────────── */}
        <section>
          <div className="mb-4 flex items-center gap-3">
            <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-zinc-400">
              <Users size={13} /> Identified People
            </div>
            <div className="h-px flex-1 bg-white/[0.05]" />
            <span className="rounded-full border border-emerald-500/20 bg-emerald-500/8 px-3 py-1 text-[10px] font-mono text-emerald-400">
              {people.length}
            </span>
          </div>

          {people.length === 0 ? (
            <div className="flex h-48 items-center justify-center rounded-2xl border border-dashed border-zinc-800 text-sm text-zinc-600">
              No global people saved for this session.
            </div>
          ) : (
            <div className="grid gap-3 grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8">
              {people.map(([gid, info]) => {
                const color    = info.color || "#888888";
                const cameras  = info.cameras || [];
                const nEmb     = info.n_gallery_updates ?? info.n_embeddings ?? 0;
                const crop     = info.best_crop;
                const nCrops   = Array.isArray(info.crop_history) ? info.crop_history.length : (crop ? 1 : 0);

                return (
                  <button
                    key={gid}
                    onClick={() => setSelectedGid(gid)}
                    className="group relative overflow-hidden rounded-2xl border border-white/[0.07] bg-zinc-900/50 text-left
                               transition duration-200 hover:border-white/[0.15] hover:shadow-[0_8px_32px_rgba(0,0,0,0.4)] hover:-translate-y-0.5"
                    style={{ boxShadow: `0 0 0 0 ${color}00` }}
                  >
                    {/* image area */}
                    <div className="relative bg-zinc-900" style={{ aspectRatio: "2/3" }}>
                      {crop ? (
                        <img
                          src={`data:image/jpeg;base64,${crop}`}
                          alt={`G${gid}`}
                          className="h-full w-full object-cover object-top transition duration-300 group-hover:scale-[1.04]"
                        />
                      ) : (
                        <div className="flex h-full w-full items-center justify-center">
                          <Users size={28} className="text-zinc-700" />
                        </div>
                      )}

                      {/* gradient overlay bottom */}
                      <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black via-black/50 to-transparent" />

                      {/* color accent line top */}
                      <div className="absolute inset-x-0 top-0 h-0.5" style={{ background: color }} />

                      {/* ID badge top-left */}
                      <div
                        className="absolute left-2 top-3 flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-black text-black shadow"
                        style={{ background: color }}
                      >
                        G{gid}
                      </div>

                      {/* crops count top-right */}
                      {nCrops > 0 && (
                        <div className="absolute right-2 top-3 rounded-full bg-black/60 px-1.5 py-0.5 text-[9px] font-mono text-zinc-300 backdrop-blur-sm">
                          {nCrops} crops
                        </div>
                      )}

                      {/* bottom info */}
                      <div className="absolute inset-x-0 bottom-0 p-2.5">
                        <div className="flex flex-wrap gap-1">
                          {cameras.slice(0, 2).map(cam => (
                            <span
                              key={cam}
                              className="rounded-full px-1.5 py-0.5 text-[8px] font-semibold"
                              style={{ background: `${color}30`, color }}
                            >
                              {cam}
                            </span>
                          ))}
                          {cameras.length > 2 && (
                            <span className="rounded-full bg-white/10 px-1.5 py-0.5 text-[8px] text-zinc-400">
                              +{cameras.length - 2}
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-[9px] font-mono text-zinc-400">
                          {nEmb} gallery upd.
                        </div>
                      </div>

                      {/* hover overlay */}
                      <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity group-hover:opacity-100" style={{ background: `${color}12` }}>
                        <span className="rounded-full bg-black/60 px-3 py-1 text-[10px] font-semibold text-white backdrop-blur-sm">
                          View details
                        </span>
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* ── CAMERAS + CONFIG ────────────────────────────── */}
        <div className="grid gap-5 xl:grid-cols-[1fr_280px]">

          {/* cameras */}
          <section>
            <div className="mb-4 flex items-center gap-3">
              <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-zinc-400">
                <Camera size={13} /> Cameras
              </div>
              <div className="h-px flex-1 bg-white/[0.05]" />
              <span className="rounded-full border border-cyan-500/20 bg-cyan-500/8 px-3 py-1 text-[10px] font-mono text-cyan-400">
                {(session.cameras || []).length}
              </span>
            </div>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              {(session.cameras || []).map(cam => (
                <div
                  key={cam.id}
                  className="group relative overflow-hidden rounded-2xl border border-white/[0.07] bg-zinc-900/40 p-4 transition hover:border-white/[0.12]"
                >
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-cyan-500/40 via-cyan-500/10 to-transparent" />
                  <div className="flex items-start gap-3">
                    <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/10 p-2 flex-shrink-0">
                      <Video size={14} className="text-cyan-400" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-bold text-zinc-100">
                          {cam.camera_name || `Camera ${cam.camera_order || cam.id}`}
                        </span>
                        {cam.camera_order != null && (
                          <span className="flex-shrink-0 rounded-full border border-zinc-700 bg-zinc-900 px-1.5 py-0.5 text-[9px] font-mono text-zinc-500">
                            #{cam.camera_order}
                          </span>
                        )}
                      </div>
                      <div className="mt-2 space-y-1 text-[10px] font-mono">
                        <div className="truncate text-zinc-500">
                          <span className="text-zinc-600">file: </span>{cam.filename || "–"}
                        </div>
                        <div className="text-zinc-500">
                          <span className="text-zinc-600">video_id: </span>{cam.video_id}
                        </div>
                      </div>
                      <div className="mt-2.5 flex items-center gap-1.5">
                        <span className={`h-1.5 w-1.5 rounded-full ${cam.status === "Completed" ? "bg-emerald-400" : "bg-yellow-400 animate-pulse"}`} />
                        <span className={`text-[10px] font-mono font-semibold ${cam.status === "Completed" ? "text-emerald-400" : "text-yellow-400"}`}>
                          {cam.status}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* config */}
          {cfgRows.length > 0 && (
            <section>
              <div className="mb-4 flex items-center gap-3">
                <div className="flex items-center gap-2 text-[11px] font-black uppercase tracking-[0.18em] text-zinc-400">
                  <Settings size={13} /> Config
                </div>
                <div className="h-px flex-1 bg-white/[0.05]" />
                {config.preset && (
                  <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2.5 py-1 text-[9px] font-mono font-bold text-zinc-400 uppercase">
                    {config.preset}
                  </span>
                )}
              </div>
              <div className="overflow-hidden rounded-2xl border border-white/[0.07] bg-zinc-900/40">
                <div className="divide-y divide-white/[0.04]">
                  {cfgRows.map(({ k, label, value }) => (
                    <div key={k} className="flex items-center justify-between px-4 py-2.5">
                      <span className="text-[11px] text-zinc-500">{label}</span>
                      <span className="text-[11px] font-mono font-bold text-zinc-200">
                        {typeof value === "boolean" ? (value ? "yes" : "no") : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

        </div>
      </div>

      {/* ── MODAL ─────────────────────────────────────────── */}
      {selectedGid && (
        <PersonModal
          gid={selectedGid}
          info={(session.global_people_summary || {})[selectedGid]}
          onClose={() => setSelectedGid(null)}
        />
      )}
    </div>
  );
}
