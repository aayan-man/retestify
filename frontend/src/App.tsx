import { useState } from "react";
import { DashboardPage } from "./pages/DashboardPage";
import { UploadPage } from "./pages/UploadPage";
import type { ProjectSummary } from "./types/kb";

export function App() {
  const [summary, setSummary] = useState<ProjectSummary | null>(null);

  // Clearing the summary returns to the upload page. The project itself is
  // untouched on the server, so this is a navigation, not a deletion.
  return summary ? (
    <DashboardPage summary={summary} onBack={() => setSummary(null)} />
  ) : (
    <UploadPage onAnalyzed={setSummary} />
  );
}
