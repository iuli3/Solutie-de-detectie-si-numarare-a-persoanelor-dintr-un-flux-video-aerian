import { Activity, Loader2 } from "lucide-react";
import { useState, useRef, useEffect } from "react";
import { useLanguage } from "../../contexts/LanguageContext";

export default function VideoDisplay({
  isProcessing, showReplayPlayer, isUploading, uploadProgress,
  processedVideoUrl, processedImageUrl, fileType, streamFrame,
  heatmapFrame, isCrowdMode, heatmapOpacity, dmCount,
  imageRef, canvasRef, currentMode, currentModeLabel, mc, dataSource,
  results, onVideoClick, onFileClick
}) {
  const { t } = useLanguage();
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef(null);

  const handleMouseDown = (e) => {
    if (zoom > 1 && (streamFrame || processedImageUrl)) {
      setIsDragging(true);
      setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
      e.preventDefault();
    }
  };

  useEffect(() => {
    if (!isDragging) return;

    const handleMouseMove = (e) => {
      setPan({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
    };
    const handleMouseUp = () => setIsDragging(false);

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isDragging, dragStart, pan]);

  useEffect(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, [processedImageUrl, processedVideoUrl]);

  return (
    <div
      ref={containerRef}
      onClick={!isProcessing && !showReplayPlayer && !isUploading && zoom === 1 ? onFileClick : undefined}
      onMouseDown={handleMouseDown}
      className={`relative h-[360px] sm:h-[480px] xl:h-[calc(100vh-212px)] xl:min-h-[520px] bg-black/80 rounded-2xl border border-zinc-800/80 overflow-hidden backdrop-blur-sm transition-all duration-300 ${
        !isProcessing && !isUploading && zoom === 1 ? 'cursor-pointer group hover:border-cyan-400/20' : zoom > 1 ? 'cursor-move' : ''
      }`}
    >
      {/* Corner brackets */}
      <div className="absolute top-3 left-3 w-5 h-5 border-l-2 border-t-2 border-cyan-400/20 rounded-tl-sm z-30 pointer-events-none" />
      <div className="absolute top-3 right-3 w-5 h-5 border-r-2 border-t-2 border-cyan-400/20 rounded-tr-sm z-30 pointer-events-none" />
      <div className="absolute bottom-3 left-3 w-5 h-5 border-l-2 border-b-2 border-cyan-400/20 rounded-bl-sm z-30 pointer-events-none" />
      <div className="absolute bottom-3 right-3 w-5 h-5 border-r-2 border-b-2 border-cyan-400/20 rounded-br-sm z-30 pointer-events-none" />

      {isProcessing && (
        <div className="absolute top-3 right-10 z-20 flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-[10px] font-bold uppercase tracking-wider backdrop-blur-sm"
          style={{ backgroundColor: mc.accentAlpha, border: `1px solid ${mc.border}`, color: mc.accent }}>
          <div className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ backgroundColor: mc.accent }} />
          <span>{currentModeLabel || currentMode.label}</span>
        </div>
      )}

      {showReplayPlayer && processedVideoUrl ? (
        <video src={processedVideoUrl} controls autoPlay className="w-full h-full object-contain" />

      ) : processedImageUrl && fileType === 'image' ? (
        <div className="w-full h-full relative">
          <img src={processedImageUrl} alt="Processed" className="w-full h-full object-contain select-none" />
          {results && (
            <div className="absolute bottom-4 left-4 bg-black/70 backdrop-blur-md px-5 py-3 rounded-xl border border-cyan-400/30 shadow-lg shadow-cyan-400/5">
              <p className="text-cyan-400 text-sm font-semibold flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                ✓ {results.unique_people} {results.unique_people === 1 ? t("detectionUi.detectedPeople") : t("detectionUi.detectedPeople")}
              </p>
            </div>
          )}
        </div>

      ) : streamFrame ? (
        <div className="w-full h-full relative" onClick={(e) => { e.stopPropagation(); onVideoClick(e); }}>
          <img ref={imageRef} src={streamFrame} alt="Frame" className="w-full h-full object-contain select-none" />
          {isCrowdMode && heatmapFrame && (
            <img src={heatmapFrame} alt="Heatmap"
              className="absolute inset-0 w-full h-full object-contain pointer-events-none mix-blend-overlay"
              style={{ opacity: heatmapOpacity / 100 }} />
          )}
          {isCrowdMode && dmCount !== null && (
            <div className="absolute bottom-4 left-4 bg-black/75 backdrop-blur-md rounded-2xl px-6 py-4 border shadow-xl"
              style={{ borderColor: mc.border }}>
              <p className="text-[10px] font-bold font-['JetBrains_Mono',monospace] uppercase tracking-wider mb-1" style={{ color: mc.accent }}>
                {currentModeLabel || currentMode.label} — {t("detectionUi.estimate")}
              </p>
              <p className="text-4xl font-bold text-white leading-none font-['Space_Grotesk',sans-serif]">{dmCount}</p>
              <p className="text-xs text-zinc-400 mt-1">{t("detectionUi.peopleInScene")}</p>
            </div>
          )}
          <canvas ref={canvasRef} className="absolute top-0 left-0 w-full h-full pointer-events-none" />
        </div>

      ) : isUploading ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-zinc-950">
          <div className="relative">
            <Loader2 className="w-14 h-14 text-cyan-400 animate-spin" />
            <div className="absolute inset-0 w-14 h-14 rounded-full bg-cyan-400/10 blur-xl" />
          </div>
          <p className="mt-5 text-sm text-cyan-400 font-semibold">{t("detectionUi.uploadingFile")}</p>
          <div className="mt-3 w-48 h-1.5 bg-zinc-800 rounded-full overflow-hidden">
            <div className="h-full bg-cyan-400 transition-all duration-300 rounded-full shadow-[0_0_8px_rgba(0,230,118,0.4)]"
              style={{ width: `${uploadProgress}%` }} />
          </div>
          <p className="mt-2 text-xs text-zinc-500 font-['JetBrains_Mono',monospace]">{uploadProgress}%</p>
        </div>

      ) : (
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <div className="relative">
            <div className="w-20 h-20 bg-zinc-900/80 rounded-2xl flex items-center justify-center border border-zinc-700/50 group-hover:border-cyan-400/30 transition-all duration-500">
              <Activity className="w-8 h-8 text-zinc-600 group-hover:text-cyan-400 transition-colors duration-500" />
            </div>
            <div className="absolute -inset-4 rounded-3xl bg-cyan-400/0 group-hover:bg-cyan-400/5 transition-all duration-500 -z-10" />
          </div>
          <p className="mt-5 text-sm text-zinc-400 font-medium">
            {dataSource === "video" && t("detection.clickUploadVideo")}
            {dataSource === "image" && t("detection.clickUploadImage")}
            {dataSource === "webcam" && t("detection.webcamSoon")}
          </p>
          <p className="mt-1.5 text-xs text-zinc-600">
            {dataSource === "video" && t("detection.sourceVideoHint")}
            {dataSource === "image" && t("detection.sourceImageHint")}
            {dataSource === "webcam" && t("detection.sourceWebcamHint")}
          </p>
        </div>
      )}
    </div>
  );
}
