import React, { useState, useEffect } from "react";
import axios from "axios";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, User, Lock, Activity, Cpu, Scan, Target, ShieldCheck, Zap } from "lucide-react";
import { useLanguage } from "./contexts/LanguageContext";
import DetectionCanvas from "./components/DetectionCanvas";

export default function Login({ onLogin }) {
  const { t, language, setLanguage } = useLanguage();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [focusField, setFocusField] = useState(null);

  const navigate = useNavigate();

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await axios.post(`${import.meta.env.VITE_API_URL}/auth/login`, {
        username,
        password
      });

      // Verificăm dacă structura datelor este cea așteptată pentru a evita crash-ul
      if (res.data && res.data.access_token) {
        const token = res.data.access_token;
        const user = res.data.user?.username || "Operator";

        onLogin(token, user);
        navigate("/dashboard");
      }
    } catch (err) {
      console.error("Login Error:", err);
      setError(err.response?.data?.error || "Invalid Credentials");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`flex min-h-screen w-full bg-transparent transition-opacity duration-1000 ${mounted ? "opacity-100" : "opacity-0"}`}>

      {/* --- PARTEA STÂNGA: BRANDING --- */}
      <div className="relative hidden w-0 flex-col items-center justify-center overflow-hidden border-r border-emerald-500/10 bg-transparent p-12 lg:flex lg:w-[60%]">

        {/* Fundal animat */}
        <div className="absolute inset-0 z-10 opacity-40">
          <DetectionCanvas />
        </div>

        {/* Glow de fundal */}
        <div className="absolute h-[500px] w-[500px] rounded-full bg-emerald-600/8 blur-[120px] z-0"></div>

        <div className="relative z-20 max-w-xl">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/5 px-4 py-1 text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400">
            <Scan size={12} />
            <span>AI Surveillance Neural Engine</span>
          </div>

          <h1 className="mb-4 text-7xl font-black tracking-tighter text-white">
            Over<span className="bg-gradient-to-r from-emerald-300 to-emerald-500 bg-clip-text text-transparent">Watch</span>
          </h1>

          <p className="mb-10 text-xl leading-relaxed text-white/40 font-light">
            Real-time AI-powered surveillance — detect, track and re-identify people across multiple camera feeds using deep learning.
          </p>

          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 p-4 backdrop-blur-md">
              <Target size={20} className="text-emerald-400" />
              <span className="text-sm font-medium text-gray-300">Multi-Camera</span>
            </div>
            <div className="flex items-center gap-3 rounded-xl border border-white/5 bg-white/5 p-4 backdrop-blur-md">
              <Cpu size={20} className="text-emerald-400" />
              <span className="text-sm font-medium text-gray-300">Deep Tracking</span>
            </div>
          </div>
        </div>

        <div className="absolute bottom-10 left-12 flex items-center gap-2 text-[10px] tracking-widest text-emerald-500/30 uppercase">
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(0,230,118,0.5)]"></div>
          <span>System Online: Node_042</span>
        </div>
      </div>

      {/* --- PARTEA DREAPTĂ: FORMULAR --- */}
      <div className="flex w-full flex-col items-center justify-center bg-[#0d0d10] p-8 lg:w-[40%] text-gray-100">

        <div className="absolute top-8 right-8">
          <button
            onClick={() => setLanguage(language === "ro" ? "en" : "ro")}
            className="text-xs font-black tracking-widest text-zinc-500 hover:text-emerald-400 transition-colors"
          >
            {language.toUpperCase()}
          </button>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-10 text-center">
              <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 shadow-xl shadow-emerald-950/20 border border-emerald-500/20">
              <img src="/overwatch_icon_light.svg" alt="OW" className="w-10 h-10" />
            </div>
              <h2 className="text-3xl font-bold tracking-tight text-white">Autentificare</h2>
              <p className="mt-2 text-sm text-white/30">Introduceți credențialele pentru a accesa consola.</p>
          </div>

          {error && (
            <div className="mb-6 rounded-lg bg-red-900/30 p-4 text-xs font-bold text-red-300 border-l-4 border-red-500/60">
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="space-y-1.5">
              <label className="text-[10px] font-bold uppercase tracking-widest text-white/25 ml-1">Utilizator</label>
              <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'user' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                <User className={`ml-4 ${focusField === 'user' ? 'text-emerald-400' : 'text-zinc-600'}`} size={18} />
                <input
                  type="text"
                  className="w-full bg-transparent p-4 text-sm outline-none text-gray-100 placeholder-white/10"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onFocus={() => setFocusField("user")}
                  onBlur={() => setFocusField(null)}
                  placeholder="admin_overwatch"
                  required
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-[10px] font-bold uppercase tracking-widest text-white/25 ml-1">Parolă</label>
              <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'pass' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                <Lock className={`ml-4 ${focusField === 'pass' ? 'text-emerald-400' : 'text-zinc-600'}`} size={18} />
                <input
                  type={showPassword ? "text" : "password"}
                  className="w-full bg-transparent p-4 text-sm outline-none text-gray-100 placeholder-white/10"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusField("pass")}
                  onBlur={() => setFocusField(null)}
                  placeholder="••••••••"
                  required
                />
                <button type="button" onClick={() => setShowPassword(!showPassword)} className="mr-4 text-zinc-600 hover:text-emerald-400">
                  {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              className="group relative flex w-full items-center justify-center gap-3 overflow-hidden rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 py-4 text-sm font-bold text-black transition-all hover:from-emerald-400 hover:to-emerald-500 active:scale-95 disabled:opacity-50 shadow-lg shadow-emerald-500/20"
            >
              {loading ? (
                <div className="h-5 w-5 animate-spin rounded-full border-2 border-black/20 border-t-black"></div>
              ) : (
                <>
                  <span>ACCES SISTEM</span>
                  <Zap size={16} className="text-black/60 group-hover:animate-pulse" />
                </>
              )}
            </button>
          </form>

          <div className="mt-8 text-center text-xs text-white/25">
            Nu aveți cont? <Link to="/register" className="font-bold text-emerald-400 hover:underline">Solicitați acces</Link>
          </div>
        </div>
      </div>
    </div>
  );
}