import type { Recommendation } from "../types/kb";

interface Props {
  recommendation: Recommendation;
  onClose: () => void;
}

export function RecommendationDetailPage({ recommendation, onClose }: Props) {
  return (
    <div className="detail-overlay" onClick={onClose}>
      <div className="detail-panel" onClick={(e) => e.stopPropagation()}>
        <button className="detail-close" onClick={onClose} aria-label="Close">
          x
        </button>
        <h2>{recommendation.component_id}</h2>
        <p className="detail-decision">
          Decision: <strong>{recommendation.decision}</strong> (
          {Math.round(recommendation.confidence * 100)}% confidence)
        </p>
        <p>{recommendation.rationale}</p>
        <p className="muted">Status: {recommendation.status}</p>
        {recommendation.related_test_ids.length > 0 && (
          <>
            <h3>Related tests</h3>
            <ul>
              {recommendation.related_test_ids.map((id) => (
                <li key={id}>{id}</li>
              ))}
            </ul>
          </>
        )}
        {recommendation.generated_test_id && (
          <p className="muted">Generated test: {recommendation.generated_test_id}</p>
        )}
      </div>
    </div>
  );
}
