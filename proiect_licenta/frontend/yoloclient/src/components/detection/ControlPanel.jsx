import { Flame, Activity, RotateCcw, X, ExternalLink, Play, Pause } from "lucide-react";
import { useLanguage } from "../../contexts/LanguageContext";

export default function ControlPanel({
  fileType, isPlaying, showReplayPlayer, processedVideoUrl,
  results, videoId, processedImageUrl,
  onPlayPause, onReplayToggle, onFullScreen, onImageFullScreen, onReset
}) {
  const { t } = useLanguage();
  return (
    <div className="bg-zinc-900/50 border border-zinc-800/80 p-4 rounded-xl backdrop-blur-sm">
      <p className="text-[10px] font-bold text-zinc-400 mb-3 uppercase tracking-[0.15em] font-['JetBrains_Mono',monospace]">{t("detectionUi.control")}</p>
      <div className="flex flex-col gap-2.5">
        {fileType === 'video' && (
          <>
            <div className="grid grid-cols-2 gap-2">
              <button onClick={onPlayPause} disabled={showReplayPlayer}
                className={`flex items-center justify-center gap-1.5 py-2.5 rounded-xl transition-all duration-300 text-xs font-semibold ${
                  showReplayPlayer ? 'bg-zinc-900 text-zinc-600 cursor-not-allowed border border-zinc-800'
                  : isPlaying ? 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
                  : 'bg-cyan-600 text-white hover:bg-cyan-500 shadow-lg shadow-cyan-500/20'
                }`}>
                {isPlaying ? <Pause size={14} fill="white" /> : <Play size={14} fill="white" />}
                {isPlaying ? t("detectionUi.pause") : t("detectionUi.resume")}
              </button>
              {processedVideoUrl && results && (
                <button onClick={onReplayToggle}
                  className={`flex items-center justify-center gap-1.5 py-2.5 rounded-xl transition-all duration-300 text-xs font-semibold ${
                    showReplayPlayer
                      ? 'bg-cyan-600 text-white hover:bg-cyan-500 shadow-lg shadow-cyan-500/20'
                      : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20'
                  }`}>
                  <Flame size={14} />
                  {showReplayPlayer ? "Live" : "Replay"}
                </button>
              )}
            </div>
            {videoId && processedVideoUrl && results && (
              <button onClick={onFullScreen}
                className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl transition-all duration-300 text-xs font-semibold bg-cyan-600/80 text-white hover:bg-cyan-500 border border-cyan-700/50 hover:border-cyan-500/50">
                <ExternalLink size={14} /> {t("common.fullScreen")}
              </button>
            )}
          </>
        )}
        {fileType === 'image' && videoId && processedImageUrl && (
          <button onClick={onImageFullScreen}
            className="w-full flex items-center justify-center gap-1.5 py-2.5 rounded-xl transition-all duration-300 text-xs font-semibold bg-cyan-600 text-white hover:bg-cyan-500 shadow-lg shadow-cyan-500/20">
            <ExternalLink size={14} /> {t("detectionUi.openFullScreen")}
          </button>
        )}
        <button onClick={onReset}
          className="w-full py-2.5 bg-zinc-800/40 rounded-xl hover:bg-red-900/30 text-zinc-400 hover:text-red-400 transition-all duration-300 flex items-center justify-center gap-1.5 border border-zinc-700/50 hover:border-red-800/50">
          <X size={16} /><span className="text-xs font-semibold">{t("detectionUi.resetSession")}</span>
        </button>
      </div>
    </div>
  );
}
