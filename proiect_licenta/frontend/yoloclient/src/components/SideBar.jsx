import React, { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Video, Crosshair,
  LogOut, LogIn, User, Languages, History,
  ChevronLeft, ChevronRight, Lock
} from "lucide-react";
import { useAuth } from "../contexts/AuthContext";
import { useLanguage } from "../contexts/LanguageContext";
import { useProcessing } from "../contexts/ProcessingContext";

export default function Sidebar({ isExpanded, setIsExpanded }) {
  const { user: authUser, logout } = useAuth();
  const { language, setLanguage, t } = useLanguage();
  const { activeJob } = useProcessing();
  const processingBadge = activeJob.status === 'processing' ? `${activeJob.progress}%` : null;
  const [user, setUser] = useState(null);
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (authUser) {
      const name = authUser.includes("@") ? authUser.split("@")[0] : authUser;
      setUser(name.charAt(0).toUpperCase() + name.slice(1));
    } else {
      setUser(null);
    }
  }, [authUser, location]);

  const handleLogout = () => {
    console.log("🚪 Inițializare logout...");
    logout();
    setTimeout(() => {
      navigate("/login");
      console.log("✅ Redirect la login completat");
    }, 150);
  };

  // --- COMPONENTA INTELIGENTĂ PENTRU LINK-URI ---
  const NavItem = ({ to, icon: Icon, label, badge }) => {
    const isActive = location.pathname === to;
    const isDisabled = !user; // Verificăm dacă e dezactivat (nu e user logat)

    // STILURI COMUNE
    const baseClasses = `relative flex items-center gap-3 p-3 rounded-xl transition-all duration-200 group mb-1 whitespace-nowrap overflow-hidden select-none`;

    // 1. CAZUL DEZACTIVAT (Nu ești logat)
    if (isDisabled) {
      return (
        <div className={`${baseClasses} text-zinc-700 cursor-not-allowed opacity-40`}>
          {React.createElement(Icon, { size: 20, className: "min-w-[20px]" })}

          <div className={`flex items-center justify-between flex-1 transition-opacity duration-300 ${isExpanded ? "opacity-100" : "opacity-0 w-0"}`}>
            <span>{label}</span>
            {isExpanded && <Lock size={12} className="text-zinc-800" />}
          </div>
        </div>
      );
    }

    // 2. CAZUL ACTIV (Ești logat - Link normal)
    return (
      <Link
        to={to}
        className={`${baseClasses}
          ${isActive
            ? "bg-emerald-500/10 text-emerald-400 shadow-lg shadow-emerald-900/10 font-medium border border-emerald-500/20"
            : "text-zinc-500 hover:bg-white/[0.03] hover:text-white cursor-pointer"
          }`}
      >
        {React.createElement(Icon, {
          size: 20,
          className: `min-w-[20px] ${isActive ? "text-emerald-400" : "text-zinc-600 group-hover:text-emerald-400"}`,
        })}
        <span className={`transition-opacity duration-300 ${isExpanded ? "opacity-100" : "opacity-0 w-0"}`}>
          {label}
        </span>
        {badge && isExpanded && (
          <span className="ml-auto text-[9px] font-bold bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 rounded border border-emerald-500/30 animate-pulse">
            {badge}
          </span>
        )}
        {badge && !isExpanded && (
          <span className="absolute top-1 right-1 w-2 h-2 bg-emerald-500 rounded-full animate-pulse" />
        )}
      </Link>
    );
  };

  const mobileItems = [
    { to: "/dashboard", icon: LayoutDashboard, label: t("common.dashboard") },
    { to: "/detection", icon: Video, label: t("common.detection"), badge: processingBadge },
    { to: "/tracking", icon: Crosshair, label: t("common.tracking") },
    { to: "/history", icon: History, label: "History" },
  ];

  return (
    <>
    <aside
      onClick={() => setIsExpanded(!isExpanded)}
      className={`fixed top-0 left-0 z-50 h-screen bg-[#0a0a0f] border-r border-white/[0.04] flex flex-col justify-between hidden md:flex transition-all duration-300 ease-in-out cursor-pointer
      ${isExpanded ? "w-64" : "w-20 hover:bg-white/[0.02]"}`}
    >

      {/* --- PARTEA DE SUS --- */}
      <div>
        {/* Header Sidebar */}
        <div className="h-20 flex items-center px-4 border-b border-white/[0.04] relative">
          <div className="w-10 h-10 bg-gradient-to-br from-emerald-400 to-emerald-600 rounded-lg flex items-center justify-center font-bold text-black shadow-md shadow-emerald-500/15 shrink-0 mx-auto md:mx-0">
            AI
          </div>

          <span className={`font-bold text-lg text-white tracking-tight ml-3 transition-opacity duration-300 ${isExpanded ? "opacity-100" : "opacity-0 w-0 overflow-hidden"}`}>
            OverWatch
          </span>

          <button
            onClick={(e) => {
              e.stopPropagation();
              setIsExpanded(!isExpanded);
            }}
            className="absolute -right-3 top-8 bg-[#0a0a0f] border border-zinc-700 text-zinc-500 rounded-full p-1 hover:text-white hover:bg-emerald-500 transition-all shadow-lg z-50"
          >
            {isExpanded ? <ChevronLeft size={14} /> : <ChevronRight size={14} />}
          </button>
        </div>

        {/* MENIUL */}
        <div className="p-3 mt-2" onClick={(e) => e.stopPropagation()}>
          <p className={`text-[10px] font-bold text-zinc-600 uppercase tracking-wider mb-4 px-2 transition-opacity duration-300 ${isExpanded ? "opacity-100" : "opacity-0 text-center"}`}>
            {isExpanded ? t("common.menu") : "OS"}
          </p>

          <NavItem to="/dashboard" icon={LayoutDashboard} label={t("common.dashboard")} />
          <NavItem to="/detection" icon={Video} label={t("common.detection")} badge={processingBadge} />
          <NavItem to="/tracking" icon={Crosshair} label={t("common.tracking")} />
          <NavItem to="/history" icon={History} label="History" />
        </div>
      </div>

      {/* --- PARTEA DE JOS (Login / Profil) --- */}
      <div className="p-3 border-t border-white/[0.04] bg-white/[0.01]" onClick={(e) => e.stopPropagation()}>
        <div className={`${isExpanded ? "mb-3 p-2.5 rounded-xl border border-zinc-800/50 bg-black/30" : "mb-3 flex justify-center"}`}>
          {isExpanded ? (
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <Languages size={14} className="text-zinc-600" />
                <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-600">
                  {t("sidebar.language")}
                </span>
              </div>

              <div className="relative p-1 rounded-full bg-black border border-zinc-800 w-[106px]">
                <div
                  className={`absolute top-1 bottom-1 w-[48px] rounded-full bg-emerald-500 transition-all duration-300 ${language === "en" ? "left-1" : "left-[53px]"
                    }`}
                />
                <div className="relative z-10 grid grid-cols-2 text-[11px] font-semibold">
                  <button
                    onClick={() => setLanguage("en")}
                    className={`py-1 rounded-full transition-colors ${language === "en" ? "text-black" : "text-zinc-500 hover:text-zinc-300"}`}
                    title={t("sidebar.english")}
                  >
                    EN
                  </button>
                  <button
                    onClick={() => setLanguage("ro")}
                    className={`py-1 rounded-full transition-colors ${language === "ro" ? "text-black" : "text-zinc-500 hover:text-zinc-300"}`}
                    title={t("sidebar.romanian")}
                  >
                    RO
                  </button>
                </div>
              </div>
            </div>
          ) : (
            <div className="inline-flex items-center gap-1 rounded-xl border border-zinc-800/50 bg-black/30 p-1 shadow-md shadow-black/30">
              <button
                onClick={() => setLanguage("en")}
                className={`h-7 w-7 rounded-md text-[10px] font-bold transition-all ${language === "en"
                  ? "bg-emerald-500 text-black shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.05]"
                  }`}
                title={t("sidebar.english")}
              >
                EN
              </button>
              <button
                onClick={() => setLanguage("ro")}
                className={`h-7 w-7 rounded-md text-[10px] font-bold transition-all ${language === "ro"
                  ? "bg-emerald-500 text-black shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300 hover:bg-white/[0.05]"
                  }`}
                title={t("sidebar.romanian")}
              >
                RO
              </button>
            </div>
          )}
        </div>

        {user ? (
          /* ESTI LOGAT: Profil + Logout */
          <div className={`flex items-center ${isExpanded ? "justify-between" : "justify-center"}`}>
            <div className="flex items-center gap-3 overflow-hidden">
              <div className="relative">
                <div className="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 shrink-0">
                  <User size={20} />
                </div>
                {/* Iconița de logout suprapusă */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleLogout();
                  }}
                  className="absolute -bottom-1 -right-1 w-5 h-5 bg-[#0a0a0f] border border-red-900 text-red-500 hover:bg-red-600 hover:text-white rounded-full flex items-center justify-center shadow-lg transition-colors"
                  title={t("common.logout")}
                >
                  <LogOut size={10} />
                </button>
              </div>
              <div className={`flex-1 min-w-0 transition-all duration-300 ${isExpanded ? "opacity-100 w-auto" : "opacity-0 w-0 overflow-hidden"}`}>
                <p className="text-sm font-medium text-white truncate">{user}</p>
                <div className="flex items-center gap-1">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                  <p className="text-[10px] text-emerald-500/60 font-bold uppercase">{t("common.online")}</p>
                </div>
              </div>
            </div>
          </div>
        ) : (
          /* NU ESTI LOGAT: Buton mare de Login */
          <Link to="/login" className={`flex items-center justify-center p-3 rounded-xl bg-emerald-500 text-black hover:bg-emerald-400 transition-all shadow-lg shadow-emerald-500/10 group`}>
            <LogIn size={20} className={isExpanded ? "mr-2" : ""} />
            {isExpanded && <span className="font-bold text-xs uppercase tracking-widest">{t("common.login")}</span>}
          </Link>
        )}
      </div>
    </aside>
    <nav className="fixed bottom-0 left-0 right-0 z-50 md:hidden border-t border-white/[0.06] bg-[#09090d]/95 px-2 py-2 backdrop-blur-xl shadow-2xl shadow-black/60">
      <div className="grid grid-cols-3 gap-1">
        {mobileItems.map(({ to, icon: Icon, label, badge }) => {
          const isActive = location.pathname === to;
          return (
            <Link
              key={to}
              to={to}
              className={`relative flex min-h-14 flex-col items-center justify-center gap-1 rounded-xl px-2 text-[10px] font-bold transition-all ${
                isActive
                  ? "bg-emerald-500/12 text-emerald-300 ring-1 ring-emerald-500/20"
                  : "text-zinc-500 hover:bg-white/[0.04] hover:text-zinc-200"
              }`}
            >
              {React.createElement(Icon, {
                size: 20,
                className: isActive ? "text-emerald-300" : "text-zinc-500",
              })}
              <span className="max-w-full truncate">{label}</span>
              {badge && (
                <span className="absolute right-3 top-2 h-2 w-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]" />
              )}
            </Link>
          );
        })}
      </div>
    </nav>
    </>
  );
}
