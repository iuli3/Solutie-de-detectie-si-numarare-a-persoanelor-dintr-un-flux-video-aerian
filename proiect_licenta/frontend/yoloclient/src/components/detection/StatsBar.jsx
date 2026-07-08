import { useLanguage } from "../../contexts/LanguageContext";

export default function StatsBar({ frameInfo, isCrowdMode, dmCount, mc }) {
  const { t } = useLanguage();
  if (!frameInfo) return null;
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:justify-between lg:items-center bg-zinc-900/50 border border-zinc-800/80 p-4 rounded-xl backdrop-blur-sm">
      <div className="grid grid-cols-2 gap-4 sm:flex sm:items-center sm:gap-6">
        <div className="flex flex-col">
          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider font-['JetBrains_Mono',monospace] mb-1">{t("detectionUi.currentFrame")}</span>
          <div className="flex items-baseline gap-1.5">
            <span className="text-2xl font-bold text-white font-['Space_Grotesk',sans-serif]">{frameInfo.frameNumber}</span>
            <span className="text-xs text-zinc-500 font-medium">/ {frameInfo.totalFrames}</span>
          </div>
        </div>
        <div className="hidden sm:block h-10 w-px bg-zinc-700/50" />
        <div className="flex flex-col">
          <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider font-['JetBrains_Mono',monospace] mb-1">{t("detectionUi.detectedPeople")}</span>
          <span className="text-2xl font-bold font-['Space_Grotesk',sans-serif]" style={{ color: mc.accent }}>{frameInfo.peopleCount}</span>
        </div>
        {isCrowdMode && dmCount !== null && (
          <>
            <div className="hidden sm:block h-10 w-px bg-zinc-700/50" />
            <div className="flex flex-col">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider font-['JetBrains_Mono',monospace] mb-1">{t("detectionUi.estimatedDmCount")}</span>
              <span className="text-2xl font-bold font-['Space_Grotesk',sans-serif]" style={{ color: mc.accent }}>{dmCount}</span>
            </div>
          </>
        )}
      </div>
      <div className="flex flex-col items-start lg:items-end gap-2">
        <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider font-['JetBrains_Mono',monospace]">{t("detectionUi.progress")}</span>
        <div className="flex items-center gap-3">
          <div className="w-36 sm:w-44 h-2 bg-zinc-800 rounded-full overflow-hidden">
            <div className="h-full transition-all duration-300 rounded-full"
              style={{ width: `${frameInfo.progress}%`, backgroundColor: mc.accent, boxShadow: `0 0 8px ${mc.accent}40` }} />
          </div>
          <span className="text-xs font-bold text-zinc-300 w-10 font-['JetBrains_Mono',monospace]">{frameInfo.progress}%</span>
        </div>
      </div>
    </div>
  );
}
