import type {
  ChangeRecord,
  Component,
  ProjectReport,
  ProjectSummary,
  Recommendation,
  TestCase,
} from "../types/kb";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${init?.method ?? "GET"} ${path} failed: ${res.status} ${body}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  createProjectFromGithub: (githubUrl: string, ref?: string) =>
    request<ProjectSummary>("/projects", {
      method: "POST",
      body: JSON.stringify({ github_url: githubUrl, ref: ref ?? null }),
    }),

  uploadProjectZip: async (file: File): Promise<ProjectSummary> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/projects/upload", { method: "POST", body: form });
    if (!res.ok) throw new Error(`upload failed: ${res.status} ${await res.text()}`);
    return res.json();
  },

  listComponents: (projectId: string) => request<Component[]>(`/projects/${projectId}/components`),
  listTests: (projectId: string) => request<TestCase[]>(`/projects/${projectId}/tests`),
  listChanges: (projectId: string) => request<ChangeRecord[]>(`/projects/${projectId}/changes`),
  listRecommendations: (projectId: string) =>
    request<Recommendation[]>(`/projects/${projectId}/recommendations`),
  getReport: (projectId: string) => request<ProjectReport>(`/projects/${projectId}/report`),

  classify: (projectId: string, provider?: string) =>
    request<Recommendation[]>(`/projects/${projectId}/classify`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),
  apply: (projectId: string, provider?: string) =>
    request<Recommendation[]>(`/projects/${projectId}/apply`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),
  detectChanges: (projectId: string) =>
    request<ChangeRecord[]>(`/projects/${projectId}/detect-changes`, { method: "POST" }),
};
