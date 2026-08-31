// Mirrors backend/app/knowledge_base/schema.py and reporting/report_builder.py

export interface ComponentMetrics {
  loc: number;
  cyclomatic_complexity: number;
  nesting_depth: number;
  num_params: number;
}

export interface Component {
  id: string;
  project_id: string;
  language: string;
  kind: "function" | "method" | "class";
  name: string;
  qualified_name: string;
  file_path: string;
  line_start: number;
  line_end: number;
  signature: string | null;
  docstring: string | null;
  parent_id: string | null;
  metrics: ComponentMetrics;
  content_hash: string;
}

export interface TestCase {
  id: string;
  project_id: string;
  language: string;
  framework: string;
  name: string;
  file_path: string;
  line_start: number;
  line_end: number;
  target_component_ids: string[];
  mapping_method: "naming_convention" | "import_graph" | "coverage" | "unmapped";
  mapping_confidence: number;
  origin: "existing" | "ai_generated" | "ai_modified";
}

export interface ChangeRecord {
  id: string;
  project_id: string;
  from_commit: string | null;
  to_commit: string | null;
  component_id: string;
  change_type: "added" | "modified" | "deleted";
  diff_summary: string | null;
  impact_propagated_to: string[];
}

export interface Recommendation {
  id: string;
  project_id: string;
  component_id: string;
  related_test_ids: string[];
  decision: "retain" | "modify" | "remove" | "generate";
  rationale: string;
  confidence: number;
  status: "pending_review" | "accepted" | "rejected" | "applied";
  generated_test_id: string | null;
}

export interface ProjectSummary {
  project_id: string;
  languages: string[];
  frameworks: string[];
  component_count: number;
  test_count: number;
  mapped_test_count: number;
  parse_error_count: number;
}

export interface ProjectReport {
  project_id: string;
  total_recommendations: number;
  retained: number;
  modified: number;
  removed: number;
  generated: number;
}
