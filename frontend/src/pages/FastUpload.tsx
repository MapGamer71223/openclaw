import React, { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";

const ACCEPTED = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"];

function UploadIcon() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
      <path d="M12 3v12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M7 8l5-5 5 5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 16v2.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V16" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export function FastUpload() {
  const navigate = useNavigate();
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ name: string; url: string | null } | null>(null);

  const handleFile = useCallback(
    async (file: File) => {
      setError(null);
      setPreview({
        name: file.name,
        url: file.type.startsWith("image/") ? URL.createObjectURL(file) : null,
      });
      setUploading(true);
      try {
        const inv = await api.upload(file);
        await api.startFast(inv.id);
        navigate(`/check/${inv.id}`);
      } catch (e: any) {
        setError(e.message || "Upload failed");
        setUploading(false);
      }
    },
    [navigate]
  );

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="p-8 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-forensic-text mb-1 tracking-tight">Is This AI-Generated?</h1>
      <p className="text-sm text-forensic-muted mb-8">
        Upload an image or video. We'll check if it's AI-generated, and if so, try to find where it was first posted.
      </p>

      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={`evidence-corners relative overflow-hidden panel border-2 border-dashed rounded-xl p-16 text-center transition-colors ${
          dragOver ? "border-forensic-accent bg-forensic-accent/5" : "border-forensic-border"
        }`}
        style={{ ["--corner-color" as any]: dragOver ? "#3ddc97" : "#6b7789" }}
      >
        {uploading && <div className="scan-sweep" />}

        {preview?.url ? (
          <img src={preview.url} alt="" className="mx-auto mb-5 max-h-40 rounded-lg border border-forensic-border object-contain" />
        ) : (
          <div className={`mx-auto mb-4 w-16 h-16 rounded-full border flex items-center justify-center transition-colors ${
            dragOver ? "border-forensic-accent text-forensic-accent" : "border-forensic-border text-forensic-muted"
          }`}>
            <UploadIcon />
          </div>
        )}

        <div className="text-lg font-semibold text-forensic-text mb-2">
          {uploading ? `Uploading ${preview?.name ?? "file"}…` : "Upload Image / Video"}
        </div>
        <div className="text-xs text-forensic-muted mono mb-6">Supported: JPG JPEG PNG WEBP MP4 MOV</div>
        <label className={`inline-block px-5 py-2.5 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm transition ${
          uploading ? "opacity-50 cursor-not-allowed" : "cursor-pointer hover:brightness-110"
        }`}>
          {uploading ? "Working…" : "Choose File"}
          <input
            type="file"
            accept={ACCEPTED.join(",")}
            className="hidden"
            disabled={uploading}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
          />
        </label>
      </div>

      {error && (
        <div className="mt-4 p-3 rounded-lg bg-forensic-danger/10 border border-forensic-danger/30 text-forensic-danger text-sm">
          {error}
        </div>
      )}
    </div>
  );
}
