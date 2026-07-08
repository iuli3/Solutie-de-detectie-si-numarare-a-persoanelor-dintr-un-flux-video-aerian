import React, { useState, useEffect } from "react";
import axios from "axios";
import { useNavigate, Link } from "react-router-dom";
import { Eye, EyeOff, User, Lock, Mail, CheckCircle2, XCircle, AlertCircle, UserPlus, Cpu, Scan, Target, ShieldCheck, Zap } from "lucide-react";
import { useLanguage } from "./contexts/LanguageContext";
import DetectionCanvas from "./components/DetectionCanvas";

export default function Register() {
  const navigate = useNavigate();
  const { t, language, setLanguage } = useLanguage();
  const [mounted, setMounted] = useState(false);
  const [focusField, setFocusField] = useState(null);
  const [success, setSuccess] = useState(false);

  const [formData, setFormData] = useState({
    firstName: "",
    lastName: "",
    email: "",
    password: ""
  });

  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const validatePassword = (pwd) => {
    const rules = [
      { key: "minLength", test: pwd.length >= 8, label: t("register.passwordRules.minLength") },
      { key: "upperCase", test: /[A-Z]/.test(pwd), label: t("register.passwordRules.upperCase") },
      { key: "number", test: /[0-9]/.test(pwd), label: t("register.passwordRules.number") },
      { key: "special", test: /[!@#$%^&*]/.test(pwd), label: t("register.passwordRules.special") },
    ];
    return {
      isValid: rules.every((r) => r.test),
      rules,
    };
  };

  const passValidation = validatePassword(formData.password);
  const handleInputChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (!passValidation.isValid) {
      setError(t("register.passwordRulesError") || "Parola nu respectă regulile de securitate.");
      return;
    }
    setLoading(true);

    try {
      await axios.post(`${import.meta.env.VITE_API_URL}/auth/register`, formData);
      setSuccess(true);
      setTimeout(() => navigate("/login"), 2000);
    } catch (err) {
      setError(err.response?.data?.error || t("register.registerFailed"));
    } finally {
      setLoading(false);
    }
  };

  const strengthScore = passValidation.rules.filter((r) => r.test).length;
  const strengthColors = ["#ef4444", "#f97316", "#eab308", "#00e676"];

  return (
    <div className={`flex min-h-screen w-full bg-transparent font-sans transition-opacity duration-1000 ${mounted ? "opacity-100" : "opacity-0"}`}>

      {/* --- PARTEA STÂNGA: BRANDING & ANIMATIE --- */}
      <div className="relative hidden w-0 flex-col items-center justify-center overflow-hidden border-r border-emerald-500/10 bg-transparent p-12 lg:flex lg:w-[60%]">

        <div className="absolute inset-0 z-10 opacity-40 mix-blend-lighten">
          <DetectionCanvas />
        </div>

        {/* Glow central */}
        <div className="absolute h-[600px] w-[600px] rounded-full bg-emerald-600/8 blur-[130px] z-0"></div>

        <div className="relative z-20 max-w-xl">
          <div className="mb-3 flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/5 px-4 py-1 text-xs font-bold text-emerald-400 shadow-[0_0_15px_rgba(0,230,118,0.08)]">
            <UserPlus size={14} />
            <span className="tracking-[0.2em] uppercase">Operator Enrollment Active</span>
          </div>

          <h1 className="mb-4 text-7xl font-extrabold tracking-tighter text-white">
            Over<span className="bg-gradient-to-r from-emerald-300 to-emerald-500 bg-clip-text text-transparent">Watch</span>
          </h1>

          <p className="mb-10 text-xl font-light leading-relaxed text-white/40">
            Real-time AI-powered surveillance — detect, track and re-identify people across multiple camera feeds using deep learning.
          </p>

          <div className="flex gap-4">
            <div className="flex items-center gap-2 rounded-lg bg-white/5 border border-white/[0.06] px-4 py-2 text-xs text-gray-300 backdrop-blur-sm">
              <ShieldCheck size={14} className="text-emerald-400" />
              <span>Secure Registration</span>
            </div>
            <div className="flex items-center gap-2 rounded-lg bg-white/5 border border-white/[0.06] px-4 py-2 text-xs text-gray-300 backdrop-blur-sm">
              <Target size={14} className="text-emerald-400" />
              <span>Multi-Feed Analysis</span>
            </div>
          </div>
        </div>

        <div className="absolute bottom-8 left-12 z-20 flex items-center gap-2 text-[10px] tracking-widest text-emerald-500/30">
          <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(0,230,118,0.5)]"></div>
          <span>ENROLLMENT_PROTOCOL: ENABLED</span>
        </div>
      </div>

      {/* --- PARTEA DREAPTĂ: FORMULAR (Dark Theme) --- */}
      <div className="flex w-full flex-col items-center justify-center bg-[#0d0d10] p-6 lg:w-[40%]">

        <div className="absolute top-6 right-6">
          <button
            onClick={() => setLanguage(language === "ro" ? "en" : "ro")}
            className="text-xs font-bold text-zinc-500 hover:text-emerald-400 transition-colors"
          >
            {language.toUpperCase()}
          </button>
        </div>

        <div className="w-full max-w-md">
          {/* Header Formular */}
          <div className="mb-8 text-center flex flex-col items-center">
            <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-emerald-500/10 shadow-xl shadow-emerald-950/20 border border-emerald-500/20">
              <img src="/overwatch_icon_light.svg" alt="OW" className="w-10 h-10" />
            </div>
            <h2 className="text-3xl font-bold tracking-tight text-white">{t("register.title")}</h2>
            <p className="mt-1 text-sm text-white/30">Creați un profil de operator OverWatch.</p>
          </div>

          {success ? (
            <div className="flex flex-col items-center gap-4 rounded-2xl bg-emerald-500/10 p-8 text-center border border-emerald-500/20 shadow-sm">
              <div className="rounded-full bg-emerald-500 p-3 text-black">
                <CheckCircle2 size={32} />
              </div>
              <div>
                <h3 className="text-lg font-bold text-white">Cont creat cu succes!</h3>
                <p className="text-sm text-emerald-400/70">Vă redirecționăm către autentificare...</p>
              </div>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="flex items-center gap-2 rounded-lg bg-red-900/30 p-3 text-xs font-bold text-red-300 border-l-4 border-red-500/60">
                  <AlertCircle size={14} />
                  <span>{error}</span>
                </div>
              )}

              {/* Grid pentru Nume/Prenume */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-white/25 ml-1">Prenume</label>
                  <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'firstName' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                    <input
                      type="text"
                      name="firstName"
                      className="w-full bg-transparent p-3 text-sm outline-none text-white placeholder-white/10"
                      value={formData.firstName}
                      onChange={handleInputChange}
                      onFocus={() => setFocusField("firstName")}
                      onBlur={() => setFocusField(null)}
                      placeholder="Ion"
                      required
                    />
                  </div>
                </div>
                <div className="space-y-1">
                  <label className="text-[10px] font-bold uppercase tracking-wider text-white/25 ml-1">Nume</label>
                  <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'lastName' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                    <input
                      type="text"
                      name="lastName"
                      className="w-full bg-transparent p-3 text-sm outline-none text-white placeholder-white/10"
                      value={formData.lastName}
                      onChange={handleInputChange}
                      onFocus={() => setFocusField("lastName")}
                      onBlur={() => setFocusField(null)}
                      placeholder="Popescu"
                      required
                    />
                  </div>
                </div>
              </div>

              {/* Email */}
              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-white/25 ml-1">Email</label>
                <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'email' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                  <Mail className={`ml-4 ${focusField === 'email' ? 'text-emerald-400' : 'text-zinc-600'}`} size={18} />
                  <input
                    type="email"
                    name="email"
                    className="w-full bg-transparent p-3 text-sm outline-none text-white placeholder-white/10"
                    value={formData.email}
                    onChange={handleInputChange}
                    onFocus={() => setFocusField("email")}
                    onBlur={() => setFocusField(null)}
                    placeholder="operator@overwatch.ai"
                    required
                  />
                </div>
              </div>

              {/* Parola */}
              <div className="space-y-1">
                <label className="text-[10px] font-bold uppercase tracking-wider text-white/25 ml-1">Parolă</label>
                <div className={`flex items-center rounded-xl border-2 transition-all ${focusField === 'password' ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-white/6 bg-white/[0.02]'}`}>
                  <Lock className={`ml-4 ${focusField === 'password' ? 'text-emerald-400' : 'text-zinc-600'}`} size={18} />
                  <input
                    type={showPassword ? "text" : "password"}
                    name="password"
                    className="w-full bg-transparent p-3 text-sm outline-none text-white placeholder-white/10"
                    value={formData.password}
                    onChange={handleInputChange}
                    onFocus={() => setFocusField("password")}
                    onBlur={() => { setFocusField(null); setPasswordTouched(true); }}
                    placeholder="••••••••"
                    required
                  />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} className="mr-4 text-zinc-600 hover:text-emerald-400">
                    {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                {/* Strength Indicator */}
                {formData.password && (
                  <div className="mt-2 flex gap-1">
                    {[0, 1, 2, 3].map((i) => (
                      <div
                        key={i}
                        className="h-1 flex-1 rounded-full transition-all duration-500"
                        style={{
                          backgroundColor: i < strengthScore ? strengthColors[strengthScore - 1] : "rgba(255,255,255,0.05)"
                        }}
                      />
                    ))}
                  </div>
                )}
              </div>

              {/* Reguli parola */}
              {(passwordTouched || formData.password) && (
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 pt-1 text-[9px] font-bold uppercase tracking-tighter">
                  {passValidation.rules.map((rule) => (
                    <div key={rule.key} className={`flex items-center gap-1 ${rule.test ? "text-emerald-400" : "text-white/15"}`}>
                      {rule.test ? <CheckCircle2 size={10} /> : <XCircle size={10} />}
                      <span>{rule.label}</span>
                    </div>
                  ))}
                </div>
              )}

              <button
                type="submit"
                disabled={loading}
                className="group relative mt-4 flex w-full items-center justify-center gap-3 overflow-hidden rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 py-4 text-sm font-bold text-black transition-all hover:from-emerald-400 hover:to-emerald-500 active:scale-95 disabled:opacity-50 shadow-lg shadow-emerald-500/20"
              >
                {loading ? (
                  <div className="h-5 w-5 animate-spin rounded-full border-2 border-black/20 border-t-black"></div>
                ) : (
                  <>
                    <span>CREARE PROFIL</span>
                    <Zap size={16} className="text-black/60 group-hover:animate-pulse" />
                  </>
                )}
              </button>
            </form>
          )}

          <div className="mt-8 text-center text-xs text-white/25 border-t border-white/5 pt-6">
            Aveți deja acces? <Link to="/login" className="font-bold text-emerald-400 hover:underline">Autentificare</Link>
          </div>
        </div>
      </div>
    </div>
  );
} 