import type { Recommendation } from "../types/kb";

const DECISION_COLORS: Record<Recommendation["decision"], string> = {
  retain: "#2e7d32",
  modify: "#ed6c02",
  remove: "#c62828",
  generate: "#1565c0",
};

interface Props {
  recommendation: Recommendation;
  onSelect: (rec: Recommendation) => void;
}

export function RecommendationCard({ recommendation, onSelect }: Props) {
  return (
    <button className="rec-card" onClick={() => onSelect(recommendation)}>
      <span className="rec-badge" style={{ backgroundColor: DECISION_COLORS[recommendation.decision] }}>
        {recommendation.decision.toUpperCase()}
      </span>
      <div className="rec-body">
        <div className="rec-component">{recommendation.component_id}</div>
        <div className="rec-rationale">{recommendation.rationale}</div>
      </div>
      <div className="rec-confidence">{Math.round(recommendation.confidence * 100)}%</div>
    </button>
  );
}
