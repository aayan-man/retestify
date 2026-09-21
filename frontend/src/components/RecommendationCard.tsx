import type { Recommendation } from "../types/kb";

const DECISION_COLORS: Record<Recommendation["decision"], string> = {
  retain: "#2e7d32",
  modify: "#ed6c02",
  remove: "#c62828",
  generate: "#1565c0",
};

// Only statuses worth calling out on the card. "pending_review" is the
// resting state and would just be noise on every row.
const STATUS_LABELS: Partial<Record<Recommendation["status"], string>> = {
  applied: "applied",
  failed: "failed",
  rejected: "rejected",
};

interface Props {
  recommendation: Recommendation;
  onSelect: (rec: Recommendation) => void;
}

export function RecommendationCard({ recommendation, onSelect }: Props) {
  const status = STATUS_LABELS[recommendation.status];

  return (
    <button className="rec-card" onClick={() => onSelect(recommendation)}>
      <span className="rec-badge" style={{ backgroundColor: DECISION_COLORS[recommendation.decision] }}>
        {recommendation.decision.toUpperCase()}
      </span>
      <div className="rec-body">
        <div className="rec-component">{recommendation.component_id}</div>
        <div className="rec-rationale">
          {recommendation.status === "failed" && recommendation.failure_reason
            ? recommendation.failure_reason
            : recommendation.rationale}
        </div>
      </div>
      {status && <span className={`rec-status rec-status-${recommendation.status}`}>{status}</span>}
      <div className="rec-confidence">{Math.round(recommendation.confidence * 100)}%</div>
    </button>
  );
}
