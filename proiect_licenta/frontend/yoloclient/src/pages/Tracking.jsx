import { useState, useRef, useEffect, useCallback } from "react";
import { Link } from "react-router-dom";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL;
import {
  Crosshair, Plus, X, Maximize2, Minimize2,
  Users, Video, Settings, ChevronRight, Square, RotateCcw, Database, Minus
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { useProcessing } from "../contexts/ProcessingContext";

const BALANCED_REID_PRESET = {
  preset: "balanced",
  enable_reid_embeddings: true,
  emit_debug_info: true,
  max_embeddings: 6,
  embedding_every_seen: 4,
  min_embeddings_to_match: 2,
  recheck_interval: 8,
  reid_threshold: 0.75,
  intra_threshold: 0.55,
  min_crop_h: 50,
  min_crop_w: 18,
  min_crop_area: 1200,
};

const STRICT_REID_PRESET = {
  preset: "strict",
  enable_reid_embeddings: true,
  emit_debug_info: true,
  max_embeddings: 8,
  embedding_every_seen: 4,
  min_embeddings_to_match: 3,
  recheck_interval: 8,
  reid_threshold: 0.82,
  intra_threshold: 0.65,
  min_crop_h: 60,
  min_crop_w: 20,
  min_crop_area: 1600,
};

const SENSITIVE_REID_PRESET = {
  preset: "sensitive",
  enable_reid_embeddings: true,
  emit_debug_info: true,
  max_embeddings: 6,
  embedding_every_seen: 3,
  min_embeddings_to_match: 2,
  recheck_interval: 6,
  reid_threshold: 0.68,
  intra_threshold: 0.45,
  min_crop_h: 40,
  min_crop_w: 15,
  min_crop_area: 800,
};

const REID_PRESETS = {
  balanced: BALANCED_REID_PRESET,
  strict: STRICT_REID_PRESET,
  sensitive: SENSITIVE_REID_PRESET,
};

const REID_NUMERIC_FIELDS = [
  "max_embeddings",
  "embedding_every_seen",
  "min_embeddings_to_match",
  "recheck_interval",
  "reid_threshold",
  "intra_threshold",
  "min_crop_h",
  "min_crop_w",
  "min_crop_area",
];

// ── Global ID colors ──────────────────────────────────────────────────────────
const GLOBAL_ID_COLORS = {
  1: "#22c55e", 2: "#ef4444", 3: "#f97316", 4: "#a855f7",
  5: "#06b6d4", 6: "#eab308", 7: "#ec4899", 8: "#14b8a6",
};
const getColor = (gid) => GLOBAL_ID_COLORS[Number(gid)] || "#888888";

const hasDetectionValue = (value) => value != null && value !== "";

const getDetectionLabel = (det = {}) => {
  if (hasDetectionValue(det.label)) return String(det.label);
  if (hasDetectionValue(det.global_id)) return `G${det.global_id}`;
  if (hasDetectionValue(det.track_id)) return `T${det.track_id}`;
  const detectionIndex = Number(det.detection_index ?? 0);
  return `D${(Number.isFinite(detectionIndex) ? detectionIndex : 0) + 1}`;
};

const getDetectionStatus = (det = {}) => {
  if (hasDetectionValue(det.global_id)) return "identified";
  if (hasDetectionValue(det.track_id)) return "tracking";
  return "detected";
};

const getDetectionKey = (det = {}, idx = 0, fallback = {}) => {
  const cameraKey = det.video_id ?? fallback.video_id ?? det.camera_name ?? fallback.camera_name ?? "cam";
  if (hasDetectionValue(det.global_id)) return `${cameraKey}-global-${det.global_id}`;
  if (hasDetectionValue(det.track_id)) return `${cameraKey}-track-${det.track_id}`;
  if (hasDetectionValue(det.detection_index)) return `${cameraKey}-det-${det.detection_index}`;
  return `${cameraKey}-det-${idx}`;
};

const getDebugDetectionKey = (det = {}, idx = 0, fallback = {}) => {
  const cameraKey = det.video_id ?? fallback.video_id ?? det.camera_name ?? fallback.camera_name ?? "cam";
  if (hasDetectionValue(det.track_id)) return `${cameraKey}-track-${det.track_id}`;
  if (hasDetectionValue(det.global_id)) return `${cameraKey}-global-${det.global_id}`;
  if (hasDetectionValue(det.detection_index)) return `${cameraKey}-det-${det.detection_index}`;
  return `${cameraKey}-det-${idx}`;
};

const getDetectionRect = (det = {}) => {
  if (Array.isArray(det.bbox_xywh) && det.bbox_xywh.length >= 4) {
    const [xRaw, yRaw, wRaw, hRaw] = det.bbox_xywh;
    const x = Number(xRaw);
    const y = Number(yRaw);
    const width = Number(wRaw);
    const height = Number(hRaw);
    if ([x, y, width, height].every(Number.isFinite) && width > 0 && height > 0) {
      return { x, y, width, height };
    }
  }

  if (Array.isArray(det.bbox) && det.bbox.length >= 4) {
    const [x1Raw, y1Raw, x2Raw, y2Raw] = det.bbox;
    const x1 = Number(x1Raw);
    const y1 = Number(y1Raw);
    const x2 = Number(x2Raw);
    const y2 = Number(y2Raw);
    if ([x1, y1, x2, y2].every(Number.isFinite) && x2 > x1 && y2 > y1) {
      return { x: x1, y: y1, width: x2 - x1, height: y2 - y1 };
    }
  }

  return null;
};

const getDetectionColor = (det = {}) => {
  if (det.color) return det.color;
  if (hasDetectionValue(det.global_id)) return getColor(det.global_id);
  if (hasDetectionValue(det.track_id)) return "#34d399";
  return "#888888";
};

// ── StatusBadge ───────────────────────────────────────────────────────────────
function StatusBadge({ status }) {
  const configs = {
    uploading:  { bg: "bg-orange-500/15", border: "border-orange-500/30", text: "text-orange-300", dot: "bg-orange-400 animate-pulse", label: "Upload..." },
    error:      { bg: "bg-red-500/15",    border: "border-red-500/30",    text: "text-red-300",    dot: "bg-red-400",                  label: "Eroare" },
    warmup:     { bg: "bg-yellow-500/15", border: "border-yellow-500/30", text: "text-yellow-300", dot: "bg-yellow-400 animate-pulse", label: "Warmup" },
    processing: { bg: "bg-emerald-500/15",border: "border-emerald-500/30",text: "text-emerald-300",dot: "bg-emerald-400 animate-pulse", label: "Live" },
    done:       { bg: "bg-blue-500/15",   border: "border-blue-500/30",   text: "text-blue-300",   dot: "bg-blue-400",                  label: "Done" },
    ready:      { bg: "bg-zinc-700/50",   border: "border-zinc-600/30",   text: "text-zinc-400",   dot: "bg-zinc-500",                  label: "Ready" },
  };
  const c = configs[status] || configs.ready;
  return (
    <span className={`flex items-center gap-1 px-2 py-0.5 rounded-full ${c.bg} border ${c.border} ${c.text} text-[10px] font-mono uppercase tracking-wider`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />
      {c.label}
    </span>
  );
}

// ── PersonToast ───────────────────────────────────────────────────────────────
function PersonToast({ toast }) {
  const color = getColor(toast.global_id);
  return (
    <div
      className="absolute bottom-8 left-2 z-30 flex items-center gap-2 rounded-md px-2 py-1.5"
      style={{ background: "rgba(8,8,8,0.95)", border: `0.5px solid ${color}40`, boxShadow: `0 0 12px ${color}20` }}
    >
      {toast.best_crop ? (
        <img src={`data:image/jpeg;base64,${toast.best_crop}`} alt="" className="w-6 h-11 object-cover rounded-sm flex-shrink-0" style={{ border: `1px solid ${color}60` }} />
      ) : (
        <div className="w-6 h-11 rounded-sm flex-shrink-0" style={{ background: `${color}15`, border: `1px solid ${color}40` }} />
      )}
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold flex-shrink-0" style={{ background: color, color: Number(toast.global_id) <= 2 ? "#000" : "#fff" }}>
            {toast.global_id}
          </div>
          <span className="text-[10px] font-mono font-semibold text-white">
            {toast.is_new_person ? "Persoană nouă" : `Re-ID G${toast.global_id}`}
          </span>
        </div>
        <div className="text-[9px] font-mono text-zinc-500 mt-0.5">
          {toast.camera_name}
          {toast.match_score > 0 && <span className="ml-1.5" style={{ color }}>{Math.round(toast.match_score * 100)}%</span>}
        </div>
        {toast.match_score > 0 && (
          <div className="w-full h-0.5 bg-zinc-800 rounded-full mt-1 overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${Math.round(toast.match_score * 100)}%`, background: color }} />
          </div>
        )}
      </div>
    </div>
  );
}

// ── ReidOverlay — canvas care deseneaza bbox-urile Re-ID peste stream ─────────
function ReidOverlay({ detections, frameWidth = 1280, frameHeight = 720 }) {
  const overlayRef = useRef(null);
  const [overlaySize, setOverlaySize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const node = overlayRef.current;
    if (!node) return;

    const updateSize = () => {
      const rect = node.getBoundingClientRect();
      setOverlaySize({ width: rect.width, height: rect.height });
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const originalW = Number(frameWidth) || 1280;
  const originalH = Number(frameHeight) || 720;
  const frameAspect = originalW / originalH;
  const overlayAspect = overlaySize.width && overlaySize.height
    ? overlaySize.width / overlaySize.height
    : frameAspect;
  const displayedWidth = overlayAspect > frameAspect
    ? overlaySize.height * frameAspect
    : overlaySize.width;
  const displayedHeight = overlayAspect > frameAspect
    ? overlaySize.height
    : overlaySize.width / frameAspect;
  const offsetX = (overlaySize.width - displayedWidth) / 2;
  const offsetY = (overlaySize.height - displayedHeight) / 2;
  const scaleX = displayedWidth / originalW;
  const scaleY = displayedHeight / originalH;

  return (
    <div ref={overlayRef} className="absolute inset-0 pointer-events-none" style={{ zIndex: 30 }}>
      {(detections || []).map((det, idx) => {
        const rect = getDetectionRect(det);
        if (!rect) return null;

        const width = rect.width * scaleX;
        const height = rect.height * scaleY;
        if (width <= 0 || height <= 0) return null;

        const label = getDetectionLabel(det);
        const color = getDetectionColor(det);

        return (
          <div
            key={getDetectionKey(det, idx)}
            className="absolute rounded-sm border-2 shadow-[0_0_14px_rgba(52,211,153,0.35)]"
            style={{
              left: offsetX + rect.x * scaleX,
              top: offsetY + rect.y * scaleY,
              width,
              height,
              borderColor: color,
              zIndex: 30,
            }}
          >
            <div
              className="absolute left-0 top-0 -translate-y-full rounded-t-sm px-1.5 py-0.5 text-[10px] font-black leading-none text-black"
              style={{ backgroundColor: color }}
            >
              {label}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── CameraCell ────────────────────────────────────────────────────────────────
function CameraCell({ video, index, isExpanded, onExpand, onRemove, reidDetections }) {
  const status = video.isUploading
    ? "uploading"
    : video.uploadError ? "error"
    : video.isProcessing ? (video.frameInfo?.progress < 5 ? "warmup" : "processing")
    : video.results ? "done"
    : "ready";

  const activeToast  = video.activeToast || null;
  const cameraKey = video.backendVideoId != null ? String(video.backendVideoId) : video.cameraName;
  const camDetections =
    video.reidDetections ||
    reidDetections?.[cameraKey]?.detections ||
    reidDetections?.[String(video.id)]?.detections ||
    reidDetections?.[video.cameraName]?.detections ||
    reidDetections?.[String(video.cameraOrder)]?.detections ||
    reidDetections?.[String(index)]?.detections ||
    reidDetections?.[String(index + 1)]?.detections ||
    [];
  const liveDetectedCount = camDetections.length > 0
    ? camDetections.length
    : video.frameInfo?.detectedPeopleCount ?? video.frameInfo?.peopleCount ?? 0;
  const liveIdentifiedCount = camDetections.length > 0
    ? new Set(camDetections.map(det => det.global_id).filter(gid => gid != null && gid !== "")).size
    : video.frameInfo?.identifiedPeopleCount ?? (video.globalIds || []).length ?? 0;
  const liveFrameNumber = video.frameInfo?.frameNumber ?? "-";
  const liveProgress = Number(video.frameInfo?.progress ?? 0);
  const hasLiveStats = Boolean(video.frameInfo) || camDetections.length > 0;

  return (
    <div className="relative w-full h-full bg-black group overflow-hidden">
      {/* Frame stream detection */}
      {video.streamFrame ? (
  <img
    src={video.streamFrame}
    alt={video.cameraName}
    className="w-full h-full object-contain"
    style={{ imageRendering: "auto" }}
  />
) : (
  <video
    src={video.src}
    className="w-full h-full object-contain opacity-80"
    muted
    playsInline
    autoPlay
    loop
  />
)}

      {!video.streamFrame && (
        <div className="absolute bottom-2 left-2 right-2 z-10 flex justify-center pointer-events-none">
          <span className="rounded bg-black/75 border border-yellow-500/25 px-2 py-1 text-[10px] font-mono text-yellow-200">
            Preview local — se așteaptă frame-uri procesate de pe cluster
          </span>
        </div>
      )}

      {/* Canvas overlay Re-ID bbox-uri */}
      {camDetections.length > 0 && (
        <ReidOverlay
          detections={camDetections}
          frameWidth={video.frameSize?.w || 1280}
          frameHeight={video.frameSize?.h || 720}
        />
      )}

      {/* Scanline */}
      <div className="absolute inset-0 pointer-events-none" style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.03) 2px, rgba(0,0,0,0.03) 4px)" }} />

      {/* Top bar */}
      <div className="absolute top-0 left-0 right-0 flex items-center justify-between px-2 py-1.5 bg-gradient-to-b from-black/80 to-transparent" style={{ zIndex: 10 }}>
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[9px] text-emerald-300 bg-black/60 border border-emerald-500/30 px-1.5 py-0.5 rounded">
            CAM {String(video.cameraOrder || index + 1).padStart(2, "0")}
          </span>
          <span className="text-[9px] text-gray-400 truncate max-w-[100px]">{video.cameraName}</span>
          <StatusBadge status={status} />
          {video.backendVideoId && !video.isUploading && (
            <span className="text-[8px] font-mono text-blue-400/80 border border-blue-500/20 px-1 py-0.5 rounded leading-none">DB</span>
          )}
          {video.serverDownloadStatus === 'downloading' && (
            <span className="text-[9px] font-mono text-yellow-400 animate-pulse leading-none" title="Descărcare pe server">↓</span>
          )}
          {video.serverDownloadStatus === 'ready' && (
            <span className="text-[9px] font-mono text-emerald-400 leading-none" title="Gata pe server">↓✓</span>
          )}
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <button onClick={() => onExpand(video.id)} className="p-1 rounded bg-black/60 hover:bg-white/10 text-gray-300 transition">
            {isExpanded ? <Minimize2 size={9} /> : <Maximize2 size={9} />}
          </button>
          <button onClick={() => onRemove(video.id)} disabled={video.isProcessing} className="p-1 rounded bg-black/60 hover:bg-red-500/80 text-gray-400 hover:text-white disabled:opacity-30 transition">
            <X size={9} />
          </button>
        </div>
      </div>

      {/* Global ID chips */}
      {video.globalIds && video.globalIds.length > 0 && (
        <div className="absolute top-8 right-1.5 flex flex-col gap-1" style={{ zIndex: 10 }}>
          {[...new Set(video.globalIds)].slice(0, 6).map(gid => (
            <div key={gid} className="w-4 h-4 rounded-full flex items-center justify-center text-[8px] font-bold shadow-lg" style={{ background: getColor(gid), color: Number(gid) <= 2 ? "#000" : "#fff" }}>
              {gid}
            </div>
          ))}
        </div>
      )}

      {/* Toast */}
      {activeToast && <PersonToast toast={activeToast} />}

      {/* Camera prepare progress overlay */}
      {video.isUploading && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-black/80 z-30 pointer-events-none">
          <Database size={18} className="text-blue-400" />
          <div className="text-[11px] text-white font-mono font-semibold tracking-wide">Uploading to DB</div>
          <div className="w-2/3 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div
              className="h-full bg-blue-500 rounded-full transition-all duration-200"
              style={{ width: `${video.uploadProgress || 0}%` }}
            />
          </div>
          <div className="text-[9px] text-zinc-400 font-mono">{video.uploadProgress || 0}%</div>
        </div>
      )}

      {/* Bottom stats */}
      {hasLiveStats && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/90 to-transparent px-2 py-1.5" style={{ zIndex: 10 }}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div>
                <div className="text-[8px] text-gray-500 uppercase tracking-wider">Frame</div>
                <div className="text-[10px] font-mono text-white">{liveFrameNumber}</div>
              </div>
              <div>
                <div className="text-[8px] text-gray-500 uppercase tracking-wider">Detected</div>
                <div className="text-[10px] font-mono text-emerald-400">
                  {liveDetectedCount}
                </div>
              </div>
              <div>
                <div className="text-[8px] text-gray-500 uppercase tracking-wider">Identified</div>
                <div className="text-[10px] font-mono text-cyan-300">
                  {liveIdentifiedCount}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-1.5">
              <div className="w-16 h-0.5 bg-zinc-800 rounded-full overflow-hidden">
                <div className="h-full bg-emerald-500 rounded-full transition-all" style={{ width: `${liveProgress}%` }} />
              </div>
              <span className="text-[8px] font-mono text-gray-500">{liveProgress}%</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── GlobalPeopleSidebar ───────────────────────────────────────────────────────
function GlobalPeopleSidebar({ people, isVisible, onSelectPerson }) {
  if (!isVisible) return null;
  const entries = Object.entries(people);

  return (
    <div className="w-56 flex-shrink-0 bg-zinc-950/95 border-l border-zinc-800/70 flex flex-col overflow-hidden">
      <div className="px-3 py-2.5 border-b border-zinc-800/70 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-2">
          <Users size={11} className="text-emerald-400" />
          <span className="text-[11px] font-semibold text-white tracking-wide">Persoane identificate</span>
        </div>
        <span className="text-[10px] font-mono text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">{entries.length}</span>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {entries.length === 0 && (
          <div className="flex flex-col items-center justify-center py-8 text-zinc-700">
            <Users size={18} className="mb-2" />
            <p className="text-[10px] font-mono text-center">Nicio persoană<br />identificată încă</p>
          </div>
        )}

        {entries.map(([gid, info]) => {
          const color = getColor(gid);
          const score = Number(info.match_score);
          const hasScore = Number.isFinite(score);
          const isNew = info.is_new_person ?? false;
          const scoreText = hasScore ? (isNew ? "ID nou" : `${Math.round(score * 100)}%`) : "-";

          return (
            <button
              key={gid}
              type="button"
              onClick={() => onSelectPerson?.(gid)}
              className="w-full text-left rounded-lg overflow-hidden hover:bg-zinc-900/80 transition"
              style={{ background: "#0d0d0d", border: `0.5px solid ${color}25` }}
            >
              <div className="flex items-center gap-2 px-2 py-1.5" style={{ borderBottom: `0.5px solid ${color}15` }}>
                <div className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold flex-shrink-0" style={{ background: color, color: Number(gid) <= 2 ? "#000" : "#fff" }}>
                  {gid}
                </div>
                <div className="flex-1 min-w-0 flex items-center justify-between">
                  <span className="text-[11px] font-mono font-semibold text-white">G{gid}</span>
                  {isNew && <span className="text-[8px] font-mono px-1 py-0.5 rounded" style={{ background: `${color}20`, color }}>NOU</span>}
                </div>
              </div>

              <div className="px-2 py-1.5 flex gap-2">
                <div className="flex-shrink-0">
                  {info.best_crop ? (
                    <img src={`data:image/jpeg;base64,${info.best_crop}`} alt="" className="w-8 h-14 object-cover rounded" style={{ border: `1px solid ${color}40` }} />
                  ) : (
                    <div className="w-8 h-14 rounded flex items-center justify-center" style={{ background: `${color}10`, border: `1px solid ${color}25` }}>
                      <Users size={10} style={{ color: `${color}60` }} />
                    </div>
                  )}
                </div>

                <div className="flex-1 min-w-0 flex flex-col justify-between">
                  <div>
                    <div className="text-[8px] text-zinc-600 uppercase tracking-wider mb-1">Camere</div>
                    <div className="flex flex-wrap gap-1">
                      {(info.cameras || []).map(cam => (
                        <span key={cam} className="text-[8px] font-mono px-1 py-0.5 rounded" style={{ background: `${color}15`, color }}>{cam}</span>
                      ))}
                    </div>
                  </div>
                  <div className="mt-1.5">
                    <div className="flex items-center justify-between mb-0.5">
                      <span className="text-[8px] text-zinc-600 uppercase tracking-wider">Similaritate</span>
                      <span className="text-[9px] font-mono" style={{ color }}>{scoreText}</span>
                    </div>
                    {hasScore && !isNew && (
                      <div className="w-full h-0.5 bg-zinc-800 rounded-full overflow-hidden">
                        <div className="h-full rounded-full" style={{ width: `${Math.round(score * 100)}%`, background: color }} />
                      </div>
                    )}
                  </div>
                  <div className="text-[8px] text-zinc-700 font-mono mt-1">{info.n_embeddings ?? 0} embeddings</div>
                </div>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

function GlobalPersonModal({ gid, info, onClose }) {
  if (!gid || !info) return null;
  const color = getColor(gid);
  const crops = info.crop_history?.length
    ? info.crop_history
    : info.best_crop
      ? [{ image: info.best_crop, camera_name: info.cameras?.[0], timestamp_ms: info.last_seen_ms }]
      : [];
  const score = Number(info.match_score);
  const hasScore = Number.isFinite(score);
  const scoreLabel = hasScore
    ? (info.is_new_person ? "ID nou creat" : `${Math.round(score * 100)}% similaritate`)
    : "scor indisponibil";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={onClose}>
      <div
        className="w-full max-w-3xl max-h-[82vh] overflow-hidden rounded-lg bg-zinc-950 border border-zinc-800 shadow-2xl"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold" style={{ background: color, color: Number(gid) <= 2 ? "#000" : "#fff" }}>
              {gid}
            </div>
            <div>
              <div className="text-sm font-semibold text-white">Persoana globala G{gid}</div>
              <div className="text-[10px] font-mono text-zinc-500">
                {(info.cameras || []).length} camere · {info.n_embeddings ?? 0} embeddings · {scoreLabel}
              </div>
            </div>
          </div>
          <button onClick={onClose} className="p-1.5 rounded bg-zinc-900 hover:bg-zinc-800 text-zinc-400 hover:text-white">
            <X size={16} />
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[220px_1fr] gap-4 p-4 overflow-y-auto max-h-[calc(82vh-58px)]">
          <div className="space-y-3">
            <div className="rounded-lg border border-zinc-800 bg-black/30 p-3">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Camere</div>
              <div className="flex flex-wrap gap-1.5">
                {(info.cameras || []).map(cam => (
                  <span key={cam} className="text-[10px] font-mono px-2 py-1 rounded" style={{ background: `${color}18`, color }}>{cam}</span>
                ))}
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-black/30 p-3 text-[11px] font-mono text-zinc-400 space-y-1.5">
              <div className="flex justify-between"><span>Global ID</span><span style={{ color }}>G{gid}</span></div>
              <div className="flex justify-between"><span>Match score</span><span>{scoreLabel}</span></div>
              <div className="flex justify-between"><span>Embeddings</span><span>{info.n_embeddings ?? 0}</span></div>
              <div className="flex justify-between"><span>Status</span><span>{info.is_new_person ? "Nou" : "Re-identificat"}</span></div>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Crop-uri primite</div>
              <div className="text-[10px] font-mono text-zinc-600">{crops.length}</div>
            </div>
            {crops.length ? (
              <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-2">
                {crops.map((crop, idx) => {
                  const cropScore = Number(crop.match_score);
                  const cropCandidate = Number(crop.candidate_score);
                  const cropThreshold = Number(crop.reid_threshold);
                  const bboxArea = Number(crop.bbox_area);
                  return (
                    <div key={`${crop.timestamp_ms || idx}-${idx}`} className="rounded border border-zinc-800 bg-black/40 p-1">
                      <img src={`data:image/jpeg;base64,${crop.image || crop}`} alt={`G${gid} crop ${idx + 1}`} className="w-full aspect-[1/2] object-cover rounded-sm" style={{ border: `1px solid ${color}30` }} />
                      <div className="mt-1 space-y-0.5 text-[8px] font-mono text-zinc-500">
                        <div className="truncate text-zinc-300">{crop.camera_name || `crop ${idx + 1}`} {crop.track_id != null ? `· T${crop.track_id}` : ""}</div>
                        <div className="truncate">F{crop.frame_number ?? "-"} {crop.timestamp_s != null ? `· ${Number(crop.timestamp_s).toFixed(1)}s` : ""}</div>
                        <div className="truncate">
                          sim {Number.isFinite(cropScore) ? cropScore.toFixed(3) : "-"}
                          {Number.isFinite(cropCandidate) ? ` · cand ${cropCandidate.toFixed(3)}` : ""}
                          {Number.isFinite(cropThreshold) ? ` / ${cropThreshold.toFixed(2)}` : ""}
                        </div>
                        <div className="truncate">
                          {crop.source || "assign"}
                          {crop.previous_global_id ? ` · G${crop.previous_global_id}->G${gid}` : ""}
                          {Number.isFinite(bboxArea) ? ` · ${Math.round(bboxArea)}px` : ""}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="h-40 rounded-lg border border-dashed border-zinc-800 flex items-center justify-center text-xs text-zinc-600">
                Nu au venit crop-uri pentru persoana asta.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── CameraConfigDrawer ────────────────────────────────────────────────────────
function CameraConfigDrawer({ video, onClose, onMetaChange }) {
  if (!video) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative bg-zinc-950 border border-zinc-800 rounded-2xl p-6 w-80 shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-semibold text-white">Camera Settings</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-white transition"><X size={16} /></button>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider mb-1.5 block">Camera name</label>
            <input type="text" value={video.cameraName || ""} onChange={e => onMetaChange(video.id, "cameraName", e.target.value)} className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500/60" placeholder="e.g. FATA, LATERAL1..." />
          </div>
          <div>
            <label className="text-[11px] text-zinc-500 uppercase tracking-wider mb-1.5 block">Camera order</label>
            <input type="number" min="1" value={video.cameraOrder || 1} onChange={e => onMetaChange(video.id, "cameraOrder", e.target.value)} className="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-sm text-white focus:outline-none focus:border-emerald-500/60" />
          </div>
          <div className="text-[10px] text-zinc-600 font-mono truncate">{video.name}</div>
        </div>
      </div>
    </div>
  );
}

// ── Grid helper ───────────────────────────────────────────────────────────────
function ReidSettingsPanel({ config, onPresetChange, onFieldChange, disabled }) {
  const [isOpen, setIsOpen] = useState(false);

  const fieldLabels = {
    max_embeddings: "Max embeddings per track",
    embedding_every_seen: "Embedding every N track appearances",
    min_embeddings_to_match: "Min embeddings to assign Global ID",
    recheck_interval: "Recheck interval seconds",
    reid_threshold: "Re-ID match threshold",
    intra_threshold: "Intra-track threshold",
    min_crop_h: "Min crop height",
    min_crop_w: "Min crop width",
    min_crop_area: "Min crop area",
  };

  const stepFor = (field) => (
    field === "reid_threshold" || field === "intra_threshold" || field === "recheck_interval"
      ? "0.01"
      : "1"
  );

  const presetLabels = {
    balanced: "Balanced",
    strict: "Strict matching",
    sensitive: "Sensitive / more matches",
    custom: "Custom",
  };

  const presetOptions = [
    { value: "balanced", label: "Balanced" },
    { value: "strict", label: "Strict" },
    { value: "sensitive", label: "Sensitive" },
    { value: "custom", label: "Custom" },
  ];

  const numericLimits = {
    max_embeddings: { min: 1, max: 20, step: 1 },
    embedding_every_seen: { min: 1, max: 50, step: 1 },
    min_embeddings_to_match: { min: 1, max: 10, step: 1 },
    recheck_interval: { min: 1, max: 60, step: 1 },
    reid_threshold: { min: 0.4, max: 0.95, step: 0.01 },
    intra_threshold: { min: 0.3, max: 0.95, step: 0.01 },
    min_crop_h: { min: 10, max: 300, step: 1 },
    min_crop_w: { min: 5, max: 200, step: 1 },
    min_crop_area: { min: 100, max: 50000, step: 100 },
  };

  const formatNumber = (field, value) => {
    const numberValue = Number(value);
    if (!Number.isFinite(numberValue)) return value;
    return field === "reid_threshold" || field === "intra_threshold"
      ? numberValue.toFixed(2)
      : String(numberValue);
  };

  const changeNumberByStep = (field, direction) => {
    const limits = numericLimits[field] || { min: -Infinity, max: Infinity, step: 1 };
    const current = Number(config[field]);
    const base = Number.isFinite(current) ? current : 0;
    const next = Math.min(limits.max, Math.max(limits.min, base + direction * limits.step));
    onFieldChange(field, formatNumber(field, next));
  };

  const statItems = [
    { label: "Max emb", value: config.max_embeddings },
    { label: "Every", value: config.embedding_every_seen },
    { label: "Match", value: config.reid_threshold },
    { label: "Crop", value: `${config.min_crop_w}x${config.min_crop_h}` },
  ];

  return (
    <div className="border-t border-white/[0.04] bg-[#08090a]/95 px-4 py-2.5">
      <div className="rounded-xl border border-emerald-500/15 bg-gradient-to-br from-zinc-950 via-zinc-950 to-emerald-950/20 shadow-[0_14px_40px_rgba(0,0,0,0.28)]">
        <button
          type="button"
          onClick={() => setIsOpen((prev) => !prev)}
          className="flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition hover:bg-white/[0.02]"
        >
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg border border-emerald-500/25 bg-emerald-500/10 text-emerald-300">
              <Crosshair size={15} />
            </div>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[10px] font-black uppercase tracking-[0.18em] text-emerald-300">Re-ID settings</span>
                <span className="rounded-full border border-zinc-700 bg-zinc-900 px-2 py-0.5 text-[9px] font-mono text-zinc-300">
                  {presetLabels[config.preset] || config.preset}
                </span>
                {!config.enable_reid_embeddings && (
                  <span className="rounded-full border border-red-500/25 bg-red-500/10 px-2 py-0.5 text-[9px] font-mono text-red-300">
                    embeddings off
                  </span>
                )}
              </div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[9px] font-mono text-zinc-500">
                {statItems.map((item) => (
                  <span key={item.label} className="rounded border border-zinc-800 bg-black/25 px-1.5 py-0.5">
                    {item.label}: <span className="text-zinc-300">{item.value}</span>
                  </span>
                ))}
              </div>
            </div>
          </div>

          <div className="flex flex-shrink-0 items-center gap-2">
            <span className="hidden text-[10px] font-mono text-zinc-500 sm:inline">
              {isOpen ? "Hide advanced" : "Edit"}
            </span>
            <ChevronRight size={15} className={`text-zinc-500 transition-transform ${isOpen ? "rotate-90 text-emerald-300" : ""}`} />
          </div>
        </button>

        <div className={`grid transition-all duration-200 ease-out ${isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}>
          <div className="overflow-hidden">
            <div className="border-t border-white/[0.06] px-3 pb-3 pt-3">
              <div className="grid gap-3 xl:grid-cols-[260px_minmax(0,1fr)]">
                <div className="rounded-lg border border-zinc-800/80 bg-black/20 p-3">
                  <label className="mb-1.5 block text-[9px] font-mono uppercase tracking-wider text-zinc-500">Preset</label>
                  <div className="grid grid-cols-2 gap-1.5">
                    {presetOptions.map((option) => {
                      const active = config.preset === option.value;
                      return (
                        <button
                          key={option.value}
                          type="button"
                          disabled={disabled}
                          onClick={() => onPresetChange(option.value)}
                          className={`rounded-lg border px-2.5 py-2 text-left text-[10px] font-mono transition disabled:cursor-not-allowed disabled:opacity-50 ${
                            active
                              ? "border-emerald-400/60 bg-emerald-500/15 text-emerald-200 shadow-[0_0_18px_rgba(16,185,129,0.12)]"
                              : "border-zinc-800 bg-zinc-950/80 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-900"
                          }`}
                        >
                          {option.label}
                        </button>
                      );
                    })}
                  </div>

                  <div className="mt-3 space-y-2">
                    <label className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-[10px] text-zinc-300">
                      <span>Enable Re-ID embeddings</span>
                      <input type="checkbox" checked={config.enable_reid_embeddings} disabled={disabled} onChange={(e) => onFieldChange("enable_reid_embeddings", e.target.checked)} className="h-4 w-4 accent-emerald-500" />
                    </label>
                    <label className="flex items-center justify-between gap-3 rounded-lg border border-zinc-800 bg-zinc-950/70 px-3 py-2 text-[10px] text-zinc-300">
                      <span>Emit Re-ID debug info</span>
                      <input type="checkbox" checked={config.emit_debug_info} disabled={disabled} onChange={(e) => onFieldChange("emit_debug_info", e.target.checked)} className="h-4 w-4 accent-emerald-500" />
                    </label>
                  </div>
                </div>

                <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
                  {REID_NUMERIC_FIELDS.map((field) => (
                    <label key={field} className="rounded-lg border border-zinc-800/80 bg-black/20 p-2">
                      <span className="mb-1.5 block text-[9px] font-mono uppercase tracking-wider text-zinc-500">{fieldLabels[field]}</span>
                      <div className="flex h-8 overflow-hidden rounded-md border border-zinc-800 bg-zinc-950 transition focus-within:border-emerald-500/60">
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => changeNumberByStep(field, -1)}
                          className="flex w-8 items-center justify-center border-r border-zinc-800 text-zinc-500 transition hover:bg-zinc-900 hover:text-emerald-300 disabled:opacity-40"
                          aria-label={`Decrease ${fieldLabels[field]}`}
                        >
                          <Minus size={12} />
                        </button>
                        <input
                          type="number"
                          step={stepFor(field)}
                          value={config[field]}
                          disabled={disabled}
                          onChange={(e) => onFieldChange(field, e.target.value)}
                          className="min-w-0 flex-1 bg-transparent px-2 text-center text-[11px] font-mono text-zinc-200 outline-none [appearance:textfield] disabled:opacity-50 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none"
                        />
                        <button
                          type="button"
                          disabled={disabled}
                          onClick={() => changeNumberByStep(field, 1)}
                          className="flex w-8 items-center justify-center border-l border-zinc-800 text-zinc-500 transition hover:bg-zinc-900 hover:text-emerald-300 disabled:opacity-40"
                          aria-label={`Increase ${fieldLabels[field]}`}
                        >
                          <Plus size={12} />
                        </button>
                      </div>
                    </label>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ReidDebugPanel({ items }) {
  if (!items.length) return null;

  const [isOpen, setIsOpen] = useState(false);
  const counts = items.reduce((acc, item) => {
    const status = item.status || getDetectionStatus(item);
    acc[status] = (acc[status] || 0) + 1;
    return acc;
  }, {});
  const rows = [...items]
    .slice(-24)
    .sort((a, b) => {
      const order = { identified: 0, tracking: 1, detected: 2 };
      return (order[a.status || getDetectionStatus(a)] ?? 3) - (order[b.status || getDetectionStatus(b)] ?? 3);
    });

  const statusClass = (status) => {
    if (status === "identified") return "border-emerald-500/30 bg-emerald-500/10 text-emerald-300";
    if (status === "tracking") return "border-cyan-500/25 bg-cyan-500/10 text-cyan-300";
    return "border-zinc-700 bg-zinc-900 text-zinc-400";
  };

  const formatNumber = (value, digits = 3) => (
    value == null || !Number.isFinite(Number(value)) ? "-" : Number(value).toFixed(digits)
  );

  return (
    <div className="absolute bottom-3 right-3 z-40 hidden xl:block">
      {!isOpen && (
        <button
          type="button"
          onClick={() => setIsOpen(true)}
          className="flex items-center gap-2 rounded-lg border border-emerald-500/25 bg-black/80 px-3 py-2 text-[10px] font-mono text-emerald-300 shadow-2xl backdrop-blur-md transition hover:border-emerald-400/50 hover:bg-zinc-950"
        >
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          Re-ID debug
          <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[9px] text-emerald-200">{items.length}</span>
        </button>
      )}

      {isOpen && (
        <div className="w-[390px] max-h-[62vh] overflow-hidden rounded-lg border border-zinc-800 bg-[#08090a]/95 shadow-2xl backdrop-blur-md">
          <div className="flex items-center justify-between border-b border-zinc-800 px-3 py-2">
            <div>
              <div className="text-[10px] font-black uppercase tracking-[0.18em] text-emerald-300">Re-ID Debug</div>
              <div className="mt-0.5 text-[9px] font-mono text-zinc-500">{items.length} live items</div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="rounded-md border border-zinc-800 bg-zinc-950 px-2 py-1 text-[10px] font-mono text-zinc-400 transition hover:border-zinc-700 hover:text-white"
            >
              hide
            </button>
          </div>

          <div className="grid grid-cols-3 gap-1.5 border-b border-zinc-800 px-3 py-2">
            <div className="rounded-md border border-emerald-500/20 bg-emerald-500/10 px-2 py-1">
              <div className="text-[8px] uppercase tracking-wider text-emerald-400">identified</div>
              <div className="text-sm font-mono text-emerald-200">{counts.identified || 0}</div>
            </div>
            <div className="rounded-md border border-cyan-500/20 bg-cyan-500/10 px-2 py-1">
              <div className="text-[8px] uppercase tracking-wider text-cyan-400">tracking</div>
              <div className="text-sm font-mono text-cyan-200">{counts.tracking || 0}</div>
            </div>
            <div className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1">
              <div className="text-[8px] uppercase tracking-wider text-zinc-500">detected</div>
              <div className="text-sm font-mono text-zinc-300">{counts.detected || 0}</div>
            </div>
          </div>

          <div className="reid-debug-scroll max-h-[45vh] overflow-y-auto p-2">
            <div className="space-y-1.5">
              {rows.map((item, idx) => {
                const status = item.status || getDetectionStatus(item);
                const label = item.label || getDetectionLabel(item);
                const embeddingText = `${item.n_embeddings ?? 0}/${item.max_embeddings ?? "-"}`;
                const isMatched = Boolean(item.matched || item.global_id != null);
                return (
                  <div key={getDebugDetectionKey(item, idx)} className="rounded-md border border-zinc-800 bg-zinc-950/80 p-2">
                    <div className="mb-1.5 flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <span className={`rounded border px-1.5 py-0.5 text-[9px] font-mono ${statusClass(status)}`}>{label}</span>
                        <span className="truncate text-[9px] font-mono text-zinc-500">{item.camera_name ?? item.video_id ?? "camera"}</span>
                      </div>
                      <span className={`rounded px-1.5 py-0.5 text-[8px] font-mono ${isMatched ? "bg-emerald-500/15 text-emerald-300" : "bg-zinc-800 text-zinc-400"}`}>
                        {isMatched ? "matched" : "pending"}
                      </span>
                    </div>

                    <div className="grid grid-cols-4 gap-1 text-[9px] font-mono">
                      <div className="rounded bg-black/35 px-1.5 py-1 text-zinc-500">
                        <span className="block text-[7px] uppercase text-zinc-700">track</span>
                        <span className="text-zinc-300">{item.track_id ?? "-"}</span>
                      </div>
                      <div className="rounded bg-black/35 px-1.5 py-1 text-zinc-500">
                        <span className="block text-[7px] uppercase text-zinc-700">emb</span>
                        <span className="text-zinc-300">{embeddingText}</span>
                      </div>
                      <div className="rounded bg-black/35 px-1.5 py-1 text-zinc-500">
                        <span className="block text-[7px] uppercase text-zinc-700">cand</span>
                        <span className="text-zinc-300">{formatNumber(item.candidate_score)}</span>
                      </div>
                      <div className="rounded bg-black/35 px-1.5 py-1 text-zinc-500">
                        <span className="block text-[7px] uppercase text-zinc-700">thr</span>
                        <span className="text-zinc-300">{formatNumber(item.reid_threshold, 2)}</span>
                      </div>
                    </div>

                    <div className="mt-1.5 flex items-center justify-between gap-2 text-[8px] font-mono text-zinc-600">
                      <span>seen {item.seen_count ?? "-"}</span>
                      <span>crop {item.good_crop == null ? "-" : String(Boolean(item.good_crop))}</span>
                      <span>score {formatNumber(item.match_score)}</span>
                      {(item.reason || item.detector_only) && <span className="max-w-[120px] truncate text-yellow-400/80">{item.reason || "detector_only"}</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function getCameraGridStyle(count, expandedId) {
  if (expandedId) return { gridTemplateColumns: "1fr", gridTemplateRows: "1fr" };
  if (count === 1) return { gridTemplateColumns: "1fr", gridTemplateRows: "1fr" };
  if (count === 2) return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr" };
  if (count <= 4) return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr" };
  if (count <= 6) return { gridTemplateColumns: "1fr 1fr 1fr", gridTemplateRows: "1fr 1fr" };
  if (count <= 9) return { gridTemplateColumns: "1fr 1fr 1fr", gridTemplateRows: "1fr 1fr 1fr" };
  return { gridTemplateColumns: "repeat(4, 1fr)", gridTemplateRows: "auto" };
}

// ══════════════════════════════════════════════════════════════════════════════
// TRACKING PAGE
// ══════════════════════════════════════════════════════════════════════════════
export default function Tracking() {
  const { token }            = useAuth();
  const { t }                = useLanguage();
  const { socket: ctxSocket } = useProcessing();

  const [videos, setVideos]           = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [expandedId, setExpandedId]   = useState(null);
  const [configVideo, setConfigVideo] = useState(null);
  const [globalPeople, setGlobalPeople] = useState({});
  const [warmupStatus, setWarmupStatus] = useState(null);
  const [statusMsg, setStatusMsg]     = useState("");
  const [showSidebar, setShowSidebar] = useState(false);
  const [selectedGlobalId, setSelectedGlobalId] = useState(null);
  const [preparedJobId, setPreparedJobId] = useState(null);
  const [isPreparing, setIsPreparing] = useState(false);
  const [reidConfig, setReidConfig] = useState(BALANCED_REID_PRESET);
  const [reidDebugItems, setReidDebugItems] = useState([]);

  // reidDetections: { camera_key: { detections: [], timestamp_ms: N } }
  const [reidDetections, setReidDetections] = useState({});
  const [completedSessionId, setCompletedSessionId] = useState(null);

  const fileInputRef    = useRef(null);
  const socketRef       = useRef(null);
  const activeVideoIdRef = useRef(null);
  const activeReidJobIdRef = useRef(null);
  const autoStartReidAfterPrepareRef = useRef(false);
  const videosRef = useRef([]);
  const reidConfigRef = useRef(BALANCED_REID_PRESET);
  const toastTimersRef  = useRef({});

  const resolveMatch = useCallback((video, incomingVideoId) => {
    if (incomingVideoId == null) return false;
    const inc = String(incomingVideoId);
    return inc === String(video.id) || (video.backendVideoId != null && inc === String(video.backendVideoId));
  }, []);

  const showToastOnCamera = useCallback((videoId, cameraName, toastData) => {
    const timerKey = videoId != null ? String(videoId) : cameraName;
    setVideos(prev => prev.map(v =>
      resolveMatch(v, videoId) || v.cameraName === cameraName
        ? { ...v, activeToast: toastData }
        : v
    ));
    if (toastTimersRef.current[timerKey]) clearTimeout(toastTimersRef.current[timerKey]);
    toastTimersRef.current[timerKey] = setTimeout(() => {
      setVideos(prev => prev.map(v =>
        resolveMatch(v, videoId) || v.cameraName === cameraName
          ? { ...v, activeToast: null }
          : v
      ));
      delete toastTimersRef.current[timerKey];
    }, 4000);
  }, [resolveMatch]);

  const handleReidPresetChange = (preset) => {
    if (preset === "custom") {
      setReidConfig(prev => ({ ...prev, preset: "custom" }));
      return;
    }
    setReidConfig(REID_PRESETS[preset] || BALANCED_REID_PRESET);
  };

  const handleReidFieldChange = (field, value) => {
    setReidConfig(prev => ({
      ...prev,
      preset: "custom",
      [field]: typeof value === "boolean" ? value : value,
    }));
  };

  const buildReidConfigPayload = () => ({
    preset: reidConfig.preset,
    enable_reid_embeddings: Boolean(reidConfig.enable_reid_embeddings),
    emit_debug_info: Boolean(reidConfig.emit_debug_info),
    max_embeddings: Number(reidConfig.max_embeddings),
    embedding_every_seen: Number(reidConfig.embedding_every_seen),
    min_embeddings_to_match: Number(reidConfig.min_embeddings_to_match),
    recheck_interval: Number(reidConfig.recheck_interval),
    reid_threshold: Number(reidConfig.reid_threshold),
    intra_threshold: Number(reidConfig.intra_threshold),
    min_crop_h: Number(reidConfig.min_crop_h),
    min_crop_w: Number(reidConfig.min_crop_w),
    min_crop_area: Number(reidConfig.min_crop_area),
  });

  const buildReidConfigPayloadFrom = (config) => ({
    preset: config.preset,
    enable_reid_embeddings: Boolean(config.enable_reid_embeddings),
    emit_debug_info: Boolean(config.emit_debug_info),
    max_embeddings: Number(config.max_embeddings),
    embedding_every_seen: Number(config.embedding_every_seen),
    min_embeddings_to_match: Number(config.min_embeddings_to_match),
    recheck_interval: Number(config.recheck_interval),
    reid_threshold: Number(config.reid_threshold),
    intra_threshold: Number(config.intra_threshold),
    min_crop_h: Number(config.min_crop_h),
    min_crop_w: Number(config.min_crop_w),
    min_crop_area: Number(config.min_crop_area),
  });

  const buildPreparedCameras = (sourceVideos) => [...sourceVideos]
    .filter(v => v.backendVideoId)
    .sort((a, b) => (a.cameraOrder || 1) - (b.cameraOrder || 1))
    .map(v => ({
      video_id: v.backendVideoId,
      camera_name: v.cameraName,
      camera_order: Number(v.cameraOrder || 1),
    }));

  // ── Sync socketRef to context socket ─────────────────────────────────────
  useEffect(() => {
    socketRef.current = ctxSocket;
  }, [ctxSocket]);

  useEffect(() => {
    activeReidJobIdRef.current = preparedJobId;
  }, [preparedJobId]);

  useEffect(() => {
    videosRef.current = videos;
  }, [videos]);

  useEffect(() => {
    reidConfigRef.current = reidConfig;
  }, [reidConfig]);

  // ── Socket event handlers ─────────────────────────────────────────────────
  useEffect(() => {
    if (!ctxSocket) return;

    const handleFrame = (data) => {
      const videoId = data?.video_id ?? activeVideoIdRef.current;
      setVideos(prev =>
        prev.map(v =>
          resolveMatch(v, videoId)
            ? {
                ...v,
                streamFrame: `data:image/jpeg;base64,${data.frame}`,
                frameInfo: {
                  frameNumber: data.frame_number,
                  totalFrames: data.total_frames,
                  peopleCount: data.people_count,
                  detectedPeopleCount: data.detected_people_count ?? data.people_count,
                  identifiedPeopleCount: data.identified_people_count ?? data.global_ids?.length,
                  progress:    data.progress,
                },
                globalIds: data.global_ids ?? v.globalIds,
              }
            : v
        )
      );
    };

    const shouldIgnoreReidEvent = (data) => {
      const activeJobId = activeReidJobIdRef.current;
      return Boolean(data?.job_id && activeJobId && String(data.job_id) !== String(activeJobId));
    };

    const normalizeDebugItem = (item, fallback = {}) => ({
      video_id: item?.video_id ?? fallback.video_id,
      camera_name: item?.camera_name ?? fallback.camera_name,
      detection_index: item?.detection_index,
      track_id: item?.track_id,
      global_id: item?.global_id,
      label: getDetectionLabel(item),
      status: getDetectionStatus(item),
      color: item?.color,
      seen_count: item?.seen_count,
      n_embeddings: item?.n_embeddings,
      max_embeddings: item?.max_embeddings,
      matched: item?.matched,
      detector_only: item?.detector_only,
      good_crop: item?.good_crop,
      bbox: item?.bbox,
      bbox_xywh: item?.bbox_xywh,
      conf: item?.conf,
      match_score: item?.match_score,
      candidate_score: item?.candidate_score,
      reid_threshold: item?.reid_threshold ?? item?.threshold,
      reason: item?.reason,
      intra_sim: item?.intra_sim,
    });

    const compactDebugItem = (item) => Object.fromEntries(
      Object.entries(item).filter(([, value]) => value !== undefined)
    );

    const mergeDebugItem = (existing = {}, incoming = {}) => ({
      ...existing,
      ...compactDebugItem(incoming),
      match_score: incoming.match_score ?? existing.match_score,
      candidate_score: incoming.candidate_score ?? existing.candidate_score,
      reid_threshold: incoming.reid_threshold ?? existing.reid_threshold,
      best_crop: incoming.best_crop ?? existing.best_crop,
    });

    const isUsefulDebugItem = (item) => (
      item?.track_id != null ||
      item?.global_id != null ||
      item?.detection_index != null ||
      Array.isArray(item?.bbox) ||
      item?.reason != null
    );

    const handleReidFrameDetections = (data) => {
  if (shouldIgnoreReidEvent(data)) return;
  const camName = data?.camera_name;
  const incomingVideoId = data?.video_id ?? data?.camera_id;
  const detections = Array.isArray(data?.detections) ? data.detections : [];
  const detectedPeopleCount = Array.isArray(data?.detections)
    ? detections.length
    : data?.detected_people_count ?? data?.people_count ?? 0;
  const identifiedPeopleCount = data?.identified_people_count ?? (Array.isArray(data?.global_ids) ? data.global_ids.length : 0);
  const frameWidth = data?.original_frame_width ?? data?.frame_width;
  const frameHeight = data?.original_frame_height ?? data?.frame_height;

  setReidDetections(prev => {
    const next = { ...prev };
    const payload = {
      detections,
      timestamp_ms: data?.timestamp_ms,
    };
    [data?.video_id, data?.camera_id, camName]
      .filter(key => key != null && key !== "")
      .forEach(key => {
        next[String(key)] = payload;
      });
    return next;
  });

  if (detections.length) {
    setReidDebugItems(prev => {
      const next = new Map(prev.map((item, idx) => [getDebugDetectionKey(item, idx), item]));
      detections.forEach(det => {
        const normalized = normalizeDebugItem(det, data);
        const key = getDebugDetectionKey(normalized, next.size, data);
        next.set(key, mergeDebugItem(next.get(key), normalized));
      });
      return Array.from(next.values()).slice(-40);
    });
  }

  setVideos(prev =>
    prev.map((v, videoIndex) => {
      const cameraIdMatches = data?.camera_id != null && (
        String(data.camera_id) === String(v.cameraOrder) ||
        String(data.camera_id) === String(videoIndex) ||
        String(data.camera_id) === String(videoIndex + 1)
      );
      if (!resolveMatch(v, incomingVideoId) && v.cameraName !== camName && !cameraIdMatches) return v;

      return {
        ...v,

        // AICI e partea importantă:
        // dacă backend-ul trimite frame, îl afișăm în interfață
        streamFrame: data.frame
          ? `data:image/jpeg;base64,${data.frame}`
          : v.streamFrame,

        reidDetections: detections,
        globalIds: data.global_ids ?? v.globalIds,

        frameInfo: {
          frameNumber: data.frame_number,
          totalFrames: data.total_frames,
          peopleCount: detectedPeopleCount,
          detectedPeopleCount,
          identifiedPeopleCount,
          progress: data.progress ?? v.frameInfo?.progress ?? 0,
        },

        ...(frameWidth && frameHeight
          ? { frameSize: { w: frameWidth, h: frameHeight } }
          : {}),
      };
    })
  );
};

    const handlePersonCrop = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      const gid = String(data.global_id);
      showToastOnCamera(data.video_id ?? data.camera_id, data.camera_name, {
        global_id:     data.global_id,
        camera_name:   data.camera_name,
        best_crop:     data.best_crop,
        match_score:   data.match_score,
        is_new_person: data.is_new_person,
      });
      setGlobalPeople(prev => {
        const existing = prev[gid] || {};
        const incomingCrops = Array.isArray(data.crops)
          ? data.crops.map((crop, idx) => ({
              image: typeof crop === "string" ? crop : crop.image || crop.crop || crop.best_crop,
              camera_name: crop.camera_name || data.camera_name,
              track_id: crop.track_id ?? data.track_id,
              timestamp_ms: crop.timestamp_ms || data.timestamp_ms || Date.now() + idx,
              timestamp_s: crop.timestamp_s ?? data.timestamp_s,
              frame_number: crop.frame_number || data.frame_number,
              bbox: crop.bbox || data.bbox,
              bbox_area: crop.bbox_area ?? data.bbox_area,
              match_score: crop.match_score ?? data.match_score,
              candidate_score: crop.candidate_score ?? data.candidate_score,
              reid_threshold: crop.reid_threshold ?? data.reid_threshold,
              source: crop.source || (data.recheck ? "recheck" : "assign"),
              previous_global_id: data.previous_global_id,
            })).filter(crop => crop.image)
          : [];
        if (data.best_crop && incomingCrops.length === 0) {
          incomingCrops.unshift({
            image: data.best_crop,
            camera_name: data.camera_name,
            track_id: data.track_id,
            timestamp_ms: data.timestamp_ms || Date.now(),
            timestamp_s: data.timestamp_s,
            frame_number: data.frame_number,
            bbox: data.bbox,
            bbox_area: data.bbox_area,
            match_score: data.match_score,
            candidate_score: data.candidate_score,
            reid_threshold: data.reid_threshold,
            source: data.recheck ? "recheck" : "assign",
            previous_global_id: data.previous_global_id,
          });
        }
        const seen = new Set();
        const cropHistory = [...incomingCrops, ...(existing.crop_history || [])]
          .filter(crop => {
            const key = `${crop.image}-${crop.camera_name || ""}`;
            if (!crop.image || seen.has(key)) return false;
            seen.add(key);
            return true;
          })
          .slice(0, 24);
        return {
          ...prev,
          [gid]: {
            ...existing,
            global_id:     data.global_id,
            cameras:       data.cameras || existing.cameras || [],
            color:         data.color   || existing.color   || "#888888",
            best_crop:     data.best_crop || existing.best_crop,
            match_score:   data.match_score   ?? existing.match_score   ?? 0,
            is_new_person: data.is_new_person ?? existing.is_new_person ?? true,
            n_embeddings:  data.n_embeddings  ?? existing.n_embeddings  ?? 0,
            last_seen_ms:   data.timestamp_ms  ?? existing.last_seen_ms,
            bbox:           data.bbox          || existing.bbox,
            crop_history:   cropHistory,
          },
        };
      });
      setShowSidebar(true);
      setReidDebugItems(prev => {
        const normalized = normalizeDebugItem({
          ...data,
          matched: true,
          label: getDetectionLabel(data),
          status: getDetectionStatus(data),
        });
        const key = getDebugDetectionKey(normalized);
        const next = new Map(prev.map((item, idx) => [getDebugDetectionKey(item, idx), item]));
        next.set(key, mergeDebugItem(next.get(key), normalized));
        return Array.from(next.values()).slice(-40);
      });
    };

    const handleReidUpdate = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      if (data.track_id != null || data.global_id != null || data.detection_index != null) {
        setReidDebugItems(prev => {
          const normalized = normalizeDebugItem(data);
          const key = getDebugDetectionKey(normalized);
          const next = new Map(prev.map((item, idx) => [getDebugDetectionKey(item, idx), item]));
          next.set(key, mergeDebugItem(next.get(key), normalized));
          return Array.from(next.values()).slice(-40);
        });
      }
      if (data.global_people) {
        setGlobalPeople(prev => {
          const updated = { ...prev };
          Object.entries(data.global_people).forEach(([gid, info]) => {
            updated[gid] = {
              ...(prev[gid] || {}),
              ...info,
              ...(String(data.global_id) === gid ? { match_score: data.match_score } : {}),
            };
          });
          return updated;
        });
      }
      if (data.camera_name && data.global_id) {
        setVideos(prev =>
          prev.map(v => {
            if (!resolveMatch(v, data.video_id ?? data.camera_id) && v.cameraName !== data.camera_name) return v;
            const ids = v.globalIds || [];
            if (ids.includes(data.global_id)) return v;
            return { ...v, globalIds: [...ids, data.global_id] };
          })
        );
      }
    };

    const handleWarmupStatus = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      setWarmupStatus(data.status);
      setStatusMsg(data.message || "");
      if (data.status === 'download_start') {
        setVideos(prev => prev.map(v => v.backendVideoId ? { ...v, serverDownloadStatus: 'downloading', downloadPercent: 0 } : v));
      } else if (data.status === 'download_bytes' && data.camera_name) {
        setVideos(prev => prev.map(v =>
          v.cameraName === data.camera_name
            ? {
                ...v,
                serverDownloadStatus: (data.percent || 0) >= 100 ? 'ready' : 'downloading',
                downloadPercent: data.percent || 0,
                statusMsg: data.message || v.statusMsg,
              }
            : v
        ));
      } else if (data.status === 'download_progress' && data.camera_name) {
        setVideos(prev => prev.map(v =>
          v.cameraName === data.camera_name ? { ...v, serverDownloadStatus: 'ready' } : v
        ));
      } else if (data.status === 'processing_start' || data.status === 'reid_ready') {
        setVideos(prev => prev.map(v =>
          v.serverDownloadStatus === 'downloading' ? { ...v, serverDownloadStatus: 'ready' } : v
        ));
      }
    };

    const handleReidPrepareStatus = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      if (data.message) setStatusMsg(data.message);
      setVideos(prev => prev.map(v => {
        const sameVideo = data.video_id != null && v.backendVideoId != null && String(v.backendVideoId) === String(data.video_id);
        const sameCamera = data.camera_name && v.cameraName === data.camera_name;
        if (!sameVideo && !sameCamera) return v;
        return {
          ...v,
          serverDownloadStatus: data.status || v.serverDownloadStatus,
          downloadPercent: data.percent ?? v.downloadPercent ?? 0,
          statusMsg: data.message || v.statusMsg,
        };
      }));
    };

    const handleReidReadyToStart = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      const readyJobId = data.job_id || null;
      setPreparedJobId(readyJobId);
      setIsPreparing(false);
      setWarmupStatus(null);
      setStatusMsg(data.message || "All cameras ready. Press Start Re-ID.");
      setVideos(prev => prev.map(v =>
        v.backendVideoId ? { ...v, serverDownloadStatus: "ready", downloadPercent: 100 } : v
      ));

      if (autoStartReidAfterPrepareRef.current && readyJobId) {
        autoStartReidAfterPrepareRef.current = false;
        activeReidJobIdRef.current = readyJobId;
        const cameras = Array.isArray(data.cameras) && data.cameras.length
          ? data.cameras
          : buildPreparedCameras(videosRef.current);

        setGlobalPeople({});
        setReidDetections({});
        setReidDebugItems([]);
        setSelectedGlobalId(null);
        setWarmupStatus("warmup");
        setStatusMsg("Reiau Re-ID cu parametrii curenti...");
        setShowSidebar(true);
        setIsProcessing(true);
        setVideos(prev => prev.map(v =>
          v.backendVideoId
            ? {
                ...v,
                isProcessing: true,
                streamFrame: null,
                frameInfo: null,
                globalIds: [],
                activeToast: null,
                serverDownloadStatus: "ready",
                downloadPercent: 100,
              }
            : v
        ));

        ctxSocket.emit("start_reid", {
          job_id: readyJobId,
          cameras,
          save_to_db: true,
          emit_live_events: true,
          reid_config: buildReidConfigPayloadFrom(reidConfigRef.current),
        });
      }
    };

    const handleReidComplete = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      setWarmupStatus("done");
      setStatusMsg(`Re-ID complet: ${data.n_people ?? "?"} persoane identificate`);
      setIsProcessing(false);
      setVideos(prev => prev.map(v => v.isProcessing ? { ...v, isProcessing: false, serverDownloadStatus: 'ready' } : v));
      if (data.db_session_id) setCompletedSessionId(data.db_session_id);
      if (data.global_people) {
        setGlobalPeople(prev => {
          const updated = { ...prev };
          Object.entries(data.global_people).forEach(([gid, info]) => {
            updated[gid] = { ...(prev[gid] || {}), ...info };
          });
          return updated;
        });
      }
    };

    const handleReidStopped = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      autoStartReidAfterPrepareRef.current = false;
      setWarmupStatus(null);
      setStatusMsg(data?.message || "Re-ID oprit.");
      setIsProcessing(false);
      setIsPreparing(false);
      setVideos(prev => prev.map(v => v.isProcessing ? { ...v, isProcessing: false } : v));
    };

    const handleReidDebugEvent = (data) => {
      if (shouldIgnoreReidEvent(data)) return;
      const entries = Array.isArray(data?.items)
        ? data.items
        : Array.isArray(data?.tracks)
          ? data.tracks
          : [data];
      setReidDebugItems(prev => {
        const next = new Map(prev.map((item, idx) => [getDebugDetectionKey(item, idx), item]));
        entries.forEach(entry => {
          const normalized = normalizeDebugItem(entry, data);
          if (!isUsefulDebugItem(normalized)) return;
          const key = getDebugDetectionKey(normalized, next.size, data);
          next.set(key, mergeDebugItem(next.get(key), normalized));
        });
        return Array.from(next.values()).slice(-40);
      });
    };

    const handleProcessingComplete = (stats) => {
      const videoId = stats?.video_id ?? activeVideoIdRef.current;
      setVideos(prev => prev.map(v => resolveMatch(v, videoId) ? { ...v, results: stats, isProcessing: false } : v));
      setIsProcessing(false);
    };

    const handleProcessingStopped = (data) => {
      const videoId = data?.video_id;
      setVideos(prev => {
        const updated = prev.map(v =>
          resolveMatch(v, videoId) ? { ...v, isProcessing: false } : v
        );
        if (!updated.some(v => v.isProcessing)) setIsProcessing(false);
        return updated;
      });
    };

    const handleError = (err) => {
      console.error("[WS] Error:", err);
      autoStartReidAfterPrepareRef.current = false;
      setStatusMsg("Eroare: " + (err.message || "unknown"));
      setIsProcessing(false);
      setIsPreparing(false);
    };

    ctxSocket.on("frame", handleFrame);
    ctxSocket.on("reid_frame_detections", handleReidFrameDetections);
    ctxSocket.on("person_crop", handlePersonCrop);
    ctxSocket.on("reid_update", handleReidUpdate);
    ctxSocket.on("reid_config", handleReidDebugEvent);
    ctxSocket.on("reid_embedding_update", handleReidDebugEvent);
    ctxSocket.on("reid_embedding_skip", handleReidDebugEvent);
    ctxSocket.on("reid_final_summary", handleReidDebugEvent);
    ctxSocket.on("warmup_status", handleWarmupStatus);
    ctxSocket.on("reid_prepare_status", handleReidPrepareStatus);
    ctxSocket.on("reid_ready_to_start", handleReidReadyToStart);
    ctxSocket.on("reid_complete", handleReidComplete);
    ctxSocket.on("reid_stopped", handleReidStopped);
    ctxSocket.on("processing_complete", handleProcessingComplete);
    ctxSocket.on("processing_stopped", handleProcessingStopped);
    ctxSocket.on("error", handleError);

    return () => {
      ctxSocket.off("frame", handleFrame);
      ctxSocket.off("reid_frame_detections", handleReidFrameDetections);
      ctxSocket.off("person_crop", handlePersonCrop);
      ctxSocket.off("reid_update", handleReidUpdate);
      ctxSocket.off("reid_config", handleReidDebugEvent);
      ctxSocket.off("reid_embedding_update", handleReidDebugEvent);
      ctxSocket.off("reid_embedding_skip", handleReidDebugEvent);
      ctxSocket.off("reid_final_summary", handleReidDebugEvent);
      ctxSocket.off("warmup_status", handleWarmupStatus);
      ctxSocket.off("reid_prepare_status", handleReidPrepareStatus);
      ctxSocket.off("reid_ready_to_start", handleReidReadyToStart);
      ctxSocket.off("reid_complete", handleReidComplete);
      ctxSocket.off("reid_stopped", handleReidStopped);
      ctxSocket.off("processing_complete", handleProcessingComplete);
      ctxSocket.off("processing_stopped", handleProcessingStopped);
      ctxSocket.off("error", handleError);
      Object.values(toastTimersRef.current).forEach(clearTimeout);
    };
  }, [ctxSocket, resolveMatch, showToastOnCamera]);

  // ── Logout ────────────────────────────────────────────────────────────────
  useEffect(() => {
    const handleLogout = () => {
      setIsProcessing(false);
      setVideos([]);
      setGlobalPeople({});
      setReidDetections({});
      setExpandedId(null);
      setShowSidebar(false);
      setSelectedGlobalId(null);
      setWarmupStatus(null);
      setStatusMsg("");
      setPreparedJobId(null);
      setIsPreparing(false);
      setReidConfig(BALANCED_REID_PRESET);
      setReidDebugItems([]);
    };
    window.addEventListener("user-logout", handleLogout);
    return () => window.removeEventListener("user-logout", handleLogout);
  }, []);

  // ── Upload ────────────────────────────────────────────────────────────────
  const handleVideoUpload = e => {
    const files = Array.from(e.target.files);
    if (!files.length) return;
    const base = videos.length;
    setPreparedJobId(null);
    setVideos(prev => [
      ...prev,
      ...files.map((file, i) => ({
        id: `video_${Date.now()}_${i}`,
        backendVideoId: null,
        name: file.name,
        src: URL.createObjectURL(file),
        file,
        streamFrame: null,
        frameInfo:   null,
        results:     null,
        isProcessing: false,
        isUploading:  false,
        uploadError:  false,
        uploadProgress: 0,
        serverDownloadStatus: 'pending',
        downloadPercent: 0,
        globalIds:    [],
        activeToast:  null,
        cameraName:   `Camera ${base + i + 1}`,
        cameraOrder:  base + i + 1,
      })),
    ]);
    e.target.value = "";
  };

  const handleCameraMetaChange = (videoId, key, value) => {
    setVideos(prev =>
      prev.map(v => {
        if (v.id !== videoId) return v;
        if (key === "cameraOrder") { const p = parseInt(value, 10); return { ...v, cameraOrder: isNaN(p) ? 1 : Math.max(1, p) }; }
        return { ...v, [key]: value };
      })
    );
  };

  const uploadVideo = async video => {
    const formData = new FormData();
    formData.append("video", video.file);
    formData.append("camera_name", video.cameraName || `Camera ${video.cameraOrder || 1}`);
    formData.append("camera_order", String(video.cameraOrder || 1));
    try {
      const res = await axios.post(`${API_URL}/upload`, formData, {
        headers: { "Content-Type": "multipart/form-data", Authorization: `Bearer ${token || localStorage.getItem("token")}` },
        validateStatus: s => s < 500,
        onUploadProgress: (p) => {
          const pct = p.total ? Math.round((p.loaded * 100) / p.total) : 0;
          setVideos(prev => prev.map(v => v.id === video.id ? { ...v, uploadProgress: pct } : v));
        },
      });
      const backendId = res.data.video_id;
      if (!backendId) { setVideos(prev => prev.map(v => v.id === video.id ? { ...v, isUploading: false, uploadError: true } : v)); return null; }
      setVideos(prev => prev.map(v => v.id === video.id ? { ...v, backendVideoId: backendId, isUploading: false } : v));
      return { frontendId: video.id, backendId, filename: video.file.name, cameraName: video.cameraName, cameraOrder: video.cameraOrder };
    } catch {
      setVideos(prev => prev.map(v => v.id === video.id ? { ...v, isUploading: false, uploadError: true } : v));
      return null;
    }
  };

  const handlePrepareCameras = async () => {
    const toUpload = [...videos]
      .sort((a, b) => (a.cameraOrder || 1) - (b.cameraOrder || 1))
      .filter(v => !v.backendVideoId && !v.isUploading);

    setPreparedJobId(null);
    setIsPreparing(true);
    setStatusMsg(toUpload.length ? `Uploading ${toUpload.length} cameras...` : "Preparing cameras on cluster...");
    setVideos(prev =>
      prev.map(v =>
        toUpload.find(t => t.id === v.id)
          ? { ...v, isUploading: true, uploadError: false, serverDownloadStatus: "pending", downloadPercent: 0 }
          : v.backendVideoId
            ? { ...v, serverDownloadStatus: "pending", downloadPercent: 0 }
            : v
      )
    );

    const uploadResults = await Promise.all(toUpload.map(v => uploadVideo(v)));
    const uploadedOk = uploadResults.filter(Boolean);

    if (uploadedOk.length !== toUpload.length) {
      setStatusMsg(`Upload partial: ${uploadedOk.length}/${toUpload.length} cameras uploaded.`);
      setIsPreparing(false);
      return;
    }

    const latestById = new Map(uploadedOk.map(r => [r.frontendId, r.backendId]));
    const cameras = videos
      .map(v => ({
        ...v,
        backendVideoId: v.backendVideoId || latestById.get(v.id),
      }))
      .filter(v => v.backendVideoId)
      .sort((a, b) => (a.cameraOrder || 1) - (b.cameraOrder || 1))
      .map(v => ({
        video_id: v.backendVideoId,
        camera_name: v.cameraName,
        camera_order: Number(v.cameraOrder || 1),
      }));

    if (!cameras.length || cameras.length !== videos.length) {
      setStatusMsg("Nu toate camerele sunt uploadate. Pregatirea clusterului nu a pornit.");
      setIsPreparing(false);
      return;
    }

    setStatusMsg("Downloading on cluster...");
    setVideos(prev => prev.map(v =>
      v.backendVideoId || latestById.has(v.id)
        ? { ...v, serverDownloadStatus: "downloading", downloadPercent: 0 }
        : v
    ));
    socketRef.current?.emit("prepare_reid", { cameras });
    return;

    if (!toUpload.length) {
      setStatusMsg("Toate camerele sunt deja încărcate în baza de date.");
      return;
    }

    setStatusMsg(`Se încarcă ${toUpload.length} camere în baza de date...`);
    setVideos(prev =>
      prev.map(v =>
        toUpload.find(t => t.id === v.id) ? { ...v, isUploading: true, uploadError: false } : v
      )
    );

    const results = await Promise.all(toUpload.map(v => uploadVideo(v)));
    const ok = results.filter(Boolean);

    if (ok.length !== toUpload.length) {
      setStatusMsg(`Upload parțial: ${ok.length}/${toUpload.length} camere încărcate.`);
    } else {
      setStatusMsg("Toate camerele au fost încărcate în baza de date.");
    }
  };

  const handleStopAll = () => {
    autoStartReidAfterPrepareRef.current = false;
    activeReidJobIdRef.current = null;
    const active = videos.filter(v => v.isProcessing && v.backendVideoId);
    active.forEach(v => {
      socketRef.current?.emit("stop_processing", { video_id: v.backendVideoId });
    });
    if (isProcessing || isPreparing || (warmupStatus && warmupStatus !== "done")) {
      socketRef.current?.emit("stop_reid", { job_id: preparedJobId });
    }
    setVideos(prev => prev.map(v =>
      v.isProcessing || v.serverDownloadStatus === "downloading"
        ? { ...v, isProcessing: false, serverDownloadStatus: "pending", downloadPercent: 0 }
        : v
    ));
    setIsProcessing(false);
    setIsPreparing(false);
    setWarmupStatus(null);
    setPreparedJobId(null);
    setStatusMsg("Oprire trimisa catre cluster...");
  };

  const handleStartReID = () => {
    if (!allReadyForReid) {
      setStatusMsg("Încarcă toate camerele în baza de date înainte de a porni Re-ID.");
      return;
    }

    const cameras = buildPreparedCameras(videos);

    if (!cameras.length) {
      setStatusMsg("Nu există camere valide pentru Re-ID.");
      return;
    }

    setGlobalPeople({});
    setReidDetections({});
    setReidDebugItems([]);
    setSelectedGlobalId(null);
    setWarmupStatus("warmup");
    setStatusMsg("Se pornește Re-ID multi-camera...");
    setShowSidebar(true);
    setIsProcessing(true);
    setVideos(prev => prev.map(v =>
      v.backendVideoId
        ? {
            ...v,
            isProcessing: true,
            streamFrame: null,
            frameInfo: null,
            serverDownloadStatus: "ready",
            downloadPercent: 100,
          }
        : v
    ));

    socketRef.current.emit("start_reid", {
      job_id: preparedJobId,
      cameras,
      save_to_db: true,
      emit_live_events: true,
      reid_config: buildReidConfigPayload(),
    });
  };

  const handleRerunReIDWithCurrentSettings = () => {
    if (isProcessing || isPreparing) return;

    const cameras = buildPreparedCameras(videos);
    if (!cameras.length || cameras.length !== videos.length) {
      setStatusMsg("Nu pot relua Re-ID: toate camerele trebuie sa fie uploadate in baza de date.");
      return;
    }

    autoStartReidAfterPrepareRef.current = true;
    activeReidJobIdRef.current = null;
    setPreparedJobId(null);
    setGlobalPeople({});
    setReidDetections({});
    setReidDebugItems([]);
    setSelectedGlobalId(null);
    setCompletedSessionId(null);
    setShowSidebar(true);
    setIsPreparing(true);
    setWarmupStatus("download_start");
    setStatusMsg("Pregatesc din nou camerele pe cluster pentru Re-ID...");
    setVideos(prev => prev.map(v =>
      v.backendVideoId
        ? {
            ...v,
            isProcessing: false,
            streamFrame: null,
            frameInfo: null,
            globalIds: [],
            activeToast: null,
            serverDownloadStatus: "downloading",
            downloadPercent: 0,
          }
        : v
    ));

    socketRef.current?.emit("prepare_reid", { cameras });
  };

  const handleResetReID = () => {
    autoStartReidAfterPrepareRef.current = false;
    activeReidJobIdRef.current = null;
    setWarmupStatus(null);
    setGlobalPeople({});
    setReidDetections({});
    setReidDebugItems([]);
    setSelectedGlobalId(null);
    setStatusMsg("");
    setShowSidebar(false);
    setPreparedJobId(null);
    setIsPreparing(false);
    setCompletedSessionId(null);
    setVideos(prev => prev.map(v => ({ ...v, serverDownloadStatus: 'pending', downloadPercent: 0 })));
  };

  const allUploaded      = videos.length > 0 && videos.every(v => v.backendVideoId);
  const allReadyOnCluster = allUploaded && videos.every(v => v.serverDownloadStatus === "ready");
  const allReadyForReid  = allReadyOnCluster && !!preparedJobId;
  const uploadedCount    = videos.filter(v => !!v.backendVideoId).length;
  const uploadingCount   = videos.filter(v => v.isUploading).length;
  const notUploadedCount = videos.filter(v => !v.backendVideoId && !v.isUploading).length;
  const hasGlobalPeople  = Object.keys(globalPeople).length > 0;
  const displayedVideos = expandedId ? videos.filter(v => v.id === expandedId) : videos;
  const gridStyle       = getCameraGridStyle(videos.length, expandedId);

  return (
    <div className="h-screen text-gray-100 flex flex-col overflow-hidden">

      {/* Top bar */}
      <div className="flex-shrink-0 flex items-center justify-between px-5 py-2.5 border-b border-white/[0.04] bg-[#0d0d10]/90 backdrop-blur-sm z-20">
        <div className="flex items-center gap-3">
          <Crosshair size={15} className="text-emerald-400" />
          <span className="text-sm font-semibold text-white tracking-wide">{t?.("tracking.title") || "Multi-Camera Tracking"}</span>
          {videos.length > 0 && <span className="text-[10px] font-mono text-zinc-600">{videos.length} {videos.length === 1 ? "camera" : "cameras"}</span>}
        </div>

        <div className="flex items-center gap-2">
          {statusMsg && <span className="text-[10px] text-zinc-400 font-mono max-w-xs truncate">{statusMsg}</span>}

          {/* Warmup / download progress badge */}
          {warmupStatus === "warmup" && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/25 text-yellow-300 text-[10px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" /> Pregătire...
            </span>
          )}
          {(warmupStatus === "download_start" || warmupStatus === "download_progress" || warmupStatus === "download_bytes") && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-blue-500/10 border border-blue-500/25 text-blue-300 text-[10px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-blue-400 animate-pulse" />
              Descărcare MinIO...
            </span>
          )}
          {warmupStatus === "processing_start" && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-yellow-500/10 border border-yellow-500/25 text-yellow-300 text-[10px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-yellow-400 animate-pulse" /> Re-ID pornit...
            </span>
          )}
          {warmupStatus === "reid_ready" && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-300 text-[10px] font-mono">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> Re-ID activ
            </span>
          )}
          {warmupStatus === "done" && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/15 border border-emerald-500/40 text-emerald-300 text-[10px] font-semibold">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" /> ✓ Re-ID Complete
            </span>
          )}

          {/* People count toggle */}
          {hasGlobalPeople && (
            <button onClick={() => setShowSidebar(s => !s)} className="flex items-center gap-1.5 px-2.5 py-1 bg-zinc-900 border border-zinc-700 hover:border-emerald-500/40 text-gray-300 text-[10px] rounded-lg transition">
              <Users size={10} className="text-emerald-400" />
              <span className="font-mono text-white">{Object.keys(globalPeople).length}</span>
              <span className="text-zinc-500">persoane</span>
              <ChevronRight size={9} className={`transition-transform ${showSidebar ? "rotate-180" : ""}`} />
            </button>
          )}

          {/* Prepare cameras */}
          {videos.length > 0 && !warmupStatus && (
            <button
              onClick={handlePrepareCameras}
              disabled={uploadingCount > 0 || isPreparing || isProcessing}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-blue-500/40 text-gray-300 text-[11px] font-medium rounded-lg transition disabled:opacity-60 disabled:cursor-wait"
            >
              <Database size={10} className="text-blue-400" />
              {uploadingCount > 0 || isPreparing
                ? "Preparing cameras..."
                : `Prepare cameras${notUploadedCount > 0 ? ` (${notUploadedCount})` : ""}`
              }
            </button>
          )}

          {/* Start Re-ID — enabled only after all cameras are in DB */}
          {videos.length > 0 && !warmupStatus && (
            <button
              onClick={handleStartReID}
              disabled={!allReadyForReid}
              title={!allReadyForReid ? "Pregateste camerele pe cluster mai intai." : "Porneste Re-ID multi-camera"}
              className={`flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded-lg transition
                ${allReadyForReid
                  ? "bg-emerald-600/80 hover:bg-emerald-500 text-black cursor-pointer"
                  : "bg-zinc-800 border border-zinc-700 text-zinc-500 cursor-not-allowed opacity-60"
                }`}
            >
              <Users size={10} /> Start Re-ID
              {!allReadyForReid && <span className="text-[9px] font-mono">({uploadedCount}/{videos.length})</span>}
            </button>
          )}

          {/* Reset Re-ID — shown after completion */}
          {warmupStatus === "done" && (
            <button
              onClick={handleResetReID}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 hover:border-emerald-500/40 text-gray-300 text-[11px] font-medium rounded-lg transition"
            >
              <RotateCcw size={10} className="text-emerald-400" /> New Re-ID
            </button>
          )}

          {/* View in History — shown after completion, links to saved session */}
          {warmupStatus === "done" && completedSessionId && (
            <Link
              to={`/tracking-history/${completedSessionId}`}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/80 hover:bg-emerald-500 text-black text-[11px] font-semibold rounded-lg transition"
            >
              View in History →
            </Link>
          )}

          {warmupStatus === "done" && (
            <button
              onClick={handleRerunReIDWithCurrentSettings}
              disabled={isPreparing || isProcessing || !allUploaded}
              title="Pregateste din nou camerele pe cluster si porneste Re-ID cu setarile curente"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-600/80 hover:bg-emerald-500 text-black text-[11px] font-semibold rounded-lg transition disabled:cursor-not-allowed disabled:opacity-50"
            >
              <RotateCcw size={10} /> Rerun with settings
            </button>
          )}

          {/* Stop All */}
          {(isProcessing || isPreparing || (warmupStatus && warmupStatus !== "done")) && (
            <button
              onClick={handleStopAll}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600/90 hover:bg-red-500 text-white text-[11px] font-semibold rounded-lg transition"
            >
              <Square size={10} fill="currentColor" /> Stop All
            </button>
          )}

          <button onClick={() => fileInputRef.current.click()} disabled={isProcessing || isPreparing} className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 hover:border-emerald-500/40 text-gray-300 text-[11px] font-medium rounded-lg transition disabled:opacity-50">
            <Plus size={10} /> Add camera
          </button>

          {expandedId && (
            <button onClick={() => setExpandedId(null)} className="flex items-center gap-1.5 px-2.5 py-1.5 bg-zinc-900 hover:bg-zinc-800 border border-zinc-700 text-gray-300 text-[11px] rounded-lg transition">
              <Minimize2 size={10} /> All cameras
            </button>
          )}

          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-emerald-500/10 border border-emerald-500/30 rounded-full">
            <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
            <span className="text-[10px] text-emerald-400 font-mono font-semibold">LIVE</span>
          </div>
        </div>
      </div>

      {videos.length > 0 && (!warmupStatus || warmupStatus === "done") && (
        <ReidSettingsPanel
          config={reidConfig}
          onPresetChange={handleReidPresetChange}
          onFieldChange={handleReidFieldChange}
          disabled={isPreparing || isProcessing}
        />
      )}

      <input type="file" accept="video/*" ref={fileInputRef} onChange={handleVideoUpload} className="hidden" multiple />

      {/* Main area */}
      <div className="flex-1 flex overflow-hidden">
        <div className="flex-1 relative overflow-hidden">
          {reidConfig.emit_debug_info && <ReidDebugPanel items={reidDebugItems} />}
          {videos.length === 0 ? (
            <div onClick={() => fileInputRef.current.click()} className="absolute inset-0 flex flex-col items-center justify-center cursor-pointer group">
              <div className="border-2 border-dashed border-zinc-800 group-hover:border-emerald-500/40 rounded-2xl p-12 transition-all text-center">
                <div className="inline-flex p-4 bg-emerald-500/10 rounded-xl mb-4 group-hover:bg-emerald-500/15 transition">
                  <Video size={28} className="text-emerald-400" />
                </div>
                <p className="text-sm font-semibold text-white mb-1">Add camera feeds</p>
                <p className="text-xs text-zinc-500">Click or drag video files here</p>
                <p className="text-[11px] text-zinc-700 mt-2">MP4, MOV, AVI, MKV supported</p>
              </div>
            </div>
          ) : (
            <div className="absolute inset-0 grid" style={{ ...gridStyle, gap: "1px", backgroundColor: "#111114" }}>
              {displayedVideos.map((video, index) => (
                <div key={video.id} className="relative overflow-hidden bg-black group">
                  <CameraCell
                    video={video}
                    index={index}
                    isExpanded={expandedId === video.id}
                    onExpand={id => setExpandedId(expandedId === id ? null : id)}
                    onRemove={id => setVideos(prev => prev.filter(v => v.id !== id))}
                    reidDetections={reidDetections}
                  />
                  <button onClick={() => setConfigVideo(video)} className="absolute bottom-2 left-2 p-1 rounded bg-black/50 hover:bg-white/10 text-zinc-600 hover:text-zinc-300 transition opacity-0 group-hover:opacity-100" style={{ zIndex: 20 }}>
                    <Settings size={9} />
                  </button>
                </div>
              ))}

              {videos.length === 3 && !expandedId && (
                <div onClick={() => fileInputRef.current.click()} className="bg-zinc-950 flex items-center justify-center cursor-pointer hover:bg-zinc-900 transition group">
                  <div className="flex flex-col items-center gap-1.5 text-zinc-700 group-hover:text-zinc-500 transition">
                    <Plus size={18} />
                    <span className="text-[9px] font-mono">Add camera</span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <GlobalPeopleSidebar
          people={globalPeople}
          isVisible={showSidebar}
          onSelectPerson={setSelectedGlobalId}
        />
      </div>

      <GlobalPersonModal
        gid={selectedGlobalId}
        info={selectedGlobalId ? globalPeople[selectedGlobalId] : null}
        onClose={() => setSelectedGlobalId(null)}
      />

      {configVideo && (
        <CameraConfigDrawer
          video={configVideo}
          onClose={() => setConfigVideo(null)}
          onMetaChange={(id, key, val) => {
            handleCameraMetaChange(id, key, val);
            setConfigVideo(prev => prev ? { ...prev, [key]: val } : prev);
          }}
        />
      )}
    </div>
  );
}




