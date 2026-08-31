import type { RiskAssessment } from "../types/kb";

const SEVERITY_COLORS: Record<"low" | "medium" | "high", string> = {
  high: "#c62828",
  medium: "#ed6c02",
  low: "#757575",
};

function SeverityBadge({ severity }: { severity: "low" | "medium" | "high" }) {
  return (
    <span className="severity-badge" style={{ backgroundColor: SEVERITY_COLORS[severity] }}>
      {severity.toUpperCase()}
    </span>
  );
}

export function RiskPanel({ assessment }: { assessment: RiskAssessment | null }) {
  if (assessment === null) {
    return <p className="muted">No risk assessment yet — run Assess Risks.</p>;
  }

  const total =
    assessment.deployment_issues.length + assessment.performance_risks.length + assessment.predicted_risks.length;

  if (total === 0) {
    return <p className="muted">No deployment, performance, or predicted risks found.</p>;
  }

  return (
    <div className="risk-panel">
      {assessment.deployment_issues.length > 0 && (
        <div className="risk-group">
          <h3>Deployment readiness ({assessment.deployment_issues.length})</h3>
          <ul className="risk-list">
            {assessment.deployment_issues.map((issue) => (
              <li key={issue.id}>
                <SeverityBadge severity={issue.severity} />
                <span className="risk-location">
                  {issue.file_path ?? ""}
                  {issue.line ? `:${issue.line}` : ""}
                </span>
                <span className="risk-message">{issue.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {assessment.performance_risks.length > 0 && (
        <div className="risk-group">
          <h3>Performance risks ({assessment.performance_risks.length})</h3>
          <ul className="risk-list">
            {assessment.performance_risks.map((risk) => (
              <li key={risk.id}>
                <SeverityBadge severity={risk.severity} />
                <span className="risk-location">{risk.component_id}</span>
                <span className="risk-message">{risk.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {assessment.predicted_risks.length > 0 && (
        <div className="risk-group">
          <h3>Predicted risks ({assessment.predicted_risks.length})</h3>
          <ul className="risk-list">
            {assessment.predicted_risks.map((risk) => (
              <li key={risk.id}>
                <SeverityBadge severity={risk.severity} />
                <span className="risk-location">{risk.component_id}</span>
                <span className="risk-message">{risk.message}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
