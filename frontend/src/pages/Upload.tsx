import React, { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { UploadCloud, ImageIcon, X, Sparkles, ScanSearch, AlertCircle } from "lucide-react";
import { api } from "../services/api";
import { SectionHeader } from "../components/ui";

const ACCEPTED = [".jpg", ".jpeg", ".png", ".webp", ".mp4", ".mov"];

export function Upload() {
  const navigate = useNavigate();
  const [dragOver, setDragOver] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [seedingDemo, setSeedingDemo] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) { setPreviewUrl(null); return; }
    if (!file.type.startsWith("image/")) { setPreviewUrl(null); return; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const selectFile = useCallback((f: File) => {
    setError(null);
    setFile(f);
  }, []);

  const startInvestigation = useCallback(async () => {
    if (!file) return;
    setError(null);
    setUploading(true);
    try {
      const inv = await api.upload(file);
      await api.start(inv.id);
      navigate(`/investigations/${inv.id}`);
    } catch (e: any) {
      setError(e.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  }, [file, navigate]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) selectFile(f);
  };

  const onSeedDemo = async () => {
    setSeedingDemo(true);
    setError(null);
    try {
      const inv = await api.seedDemo();
      navigate(`/investigations/${inv.id}`);
    } catch (e: any) {
      setError(e.message || "Demo seed failed");
    } finally {
      setSeedingDemo(false);
    }
  };

  return (
    <div className="p-5 sm:p-8 max-w-3xl mx-auto">
      <SectionHeader
        eyebrow="Investigate"
        title="Start a Media Investigation"
        subtitle="Upload an image or video and let the forensic pipeline analyze authenticity, manipulation signals, and web origins."
      />

      {!file ? (
        <div
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={`relative panel overflow-hidden border-2 border-dashed rounded-xl p-12 sm:p-16 text-center transition-colors ${
            dragOver ? "border-forensic-accent bg-forensic-accent/5" : "border-forensic-border"
          }`}
        >
          <div className="absolute inset-0 grid-texture pointer-events-none" />
          <div className="relative">
            <div className={`w-14 h-14 mx-auto rounded-xl flex items-center justify-center mb-5 border transition-colors ${
              dragOver ? "bg-forensic-accent/15 border-forensic-accent/40 text-forensic-accent" : "bg-forensic-panel3 border-forensic-border text-forensic-muted"
            }`}>
              <UploadCloud size={26} strokeWidth={1.75} />
            </div>
            <div className="text-lg font-semibold text-forensic-text mb-2">Drop Image or Video Here</div>
            <div className="text-xs text-forensic-muted mono mb-1">Supported: JPG · PNG · WEBP · MP4 · MOV</div>
            <div className="text-xs text-forensic-muted mono mb-7">Maximum file size: 100MB</div>
            <label className="inline-block px-5 py-2.5 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm cursor-pointer hover:brightness-110 transition shadow-glow">
              Choose File
              <input
                type="file"
                accept={ACCEPTED.join(",")}
                className="hidden"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) selectFile(f); }}
              />
            </label>
          </div>
        </div>
      ) : (
        <div className="panel p-5 animate-scaleIn">
          <div className="flex items-start gap-4">
            <div className="w-24 h-24 rounded-lg border border-forensic-border overflow-hidden flex-shrink-0 bg-forensic-panel3 flex items-center justify-center">
              {previewUrl ? (
                <img src={previewUrl} alt="Selected media preview" className="w-full h-full object-cover" />
              ) : (
                <ImageIcon size={24} className="text-forensic-muted" />
              )}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold text-forensic-text truncate">{file.name}</div>
              <div className="text-xs text-forensic-muted mono mt-1">
                {(file.size / 1024 / 1024).toFixed(2)} MB · {file.type || "unknown type"}
              </div>
              {!uploading && (
                <button
                  onClick={() => setFile(null)}
                  className="inline-flex items-center gap-1 text-xs text-forensic-muted hover:text-forensic-danger mt-3 transition-colors focus-ring"
                >
                  <X size={13} /> Remove
                </button>
              )}
            </div>
          </div>

          <button
            onClick={startInvestigation}
            disabled={uploading}
            className="w-full mt-5 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-lg bg-forensic-accent text-forensic-bg font-semibold text-sm hover:brightness-110 transition disabled:opacity-60 shadow-glow"
          >
            <ScanSearch size={16} />
            {uploading ? "Uploading evidence…" : "Start Investigation"}
          </button>
        </div>
      )}

      {error && (
        <div className="mt-4 flex items-start gap-2 p-3 rounded-lg bg-forensic-danger/10 border border-forensic-danger/30 text-forensic-danger text-sm animate-slideUp">
          <AlertCircle size={16} className="flex-shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      <div className="mt-8 panel p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-lg bg-forensic-violet/10 border border-forensic-violet/30 flex items-center justify-center text-forensic-violet flex-shrink-0">
            <Sparkles size={16} />
          </div>
          <div>
            <div className="text-sm font-semibold text-forensic-text">No sample media on hand?</div>
            <div className="text-xs text-forensic-muted mt-0.5 max-w-md">
              Run the bundled offline demo investigation — real forensic analysis on a generated sample, no API keys required.
            </div>
          </div>
        </div>
        <button
          onClick={onSeedDemo}
          disabled={seedingDemo}
          className="px-4 py-2 rounded-lg border border-forensic-violet/40 text-forensic-violet text-sm font-semibold hover:bg-forensic-violet/10 transition flex-shrink-0 disabled:opacity-60"
        >
          {seedingDemo ? "Running…" : "Run Demo Investigation"}
        </button>
      </div>
    </div>
  );
}
