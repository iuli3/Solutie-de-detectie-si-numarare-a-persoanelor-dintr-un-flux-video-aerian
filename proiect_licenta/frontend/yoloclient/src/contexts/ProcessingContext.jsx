import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { io } from "socket.io-client";

const ProcessingContext = createContext(null);

const IDLE_JOB = {
  videoId:     null,
  fileName:    null,
  status:      "idle",   // 'idle' | 'processing' | 'done' | 'error' | 'stopped'
  progress:    0,
  peopleCount: 0,
  frameNumber: 0,
  totalFrames: 0,
};

export function ProcessingProvider({ children }) {
  const [socket, setSocket]     = useState(null);
  const [activeJob, setActiveJob] = useState(IDLE_JOB);

  // ── Socket unic pentru toată sesiunea ────────────────────────────────────
  useEffect(() => {
    const s = io(`${import.meta.env.VITE_API_URL}`);
    setSocket(s);

    // Actualizare progres — date ușoare, doar ce trebuie să știe orice pagină
    s.on("frame", (data) => {
      setActiveJob(prev => {
        if (prev.status !== "processing") return prev;
        if (data.video_id && prev.videoId && String(data.video_id) !== String(prev.videoId)) return prev;
        return {
          ...prev,
          progress:    Number(data.progress    ?? prev.progress),
          peopleCount: Number(data.people_count ?? prev.peopleCount),
          frameNumber: Number(data.frame_number ?? prev.frameNumber),
          totalFrames: Number(data.total_frames ?? prev.totalFrames),
        };
      });
    });

    s.on("processing_complete", (stats) => {
      setActiveJob(prev => {
        if (stats.video_id && prev.videoId && String(stats.video_id) !== String(prev.videoId)) return prev;
        return { ...prev, status: "done", progress: 100 };
      });
    });

    s.on("processing_stopped", (data) => {
      setActiveJob(prev => {
        if (data?.video_id && prev.videoId && String(data.video_id) !== String(prev.videoId)) return prev;
        return { ...prev, status: "stopped" };
      });
    });

    s.on("reid_complete", () => {
      setActiveJob(prev => (
        prev.status === "processing"
          ? { ...prev, status: "done", progress: 100 }
          : prev
      ));
    });

    s.on("reid_stopped", () => {
      setActiveJob(prev => (
        prev.status === "processing"
          ? { ...prev, status: "stopped" }
          : prev
      ));
    });

    s.on("error", () => {
      setActiveJob(prev => prev.status === "processing" ? { ...prev, status: "error" } : prev);
    });

    return () => {
      s.disconnect();
      setSocket(null);
    };
  }, []);

  // ── Reset la logout ───────────────────────────────────────────────────────
  useEffect(() => {
    const handleLogout = () => setActiveJob(IDLE_JOB);
    window.addEventListener("user-logout", handleLogout);
    return () => window.removeEventListener("user-logout", handleLogout);
  }, []);

  const startJob = useCallback((videoId, fileName) => {
    setActiveJob({ ...IDLE_JOB, videoId, fileName, status: "processing" });
  }, []);

  const clearJob = useCallback(() => {
    setActiveJob(IDLE_JOB);
  }, []);

  return (
    <ProcessingContext.Provider value={{ socket, activeJob, startJob, clearJob }}>
      {children}
    </ProcessingContext.Provider>
  );
}

export function useProcessing() {
  const ctx = useContext(ProcessingContext);
  if (!ctx) throw new Error("useProcessing must be inside ProcessingProvider");
  return ctx;
}
