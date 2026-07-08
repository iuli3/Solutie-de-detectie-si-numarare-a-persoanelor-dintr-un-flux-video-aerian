import { Youtube, Link2 } from "lucide-react";
import { useLanguage } from "../../contexts/LanguageContext";

export function YoutubeModal({ youtubeUrl, setYoutubeUrl, onSubmit, onClose }) {
  const { t } = useLanguage();
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-96 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <Youtube className="text-emerald-400" size={24} />
          <h2 className="text-lg font-semibold text-white">YouTube</h2>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400 block mb-2">YouTube URL (link sau video ID)</label>
            <input type="text" placeholder="https://www.youtube.com/watch?v=..."
              value={youtubeUrl} onChange={(e) => setYoutubeUrl(e.target.value)}
              onKeyPress={(e) => e.key === "Enter" && onSubmit()}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white placeholder:text-zinc-500 text-sm focus:outline-none focus:border-cyan-400"
              autoFocus />
          </div>
          <div className="flex gap-3">
            <button onClick={onSubmit} disabled={!youtubeUrl.trim()}
              className="flex-1 bg-cyan-600 hover:bg-cyan-500 disabled:bg-zinc-700 text-white py-2 rounded-lg font-medium text-sm transition-all">
              {t("common.process")}
            </button>
            <button onClick={onClose}
              className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 py-2 rounded-lg font-medium text-sm transition-all">
              {t("common.cancel")}
            </button>
          </div>
          <p className="text-[11px] text-zinc-500 pt-2 border-t border-zinc-800">
            💡 Poți folosi link complet sau doar ID-ul video. Sistemul descarcă ~60 sec din streamul YouTube.
          </p>
        </div>
      </div>
    </div>
  );
}

export function LiveStreamModal({ liveUrl, setLiveUrl, onSubmit, onClose }) {
  const { t } = useLanguage();
  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-50">
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 w-96 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <Link2 className="text-cyan-400" size={24} />
          <h2 className="text-lg font-semibold text-white">{t("detection.liveStream")}</h2>
        </div>
        <div className="space-y-4">
          <div>
            <label className="text-xs text-zinc-400 block mb-2">URL Stream (RTSP, HLS .m3u8)</label>
            <input type="text" placeholder="https://server.com/live/playlist.m3u8"
              value={liveUrl} onChange={(e) => setLiveUrl(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && onSubmit()}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:outline-none focus:border-cyan-400"
              autoFocus />
          </div>
          <div className="flex gap-3">
            <button onClick={onSubmit}
              className="flex-1 bg-cyan-600 hover:bg-cyan-500 text-white py-2 rounded-lg font-medium text-sm transition-all">
              Start Feed
            </button>
            <button onClick={onClose}
              className="flex-1 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 py-2 rounded-lg font-medium text-sm">
              {t("common.cancel")}
            </button>
          </div>
          <p className="text-[10px] text-zinc-500 italic">
            *Notă: Stream-ul live nu va fi salvat în baza de date.
          </p>
        </div>
      </div>
    </div>
  );
}
