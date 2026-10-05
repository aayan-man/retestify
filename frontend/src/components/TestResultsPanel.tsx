import { useState } from "react";
import type { RunResult, TestOutcome } from "../types/kb";

interface Props {
  run: RunResult;
}

/** Strips the file prefix pytest/jest put in front of a test name, so the
 *  list reads as test names rather than repeated paths. */
function shortName(name: string): string {
  const parts = name.split("::");
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function fileOf(name: string): string | null {
  const parts = name.split("::");
  return parts.length > 1 ? parts[0] : null;
}

function OutcomeRow({ outcome }: { outcome: TestOutcome }) {
  const [open, setOpen] = useState(false);
  const hasDetail = Boolean(outcome.message);

  return (
    <li className={`outcome outcome-${outcome.status}`}>
      <div className="outcome-head">
        <span className={`outcome-status outcome-status-${outcome.status}`}>{outcome.status}</span>
        <span className="outcome-name" title={outcome.name}>
          {shortName(outcome.name)}
        </span>
        {fileOf(outcome.name) && <span className="outcome-file">{fileOf(outcome.name)}</span>}
        <span className="outcome-duration">{outcome.duration_ms}ms</span>
        {hasDetail && (
          <button className="outcome-toggle" onClick={() => setOpen((v) => !v)}>
            {open ? "hide" : "why?"}
          </button>
        )}
      </div>
      {open && hasDetail && <pre className="outcome-message">{outcome.message}</pre>}
    </li>
  );
}

export function TestResultsPanel({ run }: Props) {
  const [showPassing, setShowPassing] = useState(false);

  // Failures first and expanded by default: a run is usually opened to find
  // out what broke, not to admire what passed.
  const failing = run.outcomes.filter((o) => o.status !== "passed" && o.status !== "skipped");
  const skipped = run.outcomes.filter((o) => o.status === "skipped");
  const passing = run.outcomes.filter((o) => o.status === "passed");

  return (
    <section className="test-results">
      <h2>Test run</h2>

      <div className="report-strip">
        <span className={`run-status run-status-${run.status}`}>{run.status}</span>
        <span>
          {run.passed}/{run.total} passed
          {run.failed > 0 && `, ${run.failed} failed`}
          {run.errors > 0 && `, ${run.errors} errored`}
          {skipped.length > 0 && `, ${skipped.length} skipped`}
        </span>
        <span>
          Coverage: {run.coverage_percent === null ? "n/a" : `${run.coverage_percent.toFixed(1)}%`}
        </span>
        <span>{(run.duration_ms / 1000).toFixed(1)}s</span>
      </div>

      {run.total === 0 && (
        <p className="muted">
          No tests ran. {run.stderr ? "See the reason below." : "Check that the project has a test framework."}
        </p>
      )}

      {failing.length > 0 && (
        <>
          <h3 className="outcome-group-heading">
            {failing.length} failing {failing.length === 1 ? "test" : "tests"}
          </h3>
          <ul className="outcome-list">
            {failing.map((o) => (
              <OutcomeRow key={o.name} outcome={o} />
            ))}
          </ul>
        </>
      )}

      {run.total === 0 && run.stderr && <pre className="outcome-message">{run.stderr}</pre>}

      {passing.length + skipped.length > 0 && (
        <>
          <button className="link-button" onClick={() => setShowPassing((v) => !v)}>
            {showPassing ? "Hide" : "Show"} {passing.length + skipped.length} other{" "}
            {passing.length + skipped.length === 1 ? "test" : "tests"}
          </button>
          {showPassing && (
            <ul className="outcome-list">
              {[...passing, ...skipped].map((o) => (
                <OutcomeRow key={o.name} outcome={o} />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
