import { useCallback, useEffect, useRef, useState } from "react";
import {
  uploadVideo,
  uploadThumbnail,
  getFactoryCategories,
  getActiveBots,
  publishContent,
  getPublishJobs,
  getPublishJob,
  getDefaultThumbnails,
  createDefaultThumbnail,
  renameDefaultThumbnail,
  deleteDefaultThumbnail,
  deletePublishJob,
} from "../api/endpoints";
import type {
  Bot,
  ContentCategory,
  DefaultThumbnail,
  PublishJob,
  UploadedVideo,
} from "../types";

/* ── helpers ───────────────────────────────────────────── */

let _idCounter = 0;
const uid = () => `v_${++_idCounter}_${Date.now()}`;

const STORAGE_KEY = "cf_uploads";
const DEFAULTS_KEY = "cf_publish_defaults";

interface PublishDefaults {
  mode: "solo" | "group";
  ratePerMinute: number;
  deletionSeconds: number;
  groupCategory: string;
  groupCreditCost: number;
  groupCreditMode: string;
  groupCreditPerItem: number;
  uploadBotId: number;
  deliveryBotId: number;
}

function loadDefaults(): Partial<PublishDefaults> {
  try {
    const raw = localStorage.getItem(DEFAULTS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as Partial<PublishDefaults>;
  } catch { return {}; }
}

function saveDefaults(d: PublishDefaults) {
  try { localStorage.setItem(DEFAULTS_KEY, JSON.stringify(d)); } catch { /* ignore */ }
}

function loadSavedUploads(): UploadedVideo[] {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const items = JSON.parse(raw) as UploadedVideo[];
    // Drop items still marked as uploading (interrupted by tab switch)
    return items
      .filter((v) => !v.uploading && !v.error && v.storage_message_id > 0)
      .map((v) => ({ ...v, uploading: false, uploaded: true, file: null }));
  } catch {
    return [];
  }
}

function saveUploads(items: UploadedVideo[]) {
  try {
    // Only persist uploaded items — staged files have File objects that can't be serialized
    const saveable = items.filter((v) => v.uploaded && !v.error && v.storage_message_id > 0);
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(saveable));
  } catch { /* quota exceeded — ignore */ }
}

/* ── styles ────────────────────────────────────────────── */

const card: React.CSSProperties = {
  background: "#fff",
  borderRadius: 8,
  padding: 20,
  boxShadow: "0 1px 3px rgba(0,0,0,.1)",
  marginBottom: 16,
};

const dropZone: React.CSSProperties = {
  border: "2px dashed #aaa",
  borderRadius: 8,
  padding: "40px 20px",
  textAlign: "center",
  cursor: "pointer",
  transition: "border-color .2s, background .2s",
};

const dropZoneActive: React.CSSProperties = {
  ...dropZone,
  borderColor: "#4A90E2",
  background: "#eaf3ff",
};

const btn: React.CSSProperties = {
  padding: "8px 18px",
  border: "none",
  borderRadius: 4,
  cursor: "pointer",
  fontWeight: 600,
  fontSize: 14,
};

const btnPrimary: React.CSSProperties = {
  ...btn,
  background: "#4A90E2",
  color: "#fff",
};

const btnSuccess: React.CSSProperties = {
  ...btn,
  background: "#2ecc71",
  color: "#fff",
};

const btnDanger: React.CSSProperties = {
  ...btn,
  background: "#e74c3c",
  color: "#fff",
};

const input: React.CSSProperties = {
  padding: "6px 8px",
  border: "1px solid #ccc",
  borderRadius: 4,
  fontSize: 13,
  width: "100%",
  boxSizing: "border-box",
};

const select_: React.CSSProperties = { ...input };

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "10px 8px",
  borderBottom: "2px solid #ddd",
  fontSize: 13,
  fontWeight: 600,
  color: "#555",
  whiteSpace: "nowrap",
};

const tdStyle: React.CSSProperties = {
  padding: "8px",
  borderBottom: "1px solid #eee",
  verticalAlign: "middle",
  fontSize: 13,
};

/* ── component ─────────────────────────────────────────── */

export default function ContentFactory() {
  const defaults = loadDefaults();
  const [videos, setVideos] = useState<UploadedVideo[]>(loadSavedUploads);
  const [categories, setCategories] = useState<ContentCategory[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [mode, setMode] = useState<"solo" | "group">(defaults.mode || "solo");
  const [dragging, setDragging] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [ratePerMinute, setRatePerMinute] = useState(defaults.ratePerMinute ?? 0);
  const [deletionSeconds, setDeletionSeconds] = useState(defaults.deletionSeconds ?? 0);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Persistent jobs from DB
  const [jobs, setJobs] = useState<PublishJob[]>([]);

  // Default thumbnails
  const [defaultThumbs, setDefaultThumbs] = useState<DefaultThumbnail[]>([]);
  const [newThumbName, setNewThumbName] = useState("");
  const [thumbUploading, setThumbUploading] = useState(false);
  const [editingThumbId, setEditingThumbId] = useState<number | null>(null);
  const [editingThumbName, setEditingThumbName] = useState("");

  // Default bot IDs for newly staged files (from saved defaults)
  const defaultUploadBotId = defaults.uploadBotId ?? 0;
  const defaultDeliveryBotId = defaults.deliveryBotId ?? 0;

  // Group mode settings
  const [groupTitle, setGroupTitle] = useState("Content Pack");
  const [groupCategory, setGroupCategory] = useState(defaults.groupCategory || "free");
  const [groupCreditCost, setGroupCreditCost] = useState(defaults.groupCreditCost ?? 0);
  const [groupCreditMode, setGroupCreditMode] = useState(defaults.groupCreditMode || "per_item");
  const [groupCreditPerItem, setGroupCreditPerItem] = useState(defaults.groupCreditPerItem ?? 1);
  const [groupBotId, setGroupBotId] = useState(0);
  const [groupThumbId, setGroupThumbId] = useState("");

  // Persist uploads to sessionStorage so tab switches don't lose them
  useEffect(() => {
    saveUploads(videos);
  }, [videos]);

  // Load initial data
  useEffect(() => {
    getFactoryCategories()
      .then(setCategories)
      .catch(() => {
        setCategories([
          { tag: "free", label: "Free" },
          { tag: "credits", label: "Credits" },
          { tag: "credits_only", label: "Credits Only" },
        ]);
      });
    getActiveBots()
      .then((b) => {
        setBots(b);
        if (b.length > 0) {
          setGroupBotId(defaults.deliveryBotId || b[0].id);
        }
      })
      .catch(() => setBots([]));
    getDefaultThumbnails().then(setDefaultThumbs).catch(() => {});
    // Load existing jobs from DB
    _loadJobs();
  }, []);

  const _loadJobs = () => {
    getPublishJobs()
      .then(setJobs)
      .catch(() => {});
  };

  // Poll active jobs for real-time progress
  useEffect(() => {
    const activeIds = jobs.filter((j) => j.status === "queued" || j.status === "processing").map((j) => j.id);
    if (activeIds.length === 0) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return; // already polling
    pollRef.current = setInterval(async () => {
      try {
        const updated = await getPublishJobs();
        setJobs(updated);
        const stillActive = updated.some((j) => j.status === "queued" || j.status === "processing");
        if (!stillActive && pollRef.current) {
          clearInterval(pollRef.current);
          pollRef.current = null;
          setPublishing(false);
        }
      } catch { /* ignore */ }
    }, 2000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobs]);

  /* ── file handling ──────────────────────────────── */

  // Stage files without uploading — user picks bots first, then clicks "Start Upload"
  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      const defUpload = defaultUploadBotId || (bots.length > 0 ? bots[0].id : 0);
      const defDelivery = defaultDeliveryBotId || (bots.length > 0 ? bots[0].id : 0);
      const newVideos: UploadedVideo[] = [];

      for (const file of Array.from(files)) {
        const mt = file.type.startsWith("video/")
          ? "video"
          : file.type === "image/gif"
            ? "animation"
            : file.type.startsWith("image/")
              ? "photo"
              : "document";
        const v: UploadedVideo = {
          id: uid(),
          filename: file.name,
          file,
          storage_chat_id: 0,
          storage_message_id: 0,
          file_id: "",
          media_type: mt,
          title: file.name.replace(/\.[^.]+$/, ""),
          access_type: "free",
          credit_cost: 0,
          credit_mode: "per_item",
          credit_per_item: 1,
          upload_bot_id: defUpload,
          bot_id: defDelivery,
          uploading: false,
          uploaded: false,
        };
        newVideos.push(v);
      }

      setVideos((prev) => [...prev, ...newVideos]);
    },
    [bots, defaultUploadBotId, defaultDeliveryBotId],
  );

  // Upload staged files to Telegram — each item uses its own upload_bot_id
  const handleStartUpload = useCallback(async () => {
    const staged = videos.filter((v) => !v.uploaded && !v.uploading && v.file);
    if (staged.length === 0) return;

    // Mark all staged as uploading
    setVideos((prev) =>
      prev.map((v) => (v.file && !v.uploaded ? { ...v, uploading: true } : v)),
    );

    for (const v of staged) {
      if (!v.file) continue;
      try {
        const result = await uploadVideo(v.file, undefined, v.upload_bot_id || undefined);
        setVideos((prev) =>
          prev.map((x) =>
            x.id === v.id
              ? {
                  ...x,
                  storage_chat_id: result.storage_chat_id,
                  storage_message_id: result.storage_message_id,
                  file_id: result.file_id,
                  thumbnail_file_id: result.thumbnail_file_id || x.thumbnail_file_id,
                  duration: result.duration,
                  width: result.width,
                  height: result.height,
                  uploading: false,
                  uploaded: true,
                  file: null,
                }
              : x,
          ),
        );
      } catch (err: unknown) {
        let msg = "Upload failed";
        if (err && typeof err === "object" && "response" in err) {
          const resp = (err as { response?: { data?: { detail?: string }; status?: number } }).response;
          msg = resp?.data?.detail || `Upload failed (HTTP ${resp?.status})`;
        } else if (err instanceof Error) {
          msg = err.message;
        }
        setVideos((prev) =>
          prev.map((x) =>
            x.id === v.id ? { ...x, uploading: false, error: msg } : x,
          ),
        );
      }
    }
  }, [videos]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (e.dataTransfer.files.length) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const onFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files?.length) handleFiles(e.target.files);
      e.target.value = "";
    },
    [handleFiles],
  );

  /* ── row helpers ────────────────────────────────── */

  const updateVideo = (id: string, patch: Partial<UploadedVideo>) => {
    setVideos((prev) => prev.map((v) => (v.id === id ? { ...v, ...patch } : v)));
  };

  const removeVideo = (id: string) => {
    setVideos((prev) => prev.filter((v) => v.id !== id));
  };

  const handleThumbUpload = async (videoId: string, file: File) => {
    try {
      const res = await uploadThumbnail(file);
      updateVideo(videoId, { thumbnail_file_id: res.file_id });
    } catch {
      alert("Thumbnail upload failed");
    }
  };

  const handleGroupThumb = async (file: File) => {
    try {
      const res = await uploadThumbnail(file);
      setGroupThumbId(res.file_id);
    } catch {
      alert("Thumbnail upload failed");
    }
  };

  /* ── default thumbnail management ───────────────── */

  const handleAddDefaultThumb = async (file: File) => {
    if (!newThumbName.trim()) {
      alert("Enter a name for the thumbnail first");
      return;
    }
    setThumbUploading(true);
    try {
      const res = await uploadThumbnail(file);
      const saved = await createDefaultThumbnail(newThumbName.trim(), res.file_id);
      setDefaultThumbs((prev) => [...prev, saved]);
      setNewThumbName("");
    } catch {
      alert("Failed to save default thumbnail");
    }
    setThumbUploading(false);
  };

  const handleRenameThumb = async (id: number) => {
    if (!editingThumbName.trim()) return;
    try {
      const updated = await renameDefaultThumbnail(id, editingThumbName.trim());
      setDefaultThumbs((prev) => prev.map((t) => (t.id === id ? updated : t)));
      setEditingThumbId(null);
    } catch {
      alert("Rename failed");
    }
  };

  const handleDeleteThumb = async (id: number) => {
    if (!confirm("Delete this default thumbnail?")) return;
    try {
      await deleteDefaultThumbnail(id);
      setDefaultThumbs((prev) => prev.filter((t) => t.id !== id));
    } catch {
      alert("Delete failed");
    }
  };

  /* ── apply-to-all ───────────────────────────────── */

  const applyToAll = (field: keyof UploadedVideo, value: unknown) => {
    setVideos((prev) => prev.map((v) => ({ ...v, [field]: value })));
  };

  /* ── publish ────────────────────────────────────── */

  const readyVideos = videos.filter((v) => v.uploaded && !v.error && v.storage_message_id > 0);
  const stagedVideos = videos.filter((v) => !v.uploaded && !v.uploading && !v.error && v.file);
  const uploadingVideos = videos.filter((v) => v.uploading);

  const handlePublish = async () => {
    if (readyVideos.length === 0) return;
    setPublishing(true);

    try {
      const items = readyVideos.map((v) => {
        const thumbId = mode === "group"
          ? (groupThumbId || v.thumbnail_file_id || null)
          : (v.thumbnail_file_id || null);

        return {
          storage_chat_id: v.storage_chat_id,
          storage_message_id: v.storage_message_id,
          file_id: v.file_id || null,
          media_type: v.media_type,
          title: v.title,
          access_type: mode === "group" ? groupCategory : v.access_type,
          credit_cost: mode === "group" ? groupCreditCost : v.credit_cost,
          credit_mode: mode === "group" ? groupCreditMode : v.credit_mode,
          credit_per_item: mode === "group" ? groupCreditPerItem : v.credit_per_item,
          bot_id: mode === "group" ? groupBotId : v.bot_id,
          thumbnail_file_id: thumbId,
        };
      });

      const payload: Parameters<typeof publishContent>[0] = {
        mode,
        items,
        rate_per_minute: ratePerMinute,
        deletion_seconds: deletionSeconds > 0 ? deletionSeconds : null,
      };

      if (mode === "group") {
        payload.group_settings = {
          title: groupTitle,
          access_type: groupCategory,
          credit_cost: groupCreditCost,
          credit_mode: groupCreditMode,
          credit_per_item: groupCreditPerItem,
          bot_id: groupBotId,
          thumbnail_file_id: groupThumbId || null,
        };
      }

      await publishContent(payload);

      // Clear upload area — job now lives in DB
      setVideos([]);

      // Reload jobs to show the newly created one
      _loadJobs();
    } catch (err: unknown) {
      alert("Publish failed: " + (err instanceof Error ? err.message : err));
      setPublishing(false);
    }
  };

  const handleDeleteJob = async (jobId: string) => {
    try {
      await deletePublishJob(jobId);
      setJobs((prev) => prev.filter((j) => j.id !== jobId));
    } catch {
      alert("Cannot delete this job");
    }
  };

  /* ── thumbnail selector component ──────────────── */

  const ThumbSelector = ({
    value,
    onChange,
    onUpload,
  }: {
    value: string;
    onChange: (fileId: string) => void;
    onUpload: (file: File) => void;
  }) => (
    <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
      <select
        value={value && defaultThumbs.some((t) => t.file_id === value) ? value : "_custom"}
        onChange={(e) => {
          if (e.target.value === "_custom") return; // handled by file input
          if (e.target.value === "_none") { onChange(""); return; }
          onChange(e.target.value);
        }}
        style={{ ...select_, width: 120, fontSize: 11 }}
      >
        <option value="_none">— None —</option>
        {defaultThumbs.map((t) => (
          <option key={t.id} value={t.file_id}>
            🖼️ {t.name}
          </option>
        ))}
        <option value="_custom">📁 Custom upload…</option>
      </select>
      {value ? (
        <span style={{ color: "#2ecc71", fontSize: 12 }}>
          ✅{" "}
          <button
            onClick={() => onChange("")}
            style={{ ...btn, padding: "1px 6px", fontSize: 11, background: "#eee" }}
          >
            ✕
          </button>
        </span>
      ) : (
        <label
          style={{
            ...btn,
            padding: "4px 8px",
            fontSize: 11,
            background: "#f0f0f0",
            display: "inline-block",
          }}
        >
          Upload
          <input
            type="file"
            accept="image/*"
            style={{ display: "none" }}
            onChange={(e) => {
              if (e.target.files?.[0]) onUpload(e.target.files[0]);
            }}
          />
        </label>
      )}
    </div>
  );

  /* ── render ─────────────────────────────────────── */

  // Active and completed/failed jobs
  const activeJobs = jobs.filter((j) => j.status === "queued" || j.status === "processing");
  const doneJobs = jobs.filter((j) => j.status === "completed" || j.status === "failed");

  return (
    <>
      <h1 style={{ marginBottom: 8 }}>🏭 Content Factory</h1>
      <p style={{ color: "#666", marginTop: 0, marginBottom: 20 }}>
        Upload, configure, and bulk-publish content to Telegram.
      </p>

      {/* ── Publish Jobs (always visible) ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>
          📊 Publish Jobs
          {activeJobs.length > 0 && <span style={{ color: "#f39c12", marginLeft: 8 }}>({activeJobs.length} running)</span>}
        </h3>

        {jobs.length === 0 && (
          <p style={{ color: "#aaa", margin: 0, fontSize: 13 }}>No publish jobs yet. Upload files below and publish to start a job.</p>
        )}

        {activeJobs.map((job) => (
          <div
            key={job.id}
            style={{
              padding: 12,
              marginBottom: 8,
              background: "#fffbea",
              borderRadius: 6,
              border: "1px solid #fce588",
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                🔄 Job #{job.id} — {job.mode.toUpperCase()} — {job.rate_per_minute > 0 ? `${job.rate_per_minute}/min` : "⚡ All at once"}
              </span>
              <span style={{ fontSize: 12, color: "#b8860b", fontWeight: 600 }}>
                {job.status === "processing" ? "Processing…" : "Queued"}
              </span>
            </div>
            <div style={{ background: "#eee", borderRadius: 6, height: 22, overflow: "hidden" }}>
              <div
                style={{
                  height: "100%",
                  borderRadius: 6,
                  background: job.failed > 0 ? "#f39c12" : "#2ecc71",
                  width: `${Math.round(((job.completed + job.failed) / Math.max(job.total, 1)) * 100)}%`,
                  transition: "width .3s",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 700,
                  color: "#fff",
                  minWidth: 40,
                }}
              >
                {job.completed + job.failed} / {job.total}
              </div>
            </div>
            <div style={{ display: "flex", gap: 16, fontSize: 12, marginTop: 6, color: "#666" }}>
              <span>✅ {job.completed} done</span>
              <span>❌ {job.failed} failed</span>
              <span>📦 {job.total} total</span>
            </div>
          </div>
        ))}

        {doneJobs.map((job) => (
          <div
            key={job.id}
            style={{
              padding: 12,
              marginBottom: 8,
              background: job.status === "completed" ? "#f0fff4" : "#fff5f5",
              borderRadius: 6,
              border: `1px solid ${job.status === "completed" ? "#c3e6cb" : "#f5c6cb"}`,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                {job.status === "completed" ? "✅" : "❌"} Job #{job.id} — {job.mode.toUpperCase()}
                {" — "}{job.rate_per_minute > 0 ? `${job.rate_per_minute}/min` : "All at once"}
              </span>
              <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                <span style={{ fontSize: 12, color: "#888" }}>
                  {job.completed} completed, {job.failed} failed / {job.total} total
                </span>
                <button
                  onClick={() => handleDeleteJob(job.id)}
                  style={{ ...btn, padding: "2px 8px", fontSize: 11, background: "#eee" }}
                >
                  🗑️
                </button>
              </div>
            </div>

            {job.error && (
              <p style={{ color: "#e74c3c", fontSize: 12, margin: "0 0 8px" }}>Error: {job.error}</p>
            )}

            {job.results.length > 0 && (
              <details style={{ marginTop: 4 }}>
                <summary style={{ cursor: "pointer", fontSize: 12, color: "#555" }}>
                  Show {job.results.length} result{job.results.length > 1 ? "s" : ""}
                </summary>
                <div style={{ maxHeight: 200, overflowY: "auto", marginTop: 4 }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
                    <thead>
                      <tr>
                        <th style={{ ...thStyle, fontSize: 11 }}>Title</th>
                        <th style={{ ...thStyle, fontSize: 11 }}>Pack ID</th>
                        <th style={{ ...thStyle, fontSize: 11 }}>Deep Link</th>
                        <th style={{ ...thStyle, fontSize: 11 }}>Channel</th>
                      </tr>
                    </thead>
                    <tbody>
                      {job.results.map((r, i) => (
                        <tr key={i}>
                          <td style={tdStyle}>{r.title || r.error || "—"}</td>
                          <td style={tdStyle}>{r.pack_id ?? "—"}</td>
                          <td style={tdStyle}>
                            {r.deep_link ? (
                              <button
                                onClick={() => {
                                  try { navigator.clipboard.writeText(r.deep_link!); } catch { /* fallback */ }
                                }}
                                style={{ ...btn, padding: "2px 8px", fontSize: 11, background: "#eee" }}
                                title={r.deep_link}
                              >
                                📋 Copy
                              </button>
                            ) : (
                              <span style={{ color: "#e74c3c" }}>{r.error || "—"}</span>
                            )}
                          </td>
                          <td style={tdStyle}>
                            {r.channel_posted ? (
                              <span style={{ color: "#2ecc71" }}>✅</span>
                            ) : r.error ? (
                              <span style={{ color: "#e74c3c" }}>❌</span>
                            ) : (
                              <span style={{ color: "#f39c12" }}>⚠️</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
            )}
          </div>
        ))}
      </div>

      {/* ── Publish Settings (always visible) ── */}
      <div style={card}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
          <h3 style={{ margin: 0 }}>⚙️ Publish Settings</h3>
          <button
            onClick={() => {
              saveDefaults({
                mode,
                ratePerMinute,
                deletionSeconds,
                groupCategory,
                groupCreditCost,
                groupCreditMode,
                groupCreditPerItem,
                uploadBotId: defaultUploadBotId,
                deliveryBotId: defaultDeliveryBotId,
              });
              alert("Defaults saved!");
            }}
            style={{ ...btn, padding: "6px 14px", fontSize: 12, background: "#f0f0f0", border: "1px solid #ccc" }}
          >
            💾 Set as Default
          </button>
        </div>
        <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
          <div>
            <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Publish Rate</label>
            <select
              value={ratePerMinute}
              onChange={(e) => setRatePerMinute(Number(e.target.value))}
              style={{ ...select_, width: 200 }}
            >
              <option value={0}>⚡ Send all at once</option>
              <option value={1}>1 per minute</option>
              <option value={2}>2 per minute</option>
              <option value={3}>3 per minute</option>
              <option value={5}>5 per minute</option>
              <option value={10}>10 per minute</option>
            </select>
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Auto-Delete (sec)</label>
            <input
              type="number"
              min={0}
              value={deletionSeconds}
              onChange={(e) => setDeletionSeconds(Number(e.target.value))}
              style={{ ...input, width: 100 }}
              placeholder="0 = never"
            />
          </div>
          <div>
            <label style={{ display: "block", fontWeight: 600, fontSize: 13, marginBottom: 4 }}>Mode</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value as "solo" | "group")}
              style={{ ...select_, width: 260 }}
            >
              <option value="solo">Solo — Each file gets its own deep link</option>
              <option value="group">Group — All files share one deep link</option>
            </select>
          </div>
        </div>
      </div>

      {/* ── Default Thumbnails Manager ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>🖼️ Default Thumbnails</h3>
        <p style={{ fontSize: 12, color: "#888", margin: "0 0 12px" }}>
          Save reusable thumbnails to quickly assign them to content.
        </p>

        {/* Thumbnail list */}
        {defaultThumbs.length > 0 && (
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
            {defaultThumbs.map((t) => (
              <div
                key={t.id}
                style={{
                  padding: "8px 12px",
                  background: "#f0f7ff",
                  borderRadius: 6,
                  border: "1px solid #c5dcf5",
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 13,
                }}
              >
                {editingThumbId === t.id ? (
                  <>
                    <input
                      value={editingThumbName}
                      onChange={(e) => setEditingThumbName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleRenameThumb(t.id); }}
                      style={{ ...input, width: 100, fontSize: 12 }}
                      autoFocus
                    />
                    <button
                      onClick={() => handleRenameThumb(t.id)}
                      style={{ ...btn, padding: "2px 8px", fontSize: 11, background: "#2ecc71", color: "#fff" }}
                    >
                      ✓
                    </button>
                    <button
                      onClick={() => setEditingThumbId(null)}
                      style={{ ...btn, padding: "2px 8px", fontSize: 11, background: "#eee" }}
                    >
                      ✕
                    </button>
                  </>
                ) : (
                  <>
                    <span style={{ fontWeight: 600 }}>🖼️ {t.name}</span>
                    <button
                      onClick={() => { setEditingThumbId(t.id); setEditingThumbName(t.name); }}
                      style={{ ...btn, padding: "2px 6px", fontSize: 11, background: "#eee" }}
                      title="Rename"
                    >
                      ✏️
                    </button>
                    <button
                      onClick={() => handleDeleteThumb(t.id)}
                      style={{ ...btn, padding: "2px 6px", fontSize: 11, background: "#fee", color: "#e74c3c" }}
                      title="Delete"
                    >
                      🗑️
                    </button>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Add new default thumbnail */}
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <input
            value={newThumbName}
            onChange={(e) => setNewThumbName(e.target.value)}
            placeholder="Thumbnail name (e.g. Promo #1)"
            style={{ ...input, width: 200 }}
          />
          <label
            style={{
              ...btn,
              padding: "6px 14px",
              fontSize: 13,
              background: thumbUploading ? "#ccc" : "#4A90E2",
              color: "#fff",
              display: "inline-block",
              opacity: thumbUploading || !newThumbName.trim() ? 0.6 : 1,
              pointerEvents: thumbUploading ? "none" : "auto",
            }}
          >
            {thumbUploading ? "Uploading…" : "➕ Upload & Save"}
            <input
              type="file"
              accept="image/*"
              style={{ display: "none" }}
              disabled={thumbUploading || !newThumbName.trim()}
              onChange={(e) => {
                if (e.target.files?.[0]) handleAddDefaultThumb(e.target.files[0]);
              }}
            />
          </label>
        </div>
      </div>

      {/* ── Upload Zone ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>Upload Files</h3>
        <div
          style={dragging ? dropZoneActive : dropZone}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <p style={{ fontSize: 16, margin: 0 }}>
            {dragging ? "Drop files here…" : "📁 Drag & drop files here, or click to browse"}
          </p>
          <p style={{ fontSize: 12, color: "#888", margin: "8px 0 0" }}>
            Videos, images, documents — up to 2 GB per file
          </p>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="*/*"
          multiple
          style={{ display: "none" }}
          onChange={onFileInput}
        />
      </div>

      {/* ── Upload Control (shown when files are staged) ── */}
      {(stagedVideos.length > 0 || uploadingVideos.length > 0) && (
        <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center", background: "#f0f7ff", border: "1px solid #c5dcf5" }}>
          <div>
            <span style={{ fontWeight: 600, fontSize: 14 }}>
              {uploadingVideos.length > 0
                ? `⏳ Uploading ${uploadingVideos.length} file${uploadingVideos.length > 1 ? "s" : ""}…`
                : `📂 ${stagedVideos.length} file${stagedVideos.length > 1 ? "s" : ""} staged`}
            </span>
            <span style={{ fontSize: 12, color: "#888", marginLeft: 12 }}>
              (each file uses its own upload bot)
            </span>
          </div>
          <button
            onClick={handleStartUpload}
            disabled={uploadingVideos.length > 0 || stagedVideos.length === 0}
            style={{
              ...btnPrimary,
              padding: "10px 24px",
              fontSize: 15,
              opacity: uploadingVideos.length > 0 ? 0.6 : 1,
            }}
          >
            {uploadingVideos.length > 0 ? "⏳ Uploading…" : "🚀 Start Upload"}
          </button>
        </div>
      )}

      {/* ── Group Mode Settings (shown when group mode selected and files uploaded) ── */}
      {videos.length > 0 && mode === "group" && (
        <div style={card}>
          <h4 style={{ margin: "0 0 12px", color: "#2a5db0" }}>📦 Group Pack Settings</h4>
          <div style={{ display: "flex", gap: 16, flexWrap: "wrap", alignItems: "flex-end" }}>
            <div style={{ flex: "1 1 200px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Title</label>
              <input value={groupTitle} onChange={(e) => setGroupTitle(e.target.value)} style={input} />
            </div>
            <div style={{ flex: "0 0 160px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Category</label>
              <select value={groupCategory} onChange={(e) => setGroupCategory(e.target.value)} style={select_}>
                {categories.map((c) => (
                  <option key={c.tag} value={c.tag}>{c.label}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: "0 0 130px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Credit Mode</label>
              <select value={groupCreditMode} onChange={(e) => setGroupCreditMode(e.target.value)} style={select_}>
                <option value="per_item">Per Item</option>
                <option value="per_pack">Per Pack</option>
              </select>
            </div>
            <div style={{ flex: "0 0 100px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>
                {groupCreditMode === "per_pack" ? "Pack Cost" : "Cost/Item"}
              </label>
              <input
                type="number"
                min={0}
                value={groupCreditMode === "per_pack" ? groupCreditCost : groupCreditPerItem}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (groupCreditMode === "per_pack") setGroupCreditCost(v);
                  else setGroupCreditPerItem(v);
                }}
                style={input}
              />
            </div>
            <div style={{ flex: "0 0 160px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Bot</label>
              <select value={groupBotId} onChange={(e) => setGroupBotId(Number(e.target.value))} style={select_}>
                {bots.map((b) => (
                  <option key={b.id} value={b.id}>@{b.bot_username}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: "0 0 180px" }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Thumbnail</label>
              <ThumbSelector
                value={groupThumbId}
                onChange={setGroupThumbId}
                onUpload={(file) => handleGroupThumb(file)}
              />
            </div>
          </div>
        </div>
      )}

      {/* ── Video Table ── */}
      {videos.length > 0 && (
        <div style={{ ...card, overflowX: "auto" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
            <h3 style={{ margin: 0 }}>
              Files ({readyVideos.length} ready / {videos.length} total)
            </h3>
            {mode === "solo" && readyVideos.length > 1 && (
              <div style={{ display: "flex", gap: 8 }}>
                <select
                  onChange={(e) => { if (e.target.value) applyToAll("access_type", e.target.value); e.target.value = ""; }}
                  style={{ ...select_, width: 150 }}
                >
                  <option value="">Set all categories…</option>
                  {categories.map((c) => (
                    <option key={c.tag} value={c.tag}>{c.label}</option>
                  ))}
                </select>
                <select
                  onChange={(e) => { if (e.target.value) applyToAll("upload_bot_id", Number(e.target.value)); e.target.value = ""; }}
                  style={{ ...select_, width: 155 }}
                >
                  <option value="">Set all upload bots…</option>
                  {bots.map((b) => (
                    <option key={b.id} value={b.id}>@{b.bot_username}</option>
                  ))}
                </select>
                <select
                  onChange={(e) => { if (e.target.value) applyToAll("bot_id", Number(e.target.value)); e.target.value = ""; }}
                  style={{ ...select_, width: 160 }}
                >
                  <option value="">Set all delivery bots…</option>
                  {bots.map((b) => (
                    <option key={b.id} value={b.id}>@{b.bot_username}</option>
                  ))}
                </select>
                {defaultThumbs.length > 0 && (
                  <select
                    onChange={(e) => { if (e.target.value) applyToAll("thumbnail_file_id", e.target.value); e.target.value = ""; }}
                    style={{ ...select_, width: 150 }}
                  >
                    <option value="">Set all thumbnails…</option>
                    {defaultThumbs.map((t) => (
                      <option key={t.id} value={t.file_id}>{t.name}</option>
                    ))}
                  </select>
                )}
              </div>
            )}
          </div>

          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>#</th>
                <th style={thStyle}>Filename</th>
                {mode === "solo" && (
                  <>
                    <th style={thStyle}>Title</th>
                    <th style={thStyle}>Category</th>
                    <th style={thStyle}>Credit Mode</th>
                    <th style={thStyle}>Cost</th>
                    <th style={thStyle}>Upload Bot</th>
                    <th style={thStyle}>Delivery Bot</th>
                    <th style={thStyle}>Thumbnail</th>
                  </>
                )}
                <th style={thStyle}>Status</th>
                <th style={thStyle}></th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v, i) => (
                <tr key={v.id} style={{ background: v.error ? "#fff5f5" : undefined }}>
                  <td style={tdStyle}>{i + 1}</td>
                  <td style={{ ...tdStyle, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {v.filename}
                  </td>

                  {mode === "solo" && (
                    <>
                      <td style={tdStyle}>
                        <input
                          value={v.title}
                          onChange={(e) => updateVideo(v.id, { title: e.target.value })}
                          style={{ ...input, minWidth: 120 }}
                        />
                      </td>
                      <td style={tdStyle}>
                        <select
                          value={v.access_type}
                          onChange={(e) => updateVideo(v.id, { access_type: e.target.value })}
                          style={{ ...select_, minWidth: 100 }}
                        >
                          {categories.map((c) => (
                            <option key={c.tag} value={c.tag}>{c.label}</option>
                          ))}
                        </select>
                      </td>
                      <td style={tdStyle}>
                        <select
                          value={v.credit_mode}
                          onChange={(e) => updateVideo(v.id, { credit_mode: e.target.value })}
                          style={{ ...select_, minWidth: 100 }}
                        >
                          <option value="per_item">Per Item</option>
                          <option value="per_pack">Per Pack</option>
                        </select>
                      </td>
                      <td style={tdStyle}>
                        <input
                          type="number"
                          min={0}
                          value={v.credit_mode === "per_pack" ? v.credit_cost : v.credit_per_item}
                          onChange={(e) => {
                            const val = Number(e.target.value);
                            if (v.credit_mode === "per_pack") updateVideo(v.id, { credit_cost: val });
                            else updateVideo(v.id, { credit_per_item: val });
                          }}
                          style={{ ...input, width: 70 }}
                        />
                      </td>
                      <td style={tdStyle}>
                        <select
                          value={v.upload_bot_id}
                          onChange={(e) => updateVideo(v.id, { upload_bot_id: Number(e.target.value) })}
                          style={{ ...select_, minWidth: 110 }}
                          disabled={v.uploaded}
                          title={v.uploaded ? "Already uploaded" : "Bot used to upload to storage"}
                        >
                          <option value={0}>Auto</option>
                          {bots.map((b) => (
                            <option key={b.id} value={b.id}>@{b.bot_username}</option>
                          ))}
                        </select>
                      </td>
                      <td style={tdStyle}>
                        <select
                          value={v.bot_id}
                          onChange={(e) => updateVideo(v.id, { bot_id: Number(e.target.value) })}
                          style={{ ...select_, minWidth: 110 }}
                        >
                          {bots.map((b) => (
                            <option key={b.id} value={b.id}>@{b.bot_username}</option>
                          ))}
                        </select>
                        {v.uploaded && v.upload_bot_id > 0 && v.upload_bot_id === v.bot_id && (
                          <span style={{ fontSize: 10, color: "#2d7a3a" }} title="Same bot = instant copy_message">⚡</span>
                        )}
                        {v.uploaded && v.upload_bot_id > 0 && v.upload_bot_id !== v.bot_id && (
                          <span style={{ fontSize: 10, color: "#b8860b" }} title="Different bots = proxy (slower)">🐢</span>
                        )}
                      </td>
                      <td style={tdStyle}>
                        <ThumbSelector
                          value={v.thumbnail_file_id || ""}
                          onChange={(fid) => updateVideo(v.id, { thumbnail_file_id: fid || undefined })}
                          onUpload={(file) => handleThumbUpload(v.id, file)}
                        />
                      </td>
                    </>
                  )}

                  <td style={tdStyle}>
                    {v.uploading && <span style={{ color: "#f39c12" }}>⏳ Uploading…</span>}
                    {v.error && (
                      <span style={{ color: "#e74c3c", cursor: "help" }} title={v.error}>
                        ❌ {v.error.length > 30 ? v.error.slice(0, 30) + "…" : v.error}
                      </span>
                    )}
                    {!v.uploading && !v.error && v.uploaded && v.storage_message_id > 0 && (
                      <span style={{ color: "#2ecc71" }}>
                        ✅ {v.media_type === "video" ? "🎬" : v.media_type === "photo" ? "🖼️" : v.media_type === "animation" ? "🎞️" : "📄"} Ready
                      </span>
                    )}
                    {!v.uploading && !v.error && !v.uploaded && (
                      <span style={{ color: "#888" }}>📂 Staged</span>
                    )}
                  </td>

                  <td style={tdStyle}>
                    <button onClick={() => removeVideo(v.id)} style={{ ...btnDanger, padding: "4px 10px", fontSize: 12 }}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Publish Bar ── */}
      {readyVideos.length > 0 && !publishing && (
        <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 600 }}>
            {readyVideos.length} file{readyVideos.length > 1 ? "s" : ""} ready to publish
            {mode === "group" ? " (as 1 group pack)" : ` (as ${readyVideos.length} solo packs)`}
            {ratePerMinute === 0 ? " — ⚡ all at once" : ` — ${ratePerMinute}/min`}
          </span>
          <button onClick={handlePublish} style={{ ...btnSuccess, padding: "10px 28px", fontSize: 16 }}>
            🚀 Publish{activeJobs.length > 0 ? ` (Job #${activeJobs.length + 1})` : ""}
          </button>
        </div>
      )}
      {publishing && videos.length > 0 && (
        <div style={card}>
          <p style={{ color: "#888", margin: 0 }}>⏳ Starting publish job…</p>
        </div>
      )}

    </>
  );
}
