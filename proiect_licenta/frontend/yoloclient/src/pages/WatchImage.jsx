import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Download, Share2, CheckCircle2, Shield, Info, Image as ImageIcon } from "lucide-react";
import { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL;
import { useLanguage } from "../contexts/LanguageContext";

export default function WatchImage() {
  const { videoId } = useParams();
  const navigate = useNavigate();
  const { t } = useLanguage();
  const [copied, setCopied] = useState(false);
  const [hasError, setHasError] = useState(false);

  const imageUrl = `${API_URL}/api/video/watch/${videoId}`;
  const shareUrl = window.location.href;

  const copyShareLink = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen text-gray-100 font-sans selection:bg-emerald-500/30">
      <div
        className="fixed inset-0 z-0 opacity-[0.03] pointer-events-none"
        style={{ backgroundImage: "radial-gradient(#10b981 1px, transparent 1px)", backgroundSize: "32px 32px" }}
      />

      <div className="relative z-10 max-w-5xl mx-auto p-6 pt-12">
        <div className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <button
            onClick={() => navigate("/dashboard")}
            className="flex items-center w-fit gap-2 px-4 py-2 bg-zinc-900 hover:bg-zinc-800 border border-emerald-500/30 text-gray-400 hover:text-white rounded-xl transition-all text-xs font-bold uppercase tracking-widest"
          >
            <ArrowLeft className="w-4 h-4" />
            {t("common.returnToDashboard")}
          </button>

          <div className="flex items-center gap-3">
            <button
              onClick={copyShareLink}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-900 border border-zinc-800 text-zinc-300 rounded-xl hover:border-emerald-500/50 transition-all text-xs font-bold"
            >
              {copied ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-500" />
                  <span className="text-emerald-400 font-mono">{t("common.linkCopied")}</span>
                </>
              ) : (
                <>
                  <Share2 className="w-4 h-4 text-zinc-500" />
                  {t("common.shareAnalysis")}
                </>
              )}
            </button>

            <a
              href={imageUrl}
              download={`neural_analysis_image_${videoId}.jpg`}
              className="flex items-center gap-2 px-6 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl transition-all text-xs font-bold shadow-[0_0_25px_rgba(16,185,129,0.2)] active:scale-95"
            >
              <Download className="w-4 h-4" />
              {t("common.downloadResult")}
            </a>
          </div>
        </div>

        <div className="relative group rounded-2xl overflow-hidden border border-zinc-800 bg-black shadow-[0_0_60px_rgba(0,0,0,0.7)]">
          <div className="absolute top-0 left-0 right-0 p-4 flex justify-between items-start z-10 pointer-events-none opacity-60 group-hover:opacity-100 transition-opacity">
            <div className="bg-black/60 backdrop-blur-md px-3 py-1.5 rounded border border-zinc-800/50 flex items-center gap-2">
              <div className="w-1.5 h-1.5 bg-emerald-500 rounded-full animate-pulse" />
              <span className="text-[10px] font-mono text-emerald-500 font-bold uppercase tracking-tighter">{t("watch.secureImageView")}</span>
            </div>
            <div className="text-[10px] font-mono text-zinc-500 bg-black/40 px-2 py-1">REF_ID: {videoId}</div>
          </div>

          <div className="aspect-video relative bg-zinc-950 flex items-center justify-center">
            {!hasError ? (
              <img
                src={imageUrl}
                alt={`processed-${videoId}`}
                className="w-full h-full object-contain shadow-inner"
                onError={() => setHasError(true)}
              />
            ) : (
              <div className="flex flex-col items-center gap-5 p-12 text-center animate-in fade-in duration-700">
                <div className="w-20 h-20 rounded-full bg-red-500/10 flex items-center justify-center border border-red-500/20 shadow-[0_0_30px_rgba(239,68,68,0.1)]">
                  <span className="text-red-500 text-3xl">!</span>
                </div>
                <div className="space-y-2">
                  <h3 className="text-white font-black uppercase tracking-widest text-base font-mono text-red-500">{t("watch.imageErrorTitle")}</h3>
                  <p className="text-zinc-500 text-xs max-w-sm leading-relaxed">
                    {t("watch.imageErrorBody")}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="mt-8 grid grid-cols-1 md:grid-cols-3 gap-5">
          <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/20 backdrop-blur-sm group hover:border-emerald-500/30 transition-all">
            <div className="flex items-center gap-3 mb-3 text-zinc-500 group-hover:text-emerald-500 transition-colors">
              <Shield size={16} />
              <span className="text-[10px] font-black uppercase tracking-[0.2em]">{t("watch.auth")}</span>
            </div>
            <p className="text-xs text-zinc-300 font-mono">{t("watch.imageProtected")}</p>
          </div>

          <div className="p-5 rounded-2xl border border-zinc-800 bg-zinc-900/20 backdrop-blur-sm group hover:border-emerald-500/30 transition-all">
            <div className="flex items-center gap-3 mb-3 text-zinc-500 group-hover:text-emerald-500 transition-colors">
              <ImageIcon size={16} />
              <span className="text-[10px] font-black uppercase tracking-[0.2em]">{t("watch.mediaType")}</span>
            </div>
            <p className="text-xs text-zinc-300 font-mono">{t("watch.processedImageResult")}</p>
          </div>

          <div className="p-5 rounded-2xl border border-emerald-500/10 bg-emerald-500/5 group hover:border-emerald-500/30 transition-all">
            <div className="flex items-center gap-3 mb-3 text-emerald-500/70">
              <Info size={16} />
              <span className="text-[10px] font-black uppercase tracking-[0.2em]">{t("watch.statusReport")}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 bg-emerald-500 rounded-full" />
              <p className="text-xs text-emerald-400 font-mono font-bold uppercase">{t("watch.imageVerified")}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
