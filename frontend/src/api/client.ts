import type {
  ChangeRecord,
  Component,
  DeploymentIssue,
  Job,
  PerformanceRisk,
  PredictedRisk,
  ProjectReport,
  ProjectSummary,
  Recommendation,
  RiskAssessment,
  TestCase,
} from "../types/kb";

async function extractErrorDetail(res: Response): Promise<string> {
  const text = await res.text();
  try {
    const parsed = JSON.parse(text);
    if (typeof parsed?.detail === "string") return parsed.detail;
  } catch {
    // not JSON — fall through to raw text
  }
  return text;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    throw new Error(await extractErrorDetail(res));
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
    if (!res.ok) throw new Error(await extractErrorDetail(res));
    return res.json();
  },

  listComponents: (projectId: string) => request<Component[]>(`/projects/${projectId}/components`),
  listTests: (projectId: string) => request<TestCase[]>(`/projects/${projectId}/tests`),
  listChanges: (projectId: string) => request<ChangeRecord[]>(`/projects/${projectId}/changes`),
  listRecommendations: (projectId: string) =>
    request<Recommendation[]>(`/projects/${projectId}/recommendations`),
  getReport: (projectId: string) => request<ProjectReport>(`/projects/${projectId}/report`),
  downloadUrl: (projectId: string) => `/projects/${projectId}/download`,

  // Classify and apply are one LLM call per component and can run for
  // minutes, so the API starts a background job and we poll it rather than
  // holding a request open long enough for a proxy to time it out.
  classify: (projectId: string, provider?: string) =>
    request<Job>(`/projects/${projectId}/classify`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null }),
    }),
  apply: (projectId: string, provider?: string, companyId?: string) =>
    request<Job>(`/projects/${projectId}/apply`, {
      method: "POST",
      body: JSON.stringify({ provider: provider ?? null, company_id: companyId ?? null }),
    }),
  getJob: (jobId: string) => request<Job>(`/jobs/${jobId}`),
  detectChanges: (projectId: string) =>
    request<ChangeRecord[]>(`/projects/${projectId}/detect-changes`, { method: "POST" }),

  assessRisks: (projectId: string, companyId?: string) =>
    request<RiskAssessment>(`/projects/${projectId}/assess-risks`, {
      method: "POST",
      body: JSON.stringify({ company_id: companyId ?? null }),
    }),
  listDeploymentIssues: (projectId: string) =>
    request<DeploymentIssue[]>(`/projects/${projectId}/deployment-issues`),
  listPerformanceRisks: (projectId: string) =>
    request<PerformanceRisk[]>(`/projects/${projectId}/performance-risks`),
  listPredictedRisks: (projectId: string) =>
    request<PredictedRisk[]>(`/projects/${projectId}/predicted-risks`),
};
