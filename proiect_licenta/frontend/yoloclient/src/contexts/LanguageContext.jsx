import React, { createContext, useContext, useMemo, useState } from "react";
import { STRINGS } from "../i18n/strings";

const LanguageContext = createContext(null);

const STORAGE_KEY = "app_language";

function getFromPath(obj, path) {
  return path.split(".").reduce((acc, part) => (acc && acc[part] !== undefined ? acc[part] : undefined), obj);
}

function interpolate(template, params) {
  if (!params) return template;
  return String(template).replace(/{{\s*(\w+)\s*}}/g, (_, key) => {
    if (params[key] === undefined || params[key] === null) return "";
    return String(params[key]);
  });
}

export function LanguageProvider({ children }) {
  const initialLang = localStorage.getItem(STORAGE_KEY) || "en";
  const [language, setLanguage] = useState(initialLang === "ro" ? "ro" : "en");

  const changeLanguage = (lang) => {
    const normalized = lang === "ro" ? "ro" : "en";
    setLanguage(normalized);
    localStorage.setItem(STORAGE_KEY, normalized);
  };

  const t = (key, params) => {
    const langValue = getFromPath(STRINGS[language], key);
    if (langValue !== undefined) return interpolate(langValue, params);

    const fallback = getFromPath(STRINGS.en, key);
    if (fallback !== undefined) return interpolate(fallback, params);

    return key;
  };

  const value = useMemo(() => ({ language, setLanguage: changeLanguage, t }), [language]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  const ctx = useContext(LanguageContext);
  if (!ctx) {
    throw new Error("useLanguage must be used within LanguageProvider");
  }
  return ctx;
}
