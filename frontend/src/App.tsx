import { useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { UploadPage } from "./pages/UploadPage";
import type { ProjectSummary } from "./types/kb";

export function App() {
  const [summary, setSummary] = useState<ProjectSummary | null>(null);

  return summary ? <DashboardPage summary={summary} /> : <UploadPage onAnalyzed={setSummary} />;
}
