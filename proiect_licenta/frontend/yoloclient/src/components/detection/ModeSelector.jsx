import { useEffect, useRef, useState } from "react";
import { Check, ChevronDown, Cpu } from "lucide-react";
import { MODES } from "./constants";
import { useLanguage } from "../../contexts/LanguageContext";

export default function ModeSelector({ selectedMode, onModeChange, isCrowdMode, heatmapOpacity, onHeatmapOpacityChange, accentColor, isProcessing }) {
  const { t } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);
  const activeMode = MODES.find(mode => mode.id === selectedMode) || MODES[0];

  useEffect(() => {
    if (!isOpen) return;

    const handlePointerDown = (event) => {
      if (!dropdownRef.current?.contains(event.target)) setIsOpen(false);
    };

    const handleKeyDown = (event) => {
      if (event.key === "Escape") setIsOpen(false);
    };

    document.addEventListener("pointerdown", handlePointerDown);
    document.addEventListener("keydown", handleKeyDown);

    return () => {
      document.removeEventListener("pointerdown", handlePointerDown);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  useEffect(() => {
    if (isProcessing) setIsOpen(false);
  }, [isProcessing]);

  const handleModeSelect = (modeId) => {
    onModeChange(modeId);
    setIsOpen(false);
  };

  return (
    <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-3 backdrop-blur-sm shadow-[0_12px_40px_rgba(0,0,0,0.18)]">
      <div className="mb-2.5 flex items-center gap-2">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-zinc-800 bg-zinc-950/70 text-zinc-400">
          <Cpu size={13} />
        </div>
        <div className="min-w-0 flex-1">
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] font-['JetBrains_Mono',monospace] text-zinc-400">
            {t("detectionUi.processingMode")}
          </p>
          <p className="mt-0.5 truncate text-[10px] text-zinc-600">
            {t(activeMode.sublabelKey || activeMode.sublabel)}
          </p>
        </div>
        {isProcessing && (
          <span className="rounded-full border border-cyan-500/20 bg-cyan-500/10 px-2 py-0.5 text-[9px] font-bold text-cyan-400 animate-pulse">
            {t("detection.modeActive")}
          </span>
        )}
      </div>

      <div ref={dropdownRef}>
        <button
          type="button"
          onClick={() => !isProcessing && setIsOpen(prev => !prev)}
          disabled={isProcessing}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          className={[
            "flex min-h-11 w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left outline-none transition-all",
            isProcessing
              ? "cursor-not-allowed border-zinc-800 bg-zinc-950/30 text-zinc-500"
              : "border-zinc-700/70 bg-zinc-950/60 text-zinc-100 hover:border-zinc-500 focus:border-zinc-500 focus:ring-2 focus:ring-white/10",
          ].join(" ")}
        >
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full ring-4 ring-white/[0.04]"
            style={{ backgroundColor: accentColor, boxShadow: `0 0 10px ${accentColor}70` }}
          />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-semibold text-zinc-100">
              {t(activeMode.labelKey || activeMode.label)}
            </span>
          </span>
          <ChevronDown
            size={15}
            className={[
              "shrink-0 text-zinc-500 transition-transform",
              isOpen ? "rotate-180 text-zinc-300" : "",
            ].join(" ")}
          />
        </button>

        {isOpen && (
          <div className="mt-2 rounded-xl border border-zinc-800/80 bg-zinc-950/60 p-1" role="listbox" aria-label={t("detectionUi.processingMode")}>
            {MODES.map(mode => {
              const isSelected = mode.id === selectedMode;
              const label = t(mode.labelKey || mode.label);
              const sublabel = t(mode.sublabelKey || mode.sublabel);

              return (
                <button
                  key={mode.id}
                  type="button"
                  role="option"
                  aria-selected={isSelected}
                  onClick={() => handleModeSelect(mode.id)}
                  className={[
                    "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                    isSelected
                      ? "bg-white/[0.07] text-zinc-50"
                      : "text-zinc-400 hover:bg-white/[0.045] hover:text-zinc-100",
                  ].join(" ")}
                >
                  <span
                    className="h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: isSelected ? accentColor : "#52525b" }}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-xs font-semibold">{label}</span>
                    <span className="mt-0.5 block truncate text-[10px] text-zinc-500">{sublabel}</span>
                  </span>
                  {isSelected && <Check size={13} className="shrink-0" style={{ color: accentColor }} />}
                </button>
              );
            })}
          </div>
        )}
      </div>

      {isCrowdMode && (
        <div className="mt-3 border-t border-zinc-800/50 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-[11px] font-medium text-zinc-400">{t("detectionUi.heatmapOpacity")}</span>
            <span className="text-[11px] font-bold font-['JetBrains_Mono',monospace] text-zinc-300">{heatmapOpacity}%</span>
          </div>
          <input
            type="range"
            min="20"
            max="95"
            step="5"
            value={heatmapOpacity}
            onChange={(e) => onHeatmapOpacityChange(Number(e.target.value))}
            className="w-full"
            style={{ accentColor }}
          />
        </div>
      )}
    </div>
  );
}
