import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Activity,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  Download,
  Eye,
  FileVideo,
  Flame,
  Gauge,
  Layers,
  Loader2,
  Maximize2,
  PlayCircle,
  Share2,
  ShieldCheck,
  Users,
} from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";
import { useProcessing } from "../contexts/ProcessingContext";

const API_URL = import.meta.env.VITE_API_URL;

function useText() {
  const { t } = useLanguage();
  return (key, fallback) => {
    const value = t(key);
    return value === key ? fallback : value;
  };
}

function formatNumber(value, digits = 0) {
  const n = Number(value ?? 0);
  return Number.isFinite(n) ? n.toFixed(digits) : (0).toFixed(digits);
}

function StatTile({ icon: Icon, label, value, sublabel, tone = "emerald" }) {
  const tones = {
    emerald: "border-emerald-500/20 bg-emerald-500/[0.055] text-emerald-300",
    amber: "border-amber-500/20 bg-amber-500/[0.055] text-amber-300",
    orange: "border-orange-500/20 bg-orange-500/[0.055] text-orange-300",
    cyan: "border-cyan-500/20 bg-cyan-500/[0.055] text-cyan-300",
    zinc: "border-white/10 bg-white/[0.035] text-zinc-300",
  };

  return (
    <div className={`rounded-lg border ${tones[tone]} p-4`}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <span className="text-[10px] font-black uppercase tracking-[0.18em] text-zinc-500">{label}</span>
        <Icon size={16} className="shrink-0 opacity-90" />
      </div>
      <div className="text-3xl font-black tracking-tight text-white">{value}</div>
      <div className="mt-1 text-[11px] font-mono text-zinc-500">{sublabel}</div>
    </div>
  );
}

function ActionButton({ children, onClick, disabled, active, title }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex h-10 items-center justify-center gap-2 rounded-lg border px-3 text-[11px] font-black uppercase tracking-[0.12em] transition
        ${active
          ? "border-emerald-400/40 bg-emerald-500 text-black shadow-[0_0_28px_rgba(16,185,129,0.18)]"
          : "border-white/10 bg-white/[0.045] text-zinc-300 hover:border-emerald-400/35 hover:bg-white/[0.07]"
        }
        ${disabled ? "cursor-not-allowed opacity-45 hover:border-white/10 hover:bg-white/[0.045]" : ""}`}
    >
      {children}
    </button>
  );
}

export default function WatchVideo() {
  const { videoId } = useParams();
  const navigate = useNavigate();
  const tx = useText();
  const { activeJob } = useProcessing();

  const [copied, setCopied] = useState(false);
  const [variant, setVariant] = useState("normal");
  const [hasHeatmap, setHasHeatmap] = useState(false);
  const [mediaType, setMediaType] = useState("video");
  const [mediaError, setMediaError] = useState(false);
  const [metadata, setMetadata] = useState(null);
  const [loadingMetadata, setLoadingMetadata] = useState(true);
  const autoVariantVideoRef = useRef(null);

  const isActivelyProcessing = activeJob.videoId &&
    String(activeJob.videoId) === String(videoId) &&
    activeJob.status === "processing";

  const processingMode = metadata?.processing_mode;
  const isCrowdVideo = processingMode ? processingMode === "crowd" : Boolean(metadata?.dm_model_used && metadata.dm_model_used !== "tracking");
  const isTrackingVideo = processingMode === "tracking";
  const effectiveHasHeatmap = hasHeatmap || Boolean(metadata?.has_heatmap);

  const variantsUrl = `${API_URL}/api/video/watch/${videoId}/variants`;
  const videoUrl = `${API_URL}/api/video/watch/${videoId}?variant=${variant}`;
  const metadataUrl = `${API_URL}/api/videos/${videoId}/metadata`;
  const shareUrl = window.location.href;

  const analysisMode = useMemo(() => {
    if (isCrowdVideo) return `${tx("watch.crowdModel", "Crowd model")}: ${(metadata?.dm_model_used || "").toUpperCase()}`;
    if (isTrackingVideo) return tx("watch.trackingMode", "Tracking");
    return "YOLO detection";
  }, [isCrowdVideo, isTrackingVideo, metadata?.dm_model_used, tx]);

  useEffect(() => {
    let mounted = true;

    const loadVariants = async () => {
      try {
        const res = await fetch(variantsUrl);
        if (!res.ok) throw new Error("variants unavailable");
        const data = await res.json();
        if (mounted) setHasHeatmap(Boolean(data.heatmap_available));
      } catch {
        if (mounted) setHasHeatmap(false);
      }
    };

    loadVariants();
    return () => {
      mounted = false;
    };
  }, [variantsUrl]);

  useEffect(() => {
    let mounted = true;

    const loadMetadata = async () => {
      try {
        setLoadingMetadata(true);
        const token = localStorage.getItem("token") || localStorage.getItem("access_token");
        const headers = token ? { Authorization: `Bearer ${token}` } : {};
        const res = await fetch(metadataUrl, { headers });
        if (!res.ok) throw new Error("metadata unavailable");
        const data = await res.json();
        if (mounted) setMetadata(data);
      } catch {
        if (mounted) setMetadata(null);
      } finally {
        if (mounted) setLoadingMetadata(false);
      }
    };

    loadMetadata();
    return () => {
      mounted = false;
    };
  }, [metadataUrl]);

  useEffect(() => {
    let mounted = true;

    const detectType = async () => {
      try {
        const res = await fetch(videoUrl, { method: "HEAD" });
        const contentType = (res.headers.get("content-type") || "").toLowerCase();
        if (mounted) setMediaType(contentType.startsWith("image/") ? "image" : "video");
      } catch {
        if (mounted) setMediaType("video");
      }
    };

    detectType();
    return () => {
      mounted = false;
    };
  }, [videoUrl]);

  useEffect(() => {
    setMediaError(false);
  }, [variant, videoId]);

  useEffect(() => {
    if (autoVariantVideoRef.current === videoId) return;
    setVariant(isCrowdVideo && effectiveHasHeatmap ? "heatmap" : "normal");
    autoVariantVideoRef.current = videoId;
  }, [videoId, isCrowdVideo, effectiveHasHeatmap]);

  const copyShareLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const openFullscreen = () => {
    const media = document.getElementById("analysis-media");
    if (media?.requestFullscreen) media.requestFullscreen();
  };

  return (
    <div className="min-h-screen overflow-hidden text-zinc-100 selection:bg-emerald-500/30">
      <div
        className="pointer-events-none fixed inset-0 opacity-[0.05]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(53,209,123,0.32) 1px, transparent 1px), linear-gradient(90deg, rgba(53,209,123,0.32) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
        }}
      />
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_20%_0%,rgba(16,185,129,0.18),transparent_30%),radial-gradient(circle_at_85%_10%,rgba(6,182,212,0.12),transparent_28%),linear-gradient(180deg,rgba(8,9,11,0)_0%,#08090b_82%)]" />

      <main className="relative z-10 mx-auto flex min-h-screen max-w-[1680px] flex-col px-4 py-4 sm:px-6 lg:px-8">
        <header className="mb-4 flex flex-col gap-3 border-b border-white/10 pb-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => navigate("/dashboard")}
              className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-white/[0.045] text-zinc-400 transition hover:border-emerald-400/35 hover:text-white"
              title={tx("common.returnToDashboard", "Return to Dashboard")}
            >
              <ArrowLeft size={18} />
            </button>
            <div className="min-w-0">
              <div className="mb-1 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-2 py-1 text-[10px] font-black uppercase tracking-[0.16em] text-emerald-300">
                  <ShieldCheck size={12} />
                  {tx("watch.securePlayback", "Secure playback")}
                </span>
                <span className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] font-mono uppercase text-zinc-500">
                  REF {videoId}
                </span>
              </div>
              <h1 className="truncate text-xl font-black tracking-tight text-white sm:text-2xl">
                {tx("watch.analysisViewer", "Analysis Viewer")}
              </h1>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <ActionButton
              onClick={() => setVariant((prev) => (prev === "normal" ? "heatmap" : "normal"))}
              disabled={!effectiveHasHeatmap}
              active={variant === "heatmap" && effectiveHasHeatmap}
              title={effectiveHasHeatmap ? tx("watch.heatmapToggleTitle", "Toggle heatmap") : tx("watch.heatmapUnavailable", "Heatmap unavailable")}
            >
              <Flame size={15} />
              {variant === "heatmap" ? tx("watch.heatmapOn", "Heatmap on") : tx("watch.heatmapOff", "Heatmap off")}
            </ActionButton>
            <ActionButton onClick={openFullscreen}>
              <Maximize2 size={15} />
              {tx("common.fullScreen", "Full Screen")}
            </ActionButton>
            <ActionButton onClick={copyShareLink}>
              {copied ? <CheckCircle2 size={15} className="text-emerald-300" /> : <Share2 size={15} />}
              {copied ? tx("common.linkCopied", "Link copied") : tx("common.shareAnalysis", "Share Analysis")}
            </ActionButton>
            <a
              href={videoUrl}
              download={`analysis_export_${videoId}.${mediaType === "image" ? "jpg" : "mp4"}`}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-emerald-500 px-4 text-[11px] font-black uppercase tracking-[0.12em] text-black shadow-[0_0_32px_rgba(16,185,129,0.2)] transition hover:bg-emerald-400"
            >
              <Download size={15} />
              {tx("common.downloadResult", "Download Result")}
            </a>
          </div>
        </header>

        {isActivelyProcessing && (
          <section className="mb-4 rounded-lg border border-amber-400/25 bg-amber-400/[0.07] p-3">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <span className="relative flex h-3 w-3">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-60" />
                  <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-300" />
                </span>
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.16em] text-amber-200">Processing in background</p>
                  <p className="text-[11px] font-mono text-amber-100/70">
                    {activeJob.progress}% complete · {activeJob.peopleCount} people detected
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => navigate("/detection")}
                className="h-9 rounded-lg border border-amber-300/30 px-3 text-[11px] font-black uppercase tracking-[0.12em] text-amber-100 transition hover:bg-amber-300/10"
              >
                View live
              </button>
            </div>
          </section>
        )}

        <section className="grid flex-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0">
            <div className="overflow-hidden rounded-lg border border-white/10 bg-black shadow-[0_28px_90px_rgba(0,0,0,0.52)]">
              <div className="flex items-center justify-between border-b border-white/10 bg-[#0d0f13] px-4 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-300">
                    <PlayCircle size={18} />
                  </div>
                  <div>
                    <p className="text-sm font-black text-white">{variant === "heatmap" ? tx("watch.heatmapOverlay", "Heatmap overlay") : tx("watch.normalView", "Normal view")}</p>
                    <p className="text-[11px] font-mono uppercase text-zinc-500">{analysisMode}</p>
                  </div>
                </div>
                <div className="hidden items-center gap-2 sm:flex">
                  <span className="h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_12px_rgba(52,211,153,0.9)]" />
                  <span className="text-[10px] font-black uppercase tracking-[0.16em] text-zinc-500">
                    {loadingMetadata ? tx("common.loading", "Loading...") : (metadata?.status || tx("common.unknown", "Unknown"))}
                  </span>
                </div>
              </div>

              <div id="analysis-media" className="relative aspect-video bg-black">
                <div className="pointer-events-none absolute left-0 right-0 top-0 z-10 flex justify-between bg-gradient-to-b from-black/70 to-transparent p-4">
                  <span className="rounded border border-emerald-400/25 bg-black/50 px-2 py-1 text-[10px] font-mono font-black uppercase tracking-[0.12em] text-emerald-300">
                    AI output
                  </span>
                  {variant === "heatmap" && (
                    <span className="rounded border border-orange-400/25 bg-orange-500/10 px-2 py-1 text-[10px] font-mono font-black uppercase tracking-[0.12em] text-orange-200">
                      Density layer
                    </span>
                  )}
                </div>

                {!mediaError && mediaType === "image" && (
                  <img
                    key={`img-${videoId}-${variant}`}
                    src={videoUrl}
                    alt={`processed-${videoId}`}
                    className="h-full w-full object-contain"
                    onError={() => setMediaError(true)}
                  />
                )}

                {!mediaError && mediaType !== "image" && (
                  <video
                    key={`vid-${videoId}-${variant}`}
                    src={videoUrl}
                    controls
                    autoPlay
                    className="h-full w-full object-contain"
                    onError={() => setMediaError(true)}
                  />
                )}

                {mediaError && (
                  <div className="flex h-full flex-col items-center justify-center gap-4 p-8 text-center">
                    <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-red-400/25 bg-red-500/10 text-2xl font-black text-red-300">
                      !
                    </div>
                    <div>
                      <h2 className="text-sm font-black uppercase tracking-[0.18em] text-red-300">
                        {tx("watch.mediaErrorTitle", "Media unavailable")}
                      </h2>
                      <p className="mt-2 max-w-md text-sm text-zinc-500">
                        {tx("watch.mediaErrorBody", "The processed media could not be loaded. Try downloading the result or returning to the dashboard.")}
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>

          <aside className="grid content-start gap-4 xl:sticky xl:top-4">
            <div className="rounded-lg border border-white/10 bg-[#0d0f13]/90 p-4">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">Run summary</p>
                  <h2 className="mt-1 text-base font-black text-white">Detection metrics</h2>
                </div>
                {loadingMetadata && <Loader2 size={18} className="animate-spin text-emerald-300" />}
              </div>

              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-1">
                <StatTile
                  icon={Users}
                  label={tx("watch.uniquePeople", "Total people")}
                  value={loadingMetadata ? "--" : metadata?.total_unique_people ?? 0}
                  sublabel={tx("watch.totalTrackedIndividuals", "People counted in run")}
                  tone="emerald"
                />
                <StatTile
                  icon={CheckCircle2}
                  label={tx("watch.processingStatus", "Status")}
                  value={loadingMetadata ? "--" : metadata?.status || "Unknown"}
                  sublabel={tx("watch.analysisState", "Analysis state")}
                  tone="amber"
                />
                <StatTile
                  icon={BarChart3}
                  label={tx("watch.peakCount", "Peak count")}
                  value={loadingMetadata ? "--" : metadata?.max_people_in_frame ?? 0}
                  sublabel={isCrowdVideo ? tx("watch.maxInFrame", "Max in frame (DM-Count)") : tx("watch.maxInFrameGeneric", "Maximum people in frame")}
                  tone="orange"
                />
                <StatTile
                  icon={Gauge}
                  label={tx("watch.avgCount", "Avg count")}
                  value={loadingMetadata ? "--" : formatNumber(metadata?.avg_people_per_frame, 1)}
                  sublabel={isCrowdVideo ? tx("watch.avgInFrame", "Avg per frame (DM-Count)") : tx("watch.avgInFrameGeneric", "Average people per frame")}
                  tone="cyan"
                />
              </div>
            </div>

            <div className="rounded-lg border border-white/10 bg-[#0d0f13]/90 p-4">
              <p className="mb-3 text-[10px] font-black uppercase tracking-[0.2em] text-zinc-500">Playback stack</p>
              <div className="space-y-3 text-sm">
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-zinc-400"><Layers size={15} /> View</span>
                  <span className="font-mono text-zinc-200">{variant === "heatmap" ? "Heatmap" : "Normal"}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-zinc-400"><Activity size={15} /> Mode</span>
                  <span className="max-w-[180px] truncate font-mono text-zinc-200">{analysisMode}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-zinc-400"><FileVideo size={15} /> Media</span>
                  <span className="font-mono text-zinc-200">{mediaType === "image" ? "Image" : "MPEG-4 / H.264"}</span>
                </div>
                <div className="flex items-center justify-between gap-3">
                  <span className="flex items-center gap-2 text-zinc-400"><Eye size={15} /> Heatmap</span>
                  <span className={`font-mono ${effectiveHasHeatmap ? "text-emerald-300" : "text-zinc-500"}`}>
                    {effectiveHasHeatmap ? "Available" : "Unavailable"}
                  </span>
                </div>
              </div>
            </div>
          </aside>
        </section>
      </main>
    </div>
  );
}
