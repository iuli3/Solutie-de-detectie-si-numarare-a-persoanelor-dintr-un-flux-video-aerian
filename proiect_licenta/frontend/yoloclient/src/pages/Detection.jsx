import { useState, useRef, useEffect } from "react";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL;
import { Youtube, Link2 } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useLanguage } from "../contexts/LanguageContext";
import { useProcessing } from "../contexts/ProcessingContext";

import { MODES, MODE_COLORS, CHART_LEN } from "../components/detection/constants";
import ModeSelector from "../components/detection/ModeSelector";
import StatsBar from "../components/detection/StatsBar";
import VideoDisplay from "../components/detection/VideoDisplay";
import ControlPanel from "../components/detection/ControlPanel";
import LiveStatsPanel from "../components/detection/LiveStatsPanel";
import { YoutubeModal, LiveStreamModal } from "../components/detection/Modals";

export default function Detection() {
  const { t } = useLanguage();
  const navigate = useNavigate();
  const { socket: ctxSocket, activeJob, startJob, clearJob } = useProcessing();

  // ── State ────────────────────────────────────────────────────────────────
  const [, setVideoSrc] = useState(null);
  const [uploadMessage, setUploadMessage] = useState("");
  const [results, setResults] = useState(null);
  const [streamFrame, setStreamFrame] = useState(null);
  const [heatmapFrame, setHeatmapFrame] = useState(null);
  const [frameInfo, setFrameInfo] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [totalDetections, setTotalDetections] = useState(0);
  const [, setFileName] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isPlaying, setIsPlaying] = useState(true);
  const [currentMetadata, setCurrentMetadata] = useState([]);
  const [selectedIds, setSelectedIds] = useState([]);
  const [videoId, setVideoId] = useState(null);
  const [fps, setFps] = useState(0);
  const [latency, setLatency] = useState(0);
  const [avgInference, setAvgInference] = useState(0);
  const [processedVideoUrl, setProcessedVideoUrl] = useState(null);
  const [showReplayPlayer, setShowReplayPlayer] = useState(false);
  const [uniquePeopleCount, setUniquePeopleCount] = useState(0);
  const [fileType, setFileType] = useState(null);
  const [processedImageUrl, setProcessedImageUrl] = useState(null);
  const [densityCoeff, setDensityCoeff] = useState(0);
  const [heatmapOpacity, setHeatmapOpacity] = useState(70);
  const [dataSource, setDataSource] = useState("video");
  const [showYoutubeModal, setShowYoutubeModal] = useState(false);
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [showLiveModal, setShowLiveModal] = useState(false);
  const [liveUrl, setLiveUrl] = useState("");
  const [selectedMode, setSelectedMode] = useState("detection");
  const [densityHistory, setDensityHistory] = useState(Array(CHART_LEN).fill(0));
  const [countHistory, setCountHistory] = useState(Array(CHART_LEN).fill(0));
  const [dmCount, setDmCount] = useState(null);

  const currentMode = MODES.find(m => m.id === selectedMode);
  const currentModeLabel = t(currentMode?.labelKey || currentMode?.label || "");
  const isCrowdMode = selectedMode !== "detection";
  const mc = MODE_COLORS[selectedMode];

  // ── Refs ─────────────────────────────────────────────────────────────────
  const fileInputRef = useRef(null);
  const socketRef = useRef(null);
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const videoIdRef = useRef(null);
  const uniqueIdsRef = useRef(new Set());
  const lastFrameTime = useRef(Date.now());

  // ── Reset helper ──────────────────────────────────────────────────────────
  const resetAllState = () => {
    setVideoSrc(null); setStreamFrame(null); setHeatmapFrame(null); setFrameInfo(null);
    setResults(null); setCurrentMetadata([]); setSelectedIds([]); setVideoId(null);
    setProcessedVideoUrl(null); setProcessedImageUrl(null); setFileType(null);
    setShowReplayPlayer(false); setIsProcessing(false); setTotalDetections(0);
    setHeatmapOpacity(70); setSelectedMode("detection");
    setUploadMessage(""); uniqueIdsRef.current = new Set(); setUniquePeopleCount(0);
    setDmCount(null); setDensityHistory(Array(CHART_LEN).fill(0));
    setCountHistory(Array(CHART_LEN).fill(0));
    videoIdRef.current = null;
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const toTimestampMs = (ts) => {
    if (ts === null || ts === undefined || ts === "") return null;
    const value = Number(ts);
    if (!Number.isFinite(value)) return null;
    if (value > 1e12) return value;
    if (value > 1e9) return value * 1000;
    return null;
  };

  const getFrameTimestampMs = (data) => {
    const candidates = [
      data.timestamp_ms,
      data.server_timestamp_ms,
      data.relay_timestamp_ms,
      data.timestamp,
      data.server_timestamp,
    ];
    for (const candidate of candidates) {
      const tsMs = toTimestampMs(candidate);
      if (tsMs !== null) return tsMs;
    }
    return null;
  };
  const getDetectionRect = (bbox) => {
    if (!Array.isArray(bbox) || bbox.length < 4) return null;
    const [x, y, width, height] = bbox.map(Number);
    if (![x, y, width, height].every(Number.isFinite)) return null;
    return { x, y, width, height };
  };

  const getContainedImageMetrics = () => {
    const img = imageRef.current;
    const canvas = canvasRef.current;
    if (!img) return null;

    const containerW = img.clientWidth || img.getBoundingClientRect().width;
    const containerH = img.clientHeight || img.getBoundingClientRect().height;
    const naturalW = img.naturalWidth || 1280;
    const naturalH = img.naturalHeight || 720;
    if (!containerW || !containerH || !naturalW || !naturalH) return null;

    const scale = Math.min(containerW / naturalW, containerH / naturalH);
    const displayW = naturalW * scale;
    const displayH = naturalH * scale;
    const offsetX = (containerW - displayW) / 2;
    const offsetY = (containerH - displayH) / 2;

    return {
      containerW,
      containerH,
      naturalW,
      naturalH,
      displayW,
      displayH,
      offsetX,
      offsetY,
      scaleX: displayW / naturalW,
      scaleY: displayH / naturalH,
      canvasW: canvas?.width || containerW,
      canvasH: canvas?.height || containerH,
    };
  };

  useEffect(() => { videoIdRef.current = videoId; }, [videoId]);

  // ── Socket (from global ProcessingContext — persists across navigation) ───
  useEffect(() => { socketRef.current = ctxSocket; }, [ctxSocket]);

  // Restore UI state when returning to page during an active job
  useEffect(() => {
    if (activeJob.status === 'processing' && activeJob.videoId) {
      videoIdRef.current = activeJob.videoId;
      setVideoId(activeJob.videoId);
      setIsProcessing(true);
      if (activeJob.fileName) setFileName(activeJob.fileName);
      setFrameInfo({
        progress: activeJob.progress,
        peopleCount: activeJob.peopleCount,
        frameNumber: activeJob.frameNumber,
        totalFrames: activeJob.totalFrames,
      });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const socket = ctxSocket;
    if (!socket) return;

    const onConnect = () => console.log("🚀 Connected to OverWatch Cluster Gateway");

    const onFrame = (data) => {
      if (!data.frame) return;
      if (videoIdRef.current && data.video_id && String(data.video_id) !== String(videoIdRef.current)) return;
      const now = Date.now();
      const delta = (now - lastFrameTime.current) / 1000;
      if (delta > 0) setFps(Math.round(1 / delta));
      lastFrameTime.current = now;
      const tsMs = getFrameTimestampMs(data);
      if (tsMs !== null) {
        const latencyMs = now - tsMs;
        if (latencyMs >= 0 && latencyMs < 10 * 60 * 1000) {
          setLatency(Math.max(1, Math.round(latencyMs)));
        }
      }
      if (data.inference_time)
        setAvgInference(prev => prev === 0 ? data.inference_time : (prev * 0.9 + data.inference_time * 0.1));
      if (data.density_coeff !== undefined) {
        setDensityCoeff(data.density_coeff);
        setDensityHistory(prev => [...prev.slice(1), data.density_coeff]);
      }
      if (data.people_count !== undefined)
        setCountHistory(prev => [...prev.slice(1), data.people_count]);
      if (data.people_count_dmcount != null)
        setDmCount(data.people_count_dmcount);
      setStreamFrame(`data:image/jpeg;base64,${data.frame}`);
      setHeatmapFrame(data.heatmap ? `data:image/jpeg;base64,${data.heatmap}` : null);
      const progress = Math.max(0, Math.min(100,
        data.total_frames && data.frame_number >= data.total_frames ? 100 : Number(data.progress || 0)
      ));
      setFrameInfo(prev => ({ ...(prev || {}), frameNumber: data.frame_number, totalFrames: data.total_frames, peopleCount: data.people_count, progress, resolution: data.width && data.height ? `${data.width}x${data.height}` : (prev?.resolution || "1280x720") }));
      if (data.metadata) {
        setCurrentMetadata(data.metadata);
        data.metadata.forEach(p => { if (p.id != null) uniqueIdsRef.current.add(p.id); });
        setUniquePeopleCount(uniqueIdsRef.current.size);
      }
      setTotalDetections(prev => prev + data.people_count);
    };

    const onStatusUpdate = (data) => setUploadMessage(data.msg);

    const onProcessingComplete = (stats) => {
      if (stats.video_id && videoIdRef.current && String(stats.video_id) !== String(videoIdRef.current)) return;
      setResults({
        unique_people: stats.unique_people || 0,
        max_people_in_frame: stats.max_people_in_frame || 0,
        avg_people_per_frame: stats.avg_people_per_frame || 0,
        processing_time: stats.processing_time || 0,
        resolution: stats.resolution || "1280x720",
      });
      const vid = stats.video_id || videoIdRef.current;
      if (vid && !String(vid).startsWith('live_'))
        setProcessedVideoUrl(`${API_URL}/api/video/watch/${vid}?variant=normal`);
      setUniquePeopleCount(stats.unique_people || stats.max_people_in_frame || 0);
      setFrameInfo(prev => ({
        ...(prev || {}),
        progress: 100,
        peopleCount: prev?.peopleCount || 0,
        resolution: stats.resolution || prev?.resolution || "1280x720",
      }));
      setIsProcessing(false);
      setUploadMessage(`✅ ${t("detection.processingComplete")}`);
    };

    socket.on("connect", onConnect);
    socket.on("frame", onFrame);
    socket.on("status_update", onStatusUpdate);
    socket.on("processing_complete", onProcessingComplete);

    return () => {
      socket.off("connect", onConnect);
      socket.off("frame", onFrame);
      socket.off("status_update", onStatusUpdate);
      socket.off("processing_complete", onProcessingComplete);
    };
  }, [ctxSocket, t]);

  // ── Logout cleanup ────────────────────────────────────────────────────────
  useEffect(() => {
    const handleLogout = () => {
      setIsPlaying(false);
      if (processedImageUrl?.startsWith('blob:')) URL.revokeObjectURL(processedImageUrl);
      resetAllState();
    };
    window.addEventListener("user-logout", handleLogout);
    return () => window.removeEventListener("user-logout", handleLogout);
  }, [processedImageUrl]);

  // ── Canvas tracking paths ─────────────────────────────────────────────────
  useEffect(() => {
    if (!canvasRef.current || !imageRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    const metrics = getContainedImageMetrics();
    if (!metrics) return;
    // Resetăm dimensiunile DOAR dacă s-au schimbat — altfel browser-ul repaintează
    // canvas-ul (flash de alb/transparent) pe fiecare frame, cauzând artefacte vizuale
    if (canvas.width !== metrics.containerW || canvas.height !== metrics.containerH) {
      canvas.width = metrics.containerW;
      canvas.height = metrics.containerH;
    }
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (isCrowdMode) return;

    selectedIds.forEach(id => {
      const person = currentMetadata.find(p => p.id === id);
      if (!person?.path) return;
      ctx.beginPath(); ctx.strokeStyle = "#00e676"; ctx.lineWidth = 3; // EMERALD path
      person.path.forEach((point, i) => {
        const x = metrics.offsetX + point[0] * metrics.scaleX;
        const y = metrics.offsetY + point[1] * metrics.scaleY;
        if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
      });
      ctx.stroke();
      const rect = getDetectionRect(person.bbox);
      if (!rect) return;
      const w = rect.width * metrics.scaleX;
      const h = rect.height * metrics.scaleY;
      const x = metrics.offsetX + rect.x * metrics.scaleX;
      const y = metrics.offsetY + rect.y * metrics.scaleY;
      ctx.strokeStyle = "#69f0ae"; ctx.lineWidth = 2; // EMERALD bbox
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = "#69f0ae"; ctx.font = "bold 12px monospace";
      ctx.fillText(`ID: ${id}`, x, y - 5);
    });
  }, [streamFrame, currentMetadata, selectedIds, isCrowdMode]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleVideoClick = (e) => {
    if (!imageRef.current || isCrowdMode) return;
    const rect = imageRef.current.getBoundingClientRect();
    const metrics = getContainedImageMetrics();
    if (!metrics) return;
    const localX = e.clientX - rect.left;
    const localY = e.clientY - rect.top;
    if (
      localX < metrics.offsetX ||
      localX > metrics.offsetX + metrics.displayW ||
      localY < metrics.offsetY ||
      localY > metrics.offsetY + metrics.displayH
    ) {
      return;
    }
    const realX = (localX - metrics.offsetX) / metrics.scaleX;
    const realY = (localY - metrics.offsetY) / metrics.scaleY;
    for (let i = currentMetadata.length - 1; i >= 0; i--) {
      const p = currentMetadata[i];
      const bbox = getDetectionRect(p.bbox);
      if (!bbox) continue;
      if (realX >= bbox.x && realX <= bbox.x + bbox.width && realY >= bbox.y && realY <= bbox.y + bbox.height) {
        setSelectedIds(prev => prev.includes(p.id) ? prev.filter(id => id !== p.id) : [...prev, p.id]);
        break;
      }
    }
  };

  const handleModeChange = (modeId) => {
    setSelectedMode(modeId);
    const mode = MODES.find(m => m.id === modeId);
    if (socketRef.current && videoId && isProcessing)
      socketRef.current.emit("update_mode", { video_id: videoId, mode: mode.payload.mode, dm_model: mode.payload.dm_model });
    setDensityHistory(Array(CHART_LEN).fill(0));
    setCountHistory(Array(CHART_LEN).fill(0));
    setDmCount(null);
  };

  const handleLiveStreamSubmit = () => {
    if (!liveUrl.trim()) { setUploadMessage(`⚠️ ${t("detection.enterLiveUrl")}`); return; }
    const generatedVideoId = "live_" + Date.now();
    videoIdRef.current = generatedVideoId; setVideoId(generatedVideoId);
    uniqueIdsRef.current = new Set(); setUniquePeopleCount(0);
    setUploadMessage(`📡 ${t("detection.connectingLive")}`);
    setIsProcessing(true); setShowLiveModal(false);
    socketRef.current.emit("start_processing", {
      video_id: generatedVideoId, filename: t("detection.liveCamName"), stream_url: liveUrl,
      mode: currentMode.payload.mode, dm_model: currentMode.payload.dm_model
    });
    startJob(generatedVideoId, liveUrl);
    setLiveUrl("");
  };

  const handleVideoUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    const isImage = file.type.startsWith('image/');
    const isVideo = file.type.startsWith('video/');
    if (!isImage && !isVideo) { setUploadMessage(`⚠️ ${t("detection.unsupportedFile")}`); return; }
    setFileType(isImage ? 'image' : 'video');
    setUploadMessage(
      file.size > 50 * 1024 * 1024
        ? `⚡ ${t("detection.largeFileCompress")}`
        : t("detection.uploadingToCluster", { type: isImage ? "image" : "video" })
    );
    const storedToken = localStorage.getItem("token");
    setFileName(file.name); setVideoSrc(URL.createObjectURL(file));
    setUploadProgress(0); setIsUploading(true);
    setDensityHistory(Array(CHART_LEN).fill(0)); setCountHistory(Array(CHART_LEN).fill(0)); setDmCount(null);
    const formData = new FormData();
    formData.append("video", file);

    if (isImage) {
      try {
        const res = await axios.post(`${API_URL}/upload`, formData, {
          headers: { "Authorization": `Bearer ${storedToken}` },
          onUploadProgress: (p) => setUploadProgress(Math.round((p.loaded * 100) / p.total)),
        });
        setIsUploading(false); setUploadMessage(t("detection.imageProcessing")); setIsProcessing(true);
        const processRes = await axios.post(`${API_URL}/process_image`,
          { filename: file.name, video_id: res.data.video_id },
          { headers: { "Authorization": `Bearer ${storedToken}` } }
        );
        setIsProcessing(false); setUploadMessage(t("detection.processingComplete"));
        if (processRes.data.image_url) {
          const imgResponse = await axios.get(`${API_URL}${processRes.data.image_url}`, {
            headers: { "Authorization": `Bearer ${storedToken}` }, responseType: 'blob'
          });
          setProcessedImageUrl(URL.createObjectURL(imgResponse.data));
        } else if (processRes.data.processed_image) {
          setProcessedImageUrl(`data:image/jpeg;base64,${processRes.data.processed_image}`);
        }
        setResults({ unique_people: processRes.data.people_count || 0, total_detections: processRes.data.people_count || 0, processing_time: processRes.data.processing_time || 0, resolution: processRes.data.resolution || "N/A" });
        setTotalDetections(processRes.data.people_count || 0);
        setUniquePeopleCount(processRes.data.people_count || 0);
      } catch {
        setUploadMessage(t("detection.imageProcessingError")); setIsUploading(false); setIsProcessing(false);
      }
    } else {
      try {
        const res = await axios.post(`${API_URL}/upload`, formData, {
          headers: { "Authorization": `Bearer ${storedToken}` },
          onUploadProgress: (p) => setUploadProgress(Math.round((p.loaded * 100) / p.total)),
        });
        setIsUploading(false); setIsProcessing(true);
        uniqueIdsRef.current = new Set(); setUniquePeopleCount(0);
        videoIdRef.current = res.data.video_id; setVideoId(res.data.video_id);
        socketRef.current.emit("start_processing", {
          filename: file.name, video_id: res.data.video_id, user_id: res.data.user_id,
          mode: currentMode.payload.mode, dm_model: currentMode.payload.dm_model
        });
        startJob(res.data.video_id, file.name);
      } catch { setUploadMessage(t("detection.uploadError")); setIsUploading(false); }
    }
  };

  const handleRemoveVideo = async () => {
    const storedToken = localStorage.getItem("token");
    if (isProcessing && videoId && socketRef.current)
      socketRef.current.emit("stop_processing", { video_id: videoId });
    videoIdRef.current = null;
    if (videoId && !String(videoId).startsWith('live_'))
      await axios.delete(`${API_URL}/api/videos/${videoId}`, { headers: { "Authorization": `Bearer ${storedToken}` } }).catch(() => { });
    if (processedImageUrl?.startsWith('blob:')) URL.revokeObjectURL(processedImageUrl);
    resetAllState();
    clearJob();
    setUploadMessage(`✅ ${t("detection.sessionReset")}`);
  };

  const handleYoutubeSubmit = async () => {
    if (!youtubeUrl.trim()) { setUploadMessage(`⚠️ ${t("detection.enterYoutubeUrl")}`); return; }
    setUploadMessage(`📥 ${t("detection.fetchingYoutube")}`); setIsProcessing(true);
    setShowYoutubeModal(false); setYoutubeUrl("");
    const storedToken = localStorage.getItem("token");
    try {
      const res = await axios.post(`${API_URL}/process_youtube`, { youtube_url: youtubeUrl }, { headers: { "Authorization": `Bearer ${storedToken}` } });
      setFileType("video");
      videoIdRef.current = res.data.video_id; setVideoId(res.data.video_id);
      uniqueIdsRef.current = new Set(); setUniquePeopleCount(0);
      socketRef.current.emit("start_processing", { filename: res.data.filename, video_id: res.data.video_id, user_id: res.data.user_id, mode: currentMode.payload.mode, dm_model: currentMode.payload.dm_model });
      startJob(res.data.video_id, res.data.filename);
      setUploadMessage(`✅ ${t("detection.youtubeLoaded")}`);
    } catch (err) {
      setUploadMessage(`❌ ${err?.response?.data?.error || t("detection.youtubeError")}`);
      setIsProcessing(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen flex flex-col px-3 py-3 sm:px-5 lg:px-6 lg:py-4 relative">
      {/* Subtle ambient glow */}
      <div className="fixed top-0 left-1/3 w-[600px] h-[600px] bg-emerald-600/[0.04] blur-[150px] rounded-full pointer-events-none z-0" />

      <div className="relative z-10 flex flex-col flex-1">
        {/* Header: Source Selector + Status */}
        <div className="flex flex-col gap-3 xl:flex-row xl:justify-between xl:items-center mb-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-3">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-[0.15em] font-['JetBrains_Mono',monospace]">{t("detection.dataSource")}</span>
            <div className="flex gap-2 overflow-x-auto pb-1 sm:pb-0">
              <button onClick={() => setDataSource("video")}
                className={`shrink-0 px-4 py-2 rounded-xl text-xs font-semibold transition-all duration-300 ${dataSource === "video"
                    ? "bg-emerald-500 text-black shadow-lg shadow-emerald-500/20"
                    : "bg-zinc-800/50 text-zinc-400 hover:bg-zinc-800 border border-zinc-700/50 hover:border-emerald-500/30"
                  }`}>
                {t("detection.video")}
              </button>
              <button onClick={() => setShowYoutubeModal(true)}
                className="shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-zinc-800/50 text-emerald-400 hover:bg-zinc-800 border border-zinc-700/50 hover:border-emerald-500/50 transition-all duration-300">
                <Youtube size={14} /> {t("detection.youtube")}
              </button>
              <button onClick={() => setShowLiveModal(true)}
                className="shrink-0 flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-zinc-800/50 text-emerald-400 hover:bg-zinc-800 border border-zinc-700/50 hover:border-emerald-500/50 transition-all duration-300">
                <Link2 size={14} /> {t("detection.liveStream")}
              </button>
            </div>
          </div>
          <div className="w-fit flex items-center gap-2.5 px-4 py-2 bg-zinc-800/50 border border-zinc-700/50 rounded-xl backdrop-blur-sm">
            <div className={`w-2.5 h-2.5 rounded-full transition-all ${isProcessing ? "bg-emerald-400 shadow-[0_0_8px_rgba(0,230,118,0.5)] animate-pulse" : "bg-zinc-700"}`} />
            <span className="text-[10px] font-bold font-['JetBrains_Mono',monospace] text-zinc-400 uppercase tracking-wider">{isProcessing ? t("common.processing").toUpperCase() : t("common.idle").toUpperCase()}</span>
          </div>
        </div>

        {uploadMessage && (
          <div className="mb-3 p-3 bg-emerald-500/5 border-l-2 border-emerald-500 rounded-r-xl flex items-center gap-2.5 backdrop-blur-sm">
            <div className="w-2 h-2 bg-emerald-500 rounded-full animate-pulse shadow-[0_0_6px_rgba(0,230,118,0.5)]" />
            <p className="text-[10px] font-bold font-['JetBrains_Mono',monospace] text-emerald-400 uppercase tracking-wider">{uploadMessage}</p>
          </div>
        )}

        {showYoutubeModal && <YoutubeModal youtubeUrl={youtubeUrl} setYoutubeUrl={setYoutubeUrl} onSubmit={handleYoutubeSubmit} onClose={() => { setShowYoutubeModal(false); setYoutubeUrl(""); }} />}
        {showLiveModal && <LiveStreamModal liveUrl={liveUrl} setLiveUrl={setLiveUrl} onSubmit={handleLiveStreamSubmit} onClose={() => setShowLiveModal(false)} />}

        <main className="flex flex-col xl:flex-row gap-4 flex-1">
          {/* VIDEO */}
          <div className="min-w-0 flex-grow flex flex-col space-y-2">
            <StatsBar frameInfo={frameInfo} isCrowdMode={isCrowdMode} dmCount={dmCount} mc={mc} />
            <VideoDisplay
              isProcessing={isProcessing} showReplayPlayer={showReplayPlayer} isUploading={isUploading}
              uploadProgress={uploadProgress} processedVideoUrl={processedVideoUrl}
              processedImageUrl={processedImageUrl} fileType={fileType} streamFrame={streamFrame}
              heatmapFrame={heatmapFrame} isCrowdMode={isCrowdMode} heatmapOpacity={heatmapOpacity}
              dmCount={dmCount} imageRef={imageRef} canvasRef={canvasRef} currentMode={currentMode} currentModeLabel={currentModeLabel}
              mc={mc} dataSource={dataSource} results={results}
              onVideoClick={handleVideoClick}
              onFileClick={() => fileInputRef.current.click()}
            />
          </div>

          {/* SIDEBAR */}
          <div className="w-full xl:w-[360px] xl:max-h-[calc(100vh-112px)] xl:overflow-y-auto flex flex-col gap-3 pb-20 md:pb-0">
            <ModeSelector
              selectedMode={selectedMode} onModeChange={handleModeChange}
              isCrowdMode={isCrowdMode} heatmapOpacity={heatmapOpacity}
              onHeatmapOpacityChange={setHeatmapOpacity} accentColor={mc.accent}
              isProcessing={isProcessing}
            />
            <LiveStatsPanel
              frameInfo={frameInfo} fps={fps} latency={latency} avgInference={avgInference}
              isCrowdMode={isCrowdMode} dmCount={dmCount} uniquePeopleCount={uniquePeopleCount}
              totalDetections={totalDetections} results={results}
              currentMetadata={currentMetadata} selectedIds={selectedIds}
              densityHistory={densityHistory} countHistory={countHistory} densityCoeff={densityCoeff}
              mc={mc}
            />
            <ControlPanel
              fileType={fileType} isPlaying={isPlaying} showReplayPlayer={showReplayPlayer}
              processedVideoUrl={processedVideoUrl} results={results} videoId={videoId}
              processedImageUrl={processedImageUrl}
              onPlayPause={() => setIsPlaying(!isPlaying)}
              onReplayToggle={() => setShowReplayPlayer(!showReplayPlayer)}
              onFullScreen={() => navigate(`/watch/${videoId}`)}
              onImageFullScreen={() => navigate(`/watch-image/${videoId}`)}
              onReset={handleRemoveVideo}
            />
          </div>
        </main>

        <input type="file" ref={fileInputRef} onChange={handleVideoUpload}
          accept={dataSource === "video" ? "video/*" : dataSource === "image" ? "image/*" : "image/*,video/*"}
          className="hidden" />
      </div>
    </div>
  );
}
