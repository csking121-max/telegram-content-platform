import { useCallback, useEffect, useRef, useState } from "react";
import {
  uploadVideo,
  uploadThumbnail,
  getFactoryCategories,
  getActiveBots,
  publishContent,
  getPublishJob,
} from "../api/endpoints";
import type {
  Bot,
  ContentCategory,
  PublishJob,
  UploadedVideo,
} from "../types";

/* ── helpers ───────────────────────────────────────────── */

let _idCounter = 0;
const uid = () => `v_${++_idCounter}_${Date.now()}`;

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
  const [videos, setVideos] = useState<UploadedVideo[]>([]);
  const [categories, setCategories] = useState<ContentCategory[]>([]);
  const [bots, setBots] = useState<Bot[]>([]);
  const [mode, setMode] = useState<"solo" | "group">("solo");
  const [dragging, setDragging] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [activeJob, setActiveJob] = useState<PublishJob | null>(null);
  const [ratePerMinute, setRatePerMinute] = useState(2);
  const [deletionSeconds, setDeletionSeconds] = useState(0);
  const fileRef = useRef<HTMLInputElement>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Group mode settings
  const [groupTitle, setGroupTitle] = useState("Content Pack");
  const [groupCategory, setGroupCategory] = useState("free");
  const [groupCreditCost, setGroupCreditCost] = useState(0);
  const [groupCreditMode, setGroupCreditMode] = useState("per_item");
  const [groupCreditPerItem, setGroupCreditPerItem] = useState(1);
  const [groupBotId, setGroupBotId] = useState(0);
  const [groupThumbId, setGroupThumbId] = useState("");

  // Load categories and bots
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
        if (b.length > 0) setGroupBotId(b[0].id);
      })
      .catch(() => setBots([]));
  }, []);

  // Clean up poll on unmount
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  /* ── file handling ──────────────────────────────── */

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const defaultBotId = bots.length > 0 ? bots[0].id : 0;
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
          storage_chat_id: 0,
          storage_message_id: 0,
          file_id: "",
          media_type: mt,
          title: file.name.replace(/\.[^.]+$/, ""),
          access_type: "free",
          credit_cost: 0,
          credit_mode: "per_item",
          credit_per_item: 1,
          bot_id: defaultBotId,
          uploading: true,
        };
        newVideos.push(v);
      }

      setVideos((prev) => [...prev, ...newVideos]);

      // Upload each file sequentially to avoid overwhelming Telegram
      const fileArr = Array.from(files);
      for (let i = 0; i < fileArr.length; i++) {
        const v = newVideos[i];
        try {
          const result = await uploadVideo(fileArr[i]);
          setVideos((prev) =>
            prev.map((x) =>
              x.id === v.id
                ? {
                    ...x,
                    storage_chat_id: result.storage_chat_id,
                    storage_message_id: result.storage_message_id,
                    file_id: result.file_id,
                    duration: result.duration,
                    width: result.width,
                    height: result.height,
                    uploading: false,
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
    },
    [bots],
  );

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

  /* ── apply-to-all ───────────────────────────────── */

  const applyToAll = (field: keyof UploadedVideo, value: unknown) => {
    setVideos((prev) => prev.map((v) => ({ ...v, [field]: value })));
  };

  /* ── publish ────────────────────────────────────── */

  const readyVideos = videos.filter((v) => !v.uploading && !v.error && v.storage_message_id > 0);

  const handlePublish = async () => {
    if (readyVideos.length === 0) return;
    setPublishing(true);
    setActiveJob(null);

    try {
      const items = readyVideos.map((v) => ({
        storage_chat_id: v.storage_chat_id,
        storage_message_id: v.storage_message_id,
        media_type: v.media_type,
        title: v.title,
        access_type: mode === "group" ? groupCategory : v.access_type,
        credit_cost: mode === "group" ? groupCreditCost : v.credit_cost,
        credit_mode: mode === "group" ? groupCreditMode : v.credit_mode,
        credit_per_item: mode === "group" ? groupCreditPerItem : v.credit_per_item,
        bot_id: mode === "group" ? groupBotId : v.bot_id,
        thumbnail_file_id: mode === "group" ? groupThumbId || null : v.thumbnail_file_id || null,
      }));

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

      const { job_id } = await publishContent(payload);

      // Poll for job status
      pollRef.current = setInterval(async () => {
        try {
          const job = await getPublishJob(job_id);
          setActiveJob(job);
          if (job.status === "completed" || job.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setPublishing(false);
          }
        } catch {
          /* ignore polling errors */
        }
      }, 2000);
    } catch (err: unknown) {
      alert("Publish failed: " + (err instanceof Error ? err.message : err));
      setPublishing(false);
    }
  };

  /* ── render ─────────────────────────────────────── */

  return (
    <>
      <h1 style={{ marginBottom: 8 }}>🏭 Content Factory</h1>
      <p style={{ color: "#666", marginTop: 0, marginBottom: 20 }}>
        Upload, configure, and bulk-publish content to Telegram.
      </p>

      {/* ── Upload Zone ── */}
      <div style={card}>
        <h3 style={{ margin: "0 0 12px" }}>Upload Videos</h3>
        <div
          style={dragging ? dropZoneActive : dropZone}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          onClick={() => fileRef.current?.click()}
        >
          <p style={{ fontSize: 16, margin: 0 }}>
            {dragging ? "Drop videos here…" : "📁 Drag & drop videos here, or click to browse"}
          </p>
          <p style={{ fontSize: 12, color: "#888", margin: "8px 0 0" }}>
            Supports MP4, MKV, AVI, MOV — max 50 MB per file
          </p>
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="video/*"
          multiple
          style={{ display: "none" }}
          onChange={onFileInput}
        />
      </div>

      {/* ── Mode & Settings ── */}
      {videos.length > 0 && (
        <div style={card}>
          <div style={{ display: "flex", gap: 24, alignItems: "center", flexWrap: "wrap" }}>
            <div>
              <label style={{ fontWeight: 600, fontSize: 14 }}>Mode: </label>
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as "solo" | "group")}
                style={{ ...select_, width: 200 }}
              >
                <option value="solo">Solo — Each video gets its own deep link</option>
                <option value="group">Group — All videos share one deep link</option>
              </select>
            </div>
            <div>
              <label style={{ fontWeight: 600, fontSize: 14 }}>Publish Rate: </label>
              <select
                value={ratePerMinute}
                onChange={(e) => setRatePerMinute(Number(e.target.value))}
                style={{ ...select_, width: 160 }}
              >
                <option value={1}>1 per minute</option>
                <option value={2}>2 per minute</option>
                <option value={3}>3 per minute</option>
                <option value={5}>5 per minute</option>
                <option value={10}>10 per minute</option>
              </select>
            </div>
            <div>
              <label style={{ fontWeight: 600, fontSize: 14 }}>Auto-Delete (sec): </label>
              <input
                type="number"
                min={0}
                value={deletionSeconds}
                onChange={(e) => setDeletionSeconds(Number(e.target.value))}
                style={{ ...input, width: 80 }}
                placeholder="0 = never"
              />
            </div>
          </div>

          {/* ── Group Mode Settings ── */}
          {mode === "group" && (
            <div
              style={{
                marginTop: 16,
                padding: 16,
                background: "#f0f7ff",
                borderRadius: 8,
                border: "1px solid #c5dcf5",
              }}
            >
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
                <div style={{ flex: "0 0 140px" }}>
                  <label style={{ display: "block", fontSize: 12, fontWeight: 600, marginBottom: 4 }}>Thumbnail</label>
                  {groupThumbId ? (
                    <span style={{ fontSize: 12, color: "#2ecc71" }}>
                      ✅ Uploaded{" "}
                      <button
                        onClick={() => setGroupThumbId("")}
                        style={{ ...btn, padding: "2px 8px", fontSize: 11, background: "#eee" }}
                      >
                        Clear
                      </button>
                    </span>
                  ) : (
                    <label style={{ ...btn, padding: "6px 10px", fontSize: 12, background: "#eee", display: "inline-block" }}>
                      Choose…
                      <input
                        type="file"
                        accept="image/*"
                        style={{ display: "none" }}
                        onChange={(e) => { if (e.target.files?.[0]) handleGroupThumb(e.target.files[0]); }}
                      />
                    </label>
                  )}
                </div>
              </div>
            </div>
          )}
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
                  onChange={(e) => { if (e.target.value) applyToAll("bot_id", Number(e.target.value)); e.target.value = ""; }}
                  style={{ ...select_, width: 140 }}
                >
                  <option value="">Set all bots…</option>
                  {bots.map((b) => (
                    <option key={b.id} value={b.id}>@{b.bot_username}</option>
                  ))}
                </select>
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
                    <th style={thStyle}>Bot</th>
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
                      {/* Title */}
                      <td style={tdStyle}>
                        <input
                          value={v.title}
                          onChange={(e) => updateVideo(v.id, { title: e.target.value })}
                          style={{ ...input, minWidth: 120 }}
                        />
                      </td>
                      {/* Category */}
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
                      {/* Credit Mode */}
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
                      {/* Cost */}
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
                      {/* Bot */}
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
                      </td>
                      {/* Thumbnail */}
                      <td style={tdStyle}>
                        {v.thumbnail_file_id ? (
                          <span style={{ color: "#2ecc71", fontSize: 12 }}>
                            ✅{" "}
                            <button
                              onClick={() => updateVideo(v.id, { thumbnail_file_id: undefined })}
                              style={{ ...btn, padding: "1px 6px", fontSize: 11, background: "#eee" }}
                            >
                              ✕
                            </button>
                          </span>
                        ) : (
                          <label style={{ ...btn, padding: "4px 8px", fontSize: 11, background: "#f0f0f0", display: "inline-block" }}>
                            Upload
                            <input
                              type="file"
                              accept="image/*"
                              style={{ display: "none" }}
                              onChange={(e) => { if (e.target.files?.[0]) handleThumbUpload(v.id, e.target.files[0]); }}
                            />
                          </label>
                        )}
                      </td>
                    </>
                  )}

                  {/* Status */}
                  <td style={tdStyle}>
                    {v.uploading && <span style={{ color: "#f39c12" }}>⏳ Uploading…</span>}
                    {v.error && (
                      <span style={{ color: "#e74c3c", cursor: "help" }} title={v.error}>
                        ❌ {v.error.length > 30 ? v.error.slice(0, 30) + "…" : v.error}
                      </span>
                    )}
                    {!v.uploading && !v.error && v.storage_message_id > 0 && (
                      <span style={{ color: "#2ecc71" }}>
                        ✅ {v.media_type === "video" ? "🎬" : v.media_type === "photo" ? "🖼️" : v.media_type === "animation" ? "🎞️" : "📄"} Ready
                      </span>
                    )}
                  </td>

                  {/* Remove */}
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
      {readyVideos.length > 0 && !publishing && !activeJob && (
        <div style={{ ...card, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <span style={{ fontWeight: 600 }}>
            {readyVideos.length} file{readyVideos.length > 1 ? "s" : ""} ready to publish
            {mode === "group" ? " (as 1 group pack)" : ` (as ${readyVideos.length} solo packs)`}
          </span>
          <button onClick={handlePublish} style={{ ...btnSuccess, padding: "10px 28px", fontSize: 16 }}>
            🚀 Publish All
          </button>
        </div>
      )}

      {/* ── Job Progress ── */}
      {(publishing || activeJob) && (
        <div style={card}>
          <h3 style={{ margin: "0 0 12px" }}>
            {activeJob?.status === "completed"
              ? "✅ Publishing Complete"
              : activeJob?.status === "failed"
                ? "❌ Publishing Failed"
                : "⏳ Publishing in Progress…"}
          </h3>

          {activeJob && (
            <>
              {/* Progress bar */}
              <div style={{ background: "#eee", borderRadius: 6, height: 24, marginBottom: 12, overflow: "hidden" }}>
                <div
                  style={{
                    height: "100%",
                    borderRadius: 6,
                    background: activeJob.failed > 0 ? "#f39c12" : "#2ecc71",
                    width: `${Math.round(((activeJob.completed + activeJob.failed) / Math.max(activeJob.total, 1)) * 100)}%`,
                    transition: "width .3s",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 12,
                    fontWeight: 700,
                    color: "#fff",
                  }}
                >
                  {activeJob.completed + activeJob.failed} / {activeJob.total}
                </div>
              </div>

              <div style={{ display: "flex", gap: 24, fontSize: 14 }}>
                <span>✅ Completed: {activeJob.completed}</span>
                <span>❌ Failed: {activeJob.failed}</span>
                <span>📊 Total: {activeJob.total}</span>
              </div>

              {/* Results */}
              {activeJob.results.length > 0 && (
                <div style={{ marginTop: 16, maxHeight: 300, overflowY: "auto" }}>
                  <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                    <thead>
                      <tr>
                        <th style={thStyle}>Title</th>
                        <th style={thStyle}>Pack ID</th>
                        <th style={thStyle}>Deep Link</th>
                        <th style={thStyle}>Channel</th>
                      </tr>
                    </thead>
                    <tbody>
                      {activeJob.results.map((r, i) => (
                        <tr key={i}>
                          <td style={tdStyle}>{r.title || r.error || "—"}</td>
                          <td style={tdStyle}>{r.pack_id ?? "—"}</td>
                          <td style={tdStyle}>
                            {r.deep_link ? (
                              <button
                                onClick={() => { navigator.clipboard.writeText(r.deep_link!); }}
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
              )}

              {/* Reset button when done */}
              {(activeJob.status === "completed" || activeJob.status === "failed") && (
                <div style={{ marginTop: 16 }}>
                  <button
                    onClick={() => { setActiveJob(null); setPublishing(false); setVideos([]); }}
                    style={btnPrimary}
                  >
                    Start New Batch
                  </button>
                </div>
              )}
            </>
          )}

          {!activeJob && publishing && (
            <p style={{ color: "#888" }}>Starting publish job…</p>
          )}
        </div>
      )}
    </>
  );
}
