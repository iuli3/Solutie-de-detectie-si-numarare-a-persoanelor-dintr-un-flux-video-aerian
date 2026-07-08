import { Activity, TrendingUp, Loader2 } from "lucide-react";
import DensityChart from "./DensityChart";
import { CHART_LEN } from "./constants";
import { useLanguage } from "../../contexts/LanguageContext";

export default function LiveStatsPanel({
  frameInfo, fps, latency, avgInference,
  isCrowdMode, dmCount, uniquePeopleCount, totalDetections, results,
  currentMetadata, selectedIds,
  densityHistory, countHistory, densityCoeff,
  mc
}) {
  const { t } = useLanguage();
  return (
    <>
      {/* GRAFIC DENSITATE */}
      {frameInfo && (
        <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-4 backdrop-blur-sm">
          <p className="text-[10px] font-bold text-zinc-400 mb-3 uppercase tracking-[0.15em] flex items-center gap-2 font-['JetBrains_Mono',monospace]">
            <TrendingUp size={13} className="text-zinc-500" /> {t("detectionUi.densityOverTime")}
          </p>
          <div className="h-16 w-full mb-1.5">
            <DensityChart data={isCrowdMode ? countHistory : densityHistory} color={mc.accent} />
          </div>
          <div className="flex justify-between text-[9px] font-bold font-['JetBrains_Mono',monospace] text-zinc-600">
            <span>{t("detectionUi.framesAgo", { count: CHART_LEN })}</span>
            <span>{t("detectionUi.now")}</span>
          </div>
          <div className="mt-2 flex justify-between items-center">
            <span className="text-[10px] text-zinc-500 font-medium">{isCrowdMode ? t("detectionUi.peoplePerFrame") : t("detectionUi.bboxDensity")}</span>
            <span className="text-sm font-bold font-['Space_Grotesk',sans-serif]" style={{ color: mc.accent }}>
              {isCrowdMode ? (countHistory[countHistory.length - 1] || 0) : `${densityCoeff.toFixed(1)}%`}
            </span>
          </div>
        </div>
      )}

      {/* STATISTICI LIVE */}
      <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-4 backdrop-blur-sm">
        <h2 className="text-[10px] font-bold mb-3 text-zinc-400 flex items-center gap-2 uppercase tracking-[0.15em] font-['JetBrains_Mono',monospace]">
          <Activity size={13} className="text-zinc-500" /> {t("detectionUi.liveStats")}
        </h2>

        {frameInfo ? (
          <div className="space-y-2.5">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-zinc-950/50 p-3 rounded-xl border border-zinc-800/60">
                <span className="text-[9px] font-bold text-zinc-500 block mb-1 uppercase tracking-wider font-['JetBrains_Mono',monospace]">FPS</span>
                <span className={`text-lg font-bold font-['Space_Grotesk',sans-serif] ${fps < 15 ? 'text-red-400' : 'text-cyan-400'}`}>{fps}</span>
              </div>
              <div className="bg-zinc-950/50 p-3 rounded-xl border border-zinc-800/60">
                <span className="text-[9px] font-bold text-zinc-500 block mb-1 uppercase tracking-wider font-['JetBrains_Mono',monospace]">{t("detectionUi.latency")}</span>
                <span className="text-lg font-bold text-zinc-300 font-['Space_Grotesk',sans-serif]">{latency}<span className="text-xs text-zinc-500 ml-0.5">ms</span></span>
              </div>
            </div>

            <div className="bg-zinc-950/50 p-3 rounded-xl border border-zinc-800/60">
              <span className="text-[9px] font-bold text-zinc-500 block mb-1 uppercase tracking-wider font-['JetBrains_Mono',monospace]">{t("detectionUi.inferenceTime")}</span>
              <div className="flex items-baseline gap-1.5">
                <span className="text-lg font-bold text-white font-['Space_Grotesk',sans-serif]">{(avgInference * 1000).toFixed(1)}</span>
                <span className="text-[10px] text-zinc-500 font-medium">ms/frame</span>
              </div>
            </div>

            <div className="h-px bg-zinc-800/50 my-1" />

            {!isCrowdMode && (
              <div className="bg-zinc-950/30 border border-zinc-800/50 rounded-xl p-3">
                <p className="text-[10px] text-zinc-500 mb-2 font-medium">{t("detectionUi.detectedObjects")}</p>
                <div className="flex flex-wrap gap-1.5 max-h-[78px] overflow-hidden">
                  {currentMetadata.slice(0, 16).map(p => (
                    <span key={p.id} className={`px-2 py-0.5 rounded-lg text-[10px] font-semibold transition-all ${selectedIds.includes(p.id) ? 'bg-cyan-400 text-white shadow-sm shadow-cyan-400/20' : 'bg-zinc-800/80 text-zinc-400'}`}>
                      #{p.id}
                    </span>
                  ))}
                  {currentMetadata.length > 16 && <span className="text-[10px] text-zinc-600 font-medium">+{currentMetadata.length - 16}</span>}
                </div>
              </div>
            )}

            <div className="h-px bg-zinc-800/50 my-1" />

            <div className="grid gap-2">
              <div className="flex justify-between items-center p-3 rounded-xl border transition-all"
                style={{ backgroundColor: mc.accentAlpha, borderColor: mc.border }}>
                <span className="text-[10px] font-bold" style={{ color: mc.accent }}>
                    {isCrowdMode ? t("detectionUi.estimatedDmCount") : t("detectionUi.maxPeopleInFrame")}
                  </span>
                  <span className="text-lg font-bold font-['Space_Grotesk',sans-serif]" style={{ color: mc.accent }}>
                    {isCrowdMode ? (dmCount ?? "—") : (results?.max_people_in_frame ?? uniquePeopleCount ?? "—")}
                  </span>
              </div>
              {!isCrowdMode && results && (
                <div className="flex justify-between items-center bg-zinc-800/30 p-3 rounded-xl">
                  <span className="text-[10px] text-zinc-500 font-medium">{t("detectionUi.totalDetections")}</span>
                  <span className="text-sm font-bold text-zinc-300 font-['Space_Grotesk',sans-serif]">{totalDetections.toLocaleString()}</span>
                </div>
              )}
            </div>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center py-12 opacity-30">
            <Loader2 size={18} className="animate-spin mb-2 text-zinc-600" />
            <p className="text-[10px] text-zinc-600 font-medium">{t("detectionUi.waitingData")}</p>
          </div>
        )}
      </div>
    </>
  );
}
