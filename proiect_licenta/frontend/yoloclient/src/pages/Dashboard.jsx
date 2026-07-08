import React, { useEffect, useState, useCallback } from "react";
import { Link, useNavigate } from "react-router-dom";
import axios from "axios";

const API_URL = import.meta.env.VITE_API_URL;
import {
  Activity, Video, Clock, Play, Users,
  HardDrive, ExternalLink,
  Copy, CheckCircle2, ChevronRight, UploadCloud, Trash2,
  BarChart3, AlertTriangle, X
} from "lucide-react";
import { useLanguage } from "../contexts/LanguageContext";
import "../dashboard.css";

export default function Dashboard() {
  const { language, t } = useLanguage();
  const navigate = useNavigate();
  const [user, setUser] = useState(t("dashboard.defaultUser"));
  const [copiedId, setCopiedId] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [pendingDelete, setPendingDelete] = useState(null);
  const [loading, setLoading] = useState(true);
  const [visible, setVisible] = useState(false);

  const [stats, setStats] = useState({
    total_videos: 0,
    total_people: 0,
    storage_used: 0,
    recent_activity: []
  });

  const isImageFile = (filename = "") => {
    const lower = filename.toLowerCase();
    return [".jpg", ".jpeg", ".png", ".webp", ".bmp"].some(ext => lower.endsWith(ext));
  };

  const getWatchPath = (item) =>
    isImageFile(item.filename) ? `/watch-image/${item.id}` : `/watch/${item.id}`;

  const copyVideoLink = (item) => {
    const url = `${window.location.origin}${getWatchPath(item)}`;
    navigator.clipboard.writeText(url);
    setCopiedId(item.id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const requestDeleteVideo = (item, e) => {
    e.stopPropagation();
    setPendingDelete(item);
  };

  const deleteVideo = async () => {
    if (!pendingDelete) return;

    const videoId = pendingDelete.id;
    try {
      setDeletingId(videoId);
      const token = localStorage.getItem("token");
      await axios.delete(`${API_URL}/api/videos/${videoId}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setStats(prev => ({
        ...prev,
        total_videos: Math.max(0, prev.total_videos - 1),
        recent_activity: prev.recent_activity.filter(item => item.id !== videoId)
      }));
      setPendingDelete(null);
    } catch (err) {
      console.error("Delete error:", err);
      alert(t("dashboard.deleteError"));
    } finally {
      setDeletingId(null);
    }
  };

  useEffect(() => {
    const storedUser = localStorage.getItem("user");
    if (storedUser) {
      const displayName = storedUser.includes("@") ? storedUser.split("@")[0] : storedUser;
      setUser(displayName.charAt(0).toUpperCase() + displayName.slice(1));
    }

    const fetchDashboardData = async () => {
      try {
        const token = localStorage.getItem("token");
        const res = await axios.get(`${API_URL}/api/dashboard-stats`, {
          headers: { Authorization: `Bearer ${token}` }
        });
        setStats(res.data);
      } catch (err) {
        console.error("API Error:", err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardData();

    requestAnimationFrame(() => {
      setTimeout(() => setVisible(true), 50);
    });
  }, []);

  const formatDate = useCallback((isoString) => {
    return new Date(isoString).toLocaleDateString(language === "ro" ? "ro-RO" : "en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit"
    });
  }, [language]);

  return (
    <div className="dash-page">
      <div className={`dash-content ${visible ? "dash-content--visible" : ""}`}>
        <div className="dash-header">
          <div>
            <h1 className="dash-header__title">
              {t("dashboard.hello")}, <span className="dash-header__name">{user}</span>
            </h1>
          </div>
          <div className="dash-header__status">
            <div className="dash-header__status-dot" />
            {t("dashboard.serverOnline")}
          </div>
        </div>

        <div className="dash-hero">
          <div className="dash-hero__copy">
            <div className="dash-hero__badge">
              <Activity size={13} /> {t("dashboard.aiCore")}
            </div>
            <h2>{t("dashboard.advancedAnalysis")}</h2>
            <p>{t("dashboard.advancedAnalysisDesc")}</p>

            <div className="dash-hero__buttons">
              <Link to="/detection" className="dash-btn dash-btn--primary">
                <UploadCloud size={18} />
                {t("dashboard.uploadVideo")}
              </Link>
              <Link to="/tracking" className="dash-btn dash-btn--secondary">
                <Activity size={18} />
                {t("dashboard.liveTracking")}
              </Link>
            </div>
          </div>

          <div className="dash-detection-demo" aria-hidden="true">
            <div className="dash-detection-demo__hud">
              <span>LIVE CAM 04</span>
            </div>
            <div className="dash-detection-demo__reticle" />
            <div className="dash-detection-demo__noise" />
            <div className="dash-detection-demo__grid" />
            <div className="dash-detection-demo__scan" />

            <div className="dash-person dash-person--1">
              <span className="dash-person__head" />
              <span className="dash-person__body" />
            </div>
            <div className="dash-person dash-person--2">
              <span className="dash-person__head" />
              <span className="dash-person__body" />
            </div>
            <div className="dash-person dash-person--3">
              <span className="dash-person__head" />
              <span className="dash-person__body" />
            </div>
            <div className="dash-person dash-person--4">
              <span className="dash-person__head" />
              <span className="dash-person__body" />
            </div>

            <div className="dash-box dash-box--1"><span>person 0.98</span></div>
            <div className="dash-box dash-box--2"><span>person 0.94</span></div>
            <div className="dash-box dash-box--3"><span>person 0.91</span></div>
            <div className="dash-box dash-box--4"><span>person 0.87</span></div>

            <div className="dash-track dash-track--1" />
            <div className="dash-track dash-track--2" />
            <div className="dash-track dash-track--3" />

            <div className="dash-detection-demo__counter">
              <Users size={15} />
              <span>4 DETECTED</span>
            </div>
          </div>
        </div>

        <div className="dash-lower-grid">
          <div className="dash-stats">
            <div className="dash-stat">
              <Users size={22} className="dash-stat__icon" />
              <p className="dash-stat__label">{t("dashboard.identifiedPeople")}</p>
              <p className="dash-stat__number">{loading ? "..." : stats.total_people.toLocaleString()}</p>
            </div>

            <div className="dash-stat">
              <Video size={22} className="dash-stat__icon" />
              <p className="dash-stat__label">{t("dashboard.media")}</p>
              <p className="dash-stat__number">{loading ? "-" : stats.total_videos}</p>
            </div>

            <div className="dash-stat">
              <HardDrive size={22} className="dash-stat__icon" />
              <p className="dash-stat__label">{t("dashboard.storage")}</p>
              <p className="dash-stat__number">
                {loading ? "-" : stats.storage_used}
                <span className="dash-stat__unit">MB</span>
              </p>
            </div>
          </div>

          <div className="dash-activity">
            <div className="dash-activity__header">
              <div className="dash-activity__title-wrap">
                <div className="dash-activity__icon-box">
                  <BarChart3 size={18} />
                </div>
                <h3 className="dash-activity__title">{t("dashboard.recentActivity")}</h3>
              </div>
              {!loading && stats.recent_activity.length > 0 && (
                <span className="dash-activity__count">
                  {stats.recent_activity.length} {language === "ro" ? "fisiere" : "files"}
                </span>
              )}
            </div>

            <div>
              {loading ? (
                <div className="dash-activity__empty">
                  <div className="dash-activity__spinner" />
                  <p>{t("dashboard.loadingData")}</p>
                </div>
              ) : stats.recent_activity.length === 0 ? (
                <div className="dash-activity__empty">
                  <div className="dash-activity__empty-icon">
                    <Video size={28} />
                  </div>
                  <p>{t("dashboard.noProcessedFiles")}</p>
                </div>
              ) : (
                stats.recent_activity.map((item, index) => {
                  const isCompleted = item.status === "Completed";
                  const watchPath = getWatchPath(item);

                  return (
                    <div
                      key={item.id}
                      className={`dash-activity__item ${
                        index !== stats.recent_activity.length - 1
                          ? "dash-activity__item--bordered"
                          : ""
                      } ${deletingId === item.id ? "dash-activity__item--deleting" : ""}`}
                      style={{ animationDelay: `${index * 60}ms` }}
                    >
                      <div
                        className="dash-activity__item-left"
                        onClick={() => isCompleted && navigate(watchPath)}
                      >
                        <div
                          className={`dash-activity__play ${
                            isCompleted ? "dash-activity__play--done" : ""
                          }`}
                        >
                          <Play size={20} fill={isCompleted ? "currentColor" : "none"} />
                        </div>

                        <div className="dash-activity__item-info">
                          <p className="dash-activity__item-name">{item.filename}</p>
                          <div className="dash-activity__item-meta">
                            <span>
                              <Clock size={13} /> {formatDate(item.created_at)}
                            </span>
                            <span className="meta-people">
                              <Users size={13} /> {item.people_count} {t("dashboard.peopleAbbrev")}
                            </span>
                          </div>
                        </div>
                      </div>

                      <div className="dash-activity__item-right">
                        <div
                          className={`dash-activity__badge ${
                            isCompleted
                              ? "dash-activity__badge--done"
                              : "dash-activity__badge--progress"
                          }`}
                        >
                          {isCompleted ? t("dashboard.completed") : t("dashboard.inProgress")}
                        </div>

                        <div className="dash-activity__actions">
                          {isCompleted && (
                            <>
                              <button
                                onClick={(e) => { e.stopPropagation(); copyVideoLink(item); }}
                                className="dash-activity__action-btn"
                                title={t("dashboard.copyLink")}
                              >
                                {copiedId === item.id
                                  ? <CheckCircle2 size={16} style={{ color: "#00e676" }} />
                                  : <Copy size={16} />
                                }
                              </button>
                              <Link
                                to={watchPath}
                                onClick={(e) => e.stopPropagation()}
                                className="dash-activity__action-btn"
                              >
                                <ExternalLink size={16} />
                              </Link>
                            </>
                          )}

                          <button
                            onClick={(e) => requestDeleteVideo(item, e)}
                            disabled={deletingId === item.id}
                            className="dash-activity__action-btn dash-activity__action-btn--delete"
                            title={language === "ro" ? "Sterge fisierul" : "Delete file"}
                          >
                            {deletingId === item.id ? (
                              <div className="dash-activity__delete-spinner" />
                            ) : (
                              <Trash2 size={16} />
                            )}
                          </button>
                        </div>

                        <div className="dash-activity__chevron">
                          <ChevronRight size={20} />
                        </div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        </div>
      </div>

      {pendingDelete && (
        <div className="dash-delete-modal" role="dialog" aria-modal="true" aria-labelledby="dash-delete-title">
          <div className="dash-delete-modal__backdrop" onClick={() => !deletingId && setPendingDelete(null)} />
          <div className="dash-delete-modal__card">
            <button
              type="button"
              className="dash-delete-modal__close"
              onClick={() => setPendingDelete(null)}
              disabled={Boolean(deletingId)}
              aria-label="Close"
            >
              <X size={16} />
            </button>

            <div className="dash-delete-modal__icon">
              <AlertTriangle size={24} />
            </div>

            <div>
              <h3 id="dash-delete-title" className="dash-delete-modal__title">
                {language === "ro" ? "Stergi fisierul procesat?" : "Delete processed file?"}
              </h3>
              <p className="dash-delete-modal__text">
                {language === "ro"
                  ? "Fisierul si rezultatele asociate vor fi eliminate din dashboard."
                  : "The file and its related results will be removed from the dashboard."}
              </p>
              <div className="dash-delete-modal__file">
                <Video size={15} />
                <span>{pendingDelete.filename}</span>
              </div>
            </div>

            <div className="dash-delete-modal__actions">
              <button
                type="button"
                className="dash-delete-modal__btn dash-delete-modal__btn--cancel"
                onClick={() => setPendingDelete(null)}
                disabled={Boolean(deletingId)}
              >
                {language === "ro" ? "Anuleaza" : "Cancel"}
              </button>
              <button
                type="button"
                className="dash-delete-modal__btn dash-delete-modal__btn--danger"
                onClick={deleteVideo}
                disabled={Boolean(deletingId)}
              >
                {deletingId ? (
                  <>
                    <span className="dash-activity__delete-spinner" />
                    {language === "ro" ? "Se sterge..." : "Deleting..."}
                  </>
                ) : (
                  <>
                    <Trash2 size={15} />
                    {language === "ro" ? "Sterge" : "Delete"}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
