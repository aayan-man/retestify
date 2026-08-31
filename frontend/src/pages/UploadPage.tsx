import { useState } from "react";
import { api } from "../api/client";
import type { ProjectSummary } from "../types/kb";

interface Props {
  onAnalyzed: (summary: ProjectSummary) => void;
}

export function UploadPage({ onAnalyzed }: Props) {
  const [githubUrl, setGithubUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleGithubSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onAnalyzed(await api.createProjectFromGithub(githubUrl));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onAnalyzed(await api.uploadProjectZip(file));
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="upload-page">
      <h1>AI-Driven Test Case Management</h1>
      <p className="muted">Ingest a target repository to analyze its source and test coverage.</p>

      <form onSubmit={handleGithubSubmit} className="upload-form">
        <label htmlFor="github-url">GitHub repository URL</label>
        <input
          id="github-url"
          type="text"
          value={githubUrl}
          onChange={(e) => setGithubUrl(e.target.value)}
          placeholder="https://github.com/owner/repo"
          required
        />
        <button type="submit" disabled={busy || !githubUrl}>
          {busy ? "Analyzing..." : "Analyze from GitHub"}
        </button>
      </form>

      <div className="upload-divider">or</div>

      <label htmlFor="zip-upload" className="upload-form">
        Upload a .zip file
        <input id="zip-upload" type="file" accept=".zip" onChange={handleFileChange} disabled={busy} />
      </label>

      {error && <p className="error">{error}</p>}
    </div>
  );
}
