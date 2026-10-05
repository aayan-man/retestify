"""Java/Maven test runner.

Maven is a network-first build tool: plugins, their dependencies, the
surefire provider and the project's own libraries are all resolved from
remote repositories on demand. The sandboxed run, however, executes with
`--network=none` (see sandbox_exec.run_in_container), so a plain `mvn test`
inside it cannot resolve anything and the suite never starts -- the exact
failure mode that made the Python runner silently useless before its
tooling was baked into the image.

The fix is the same one PytestRunner uses: do every networked step at image
*build* time, where there is a network. The build copies the target repo's
pom.xml into the image, runs `dependency:go-offline` and a no-op `test`
lifecycle pass to populate /root/.m2, and pre-fetches the surefire
providers that surefire itself only resolves lazily once it has detected
tests. The run then uses `mvn -o` (offline) and resolves everything from
the local repository already inside the image.
"""

from __future__ import annotations

import hashlib
import time
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path

from app.config import settings
from app.repo_manager.workspace import Workspace

from .base import RunResult, TestOutcome, TestRunner, overall_status
from .sandbox_exec import ensure_runner_image, run_in_container, runner_image_tag


# No APP_TEST_RUNNER_DOCKER_IMAGE_JAVA setting exists yet; read it if one is
# added, otherwise fall back to a pinned Maven + JDK 17 base.
DEFAULT_JAVA_IMAGE = "maven:3.9-eclipse-temurin-17"

# Every line here runs with a network, which is the entire point.
#
#  - go-offline resolves the project's declared dependencies and build
#    plugins. It is strict: if the pom cannot be resolved at all, failing
#    loudly here (docker build stderr is surfaced to the caller) is far more
#    useful than a baffling offline failure later.
#  - The no-op `test` pass walks the real default lifecycle, which pulls the
#    resources/compiler/surefire plugins that go-offline does not always
#    reach. The build context holds only pom.xml, so there is nothing to
#    compile and nothing to run; it is tolerant because some poms legitimately
#    cannot complete a lifecycle without their sources present.
#  - surefire picks its *provider* (surefire-junit4, surefire-junit-platform,
#    ...) at runtime from what it finds on the test classpath, so no earlier
#    step downloads it. The provider version must match the surefire plugin
#    version that was just resolved, which is read back out of the local
#    repository rather than hard-coded.
MAVEN_RUNNER_DOCKERFILE = """FROM {base}
COPY pom.xml /prefetch/pom.xml
WORKDIR /prefetch
RUN mvn -B -f /prefetch/pom.xml dependency:go-offline
RUN mvn -B -f /prefetch/pom.xml test || true
RUN V=$(ls /root/.m2/repository/org/apache/maven/plugins/maven-surefire-plugin 2>/dev/null | head -1) \\
 && for p in surefire-junit4 surefire-junit47 surefire-junit-platform; do \\
      mvn -B dependency:get -Dartifact=org.apache.maven.surefire:$p:$V || true; \\
    done
WORKDIR /workspace
"""

SUREFIRE_REPORT_DIR = "target/surefire-reports"

NO_POM_HINT = (
    "The target repo has no pom.xml at its root, so there is no Maven project "
    "to build. A multi-module or nested-layout repo needs the module directory "
    "ingested as the workspace source root."
)

NO_REPORT_HINT = (
    f"Maven produced no surefire reports ({SUREFIRE_REPORT_DIR}/TEST-*.xml); the "
    "suite did not run to completion, so this run is reported as an error rather "
    "than a pass. The usual causes are a test-compile failure (a test framework "
    "the pom does not declare as a dependency) or a dependency that was not in "
    "the local repository baked into the runner image."
)


class MavenRunner(TestRunner):
    language = "java"

    def __init__(self, image: str | None = None):
        self.image = image or getattr(settings, "test_runner_docker_image_java", DEFAULT_JAVA_IMAGE)

    def run(self, workspace: Workspace, *, targets: list[str] | None = None, timeout_s: int = 300) -> RunResult:
        run_id = f"run_{uuid.uuid4().hex[:10]}"
        start = time.monotonic()

        pom = workspace.source_dir / "pom.xml"
        if not pom.is_file():
            return _error_result(run_id, start, NO_POM_HINT)

        if targets:
            # Surefire selects by test class/method pattern, not by path.
            selector = f" -Dtest={','.join(targets)} -DfailIfNoSpecifiedTests=false"
        else:
            selector = ""

        # Stale reports from an earlier run are deleted *before* the build, not
        # after parsing: a run whose test-compile fails would otherwise leave
        # the previous run's XML in place and be parsed as a pass. A false
        # green is the worst way for a test tool to be wrong.
        #
        # -o is offline mode. It is what makes --network=none survivable, and
        # it also means a missing artifact fails fast instead of hanging on a
        # connect timeout.
        command = [
            "sh",
            "-c",
            f"rm -rf {SUREFIRE_REPORT_DIR}; mvn -o -B test{selector}",
        ]

        # The pom is what the image's local repository was populated from, so
        # a changed pom has to produce a different image.
        digest = hashlib.sha256(pom.read_bytes()).hexdigest()[:12]
        dockerfile = MAVEN_RUNNER_DOCKERFILE.format(base=self.image)

        try:
            image = ensure_runner_image(
                runner_image_tag(self.image, f"maven-{digest}"),
                dockerfile,
                # Supplies pom.xml to COPY. Only the pom is read from it, so an
                # unrelated source edit does not invalidate the image.
                context_dir=workspace.source_dir,
            )
            proc = run_in_container(
                image=image,
                workspace_dir=workspace.source_dir,
                command=command,
                timeout_s=timeout_s,
                # A JVM plus the Maven launcher does not fit the 512m default.
                memory="1g",
            )
        except Exception as e:
            return _error_result(run_id, start, str(e))
        duration_ms = int((time.monotonic() - start) * 1000)

        outcomes, totals = _parse_surefire_reports(workspace.source_dir / SUREFIRE_REPORT_DIR)

        stderr = proc.stderr[-4000:]
        if totals["total"] == 0:
            stderr = _append_note(stderr, NO_REPORT_HINT)

        return RunResult(
            run_id=run_id,
            status=overall_status(totals),
            total=totals["total"],
            passed=totals["passed"],
            failed=totals["failed"],
            errors=totals["errors"],
            skipped=totals["skipped"],
            duration_ms=duration_ms,
            outcomes=outcomes,
            # Not wired up. JaCoCo reports coverage only when the jacoco plugin
            # is bound into the build, which would mean rewriting the target
            # repo's pom.xml -- this runner does not mutate the project under
            # test. `-Djacoco.skip=false` cannot add a plugin that the pom
            # never declared.
            coverage_percent=None,
            stdout=proc.stdout[-4000:],
            stderr=stderr,
        )


def _error_result(run_id: str, start: float, message: str) -> RunResult:
    return RunResult(
        run_id=run_id,
        status="error",
        total=0,
        passed=0,
        failed=0,
        errors=1,
        skipped=0,
        duration_ms=int((time.monotonic() - start) * 1000),
        stderr=message,
    )


def _append_note(stderr: str, note: str) -> str:
    return f"{stderr.rstrip()}\n{note}" if stderr.strip() else note


def _parse_surefire_reports(report_dir: Path) -> tuple[list[TestOutcome], dict[str, int]]:
    """Read every TEST-*.xml surefire wrote, newest-run-only by construction
    (the directory is cleared before the build)."""
    totals = {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    if not report_dir.is_dir():
        return [], totals

    outcomes: list[TestOutcome] = []
    for path in sorted(report_dir.glob("TEST-*.xml")):
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError):
            continue
        # A <testsuite> root, or a <testsuites> wrapper around several.
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        for suite in suites:
            for case in suite.findall("testcase"):
                outcome = _parse_testcase(case)
                outcomes.append(outcome)
                totals["total"] += 1
                # TestOutcome.status uses the singular "error"; the totals key
                # is the plural "errors" that RunResult/overall_status expect.
                totals["errors" if outcome.status == "error" else outcome.status] += 1
    return outcomes, totals


def _parse_testcase(case: ET.Element) -> TestOutcome:
    classname = case.get("classname") or ""
    name = case.get("name") or "unknown"
    full_name = f"{classname}#{name}" if classname else name

    # Surefire distinguishes an assertion failure (<failure>) from an
    # unexpected exception (<error>); base.overall_status treats both as
    # not-a-pass, but keeping them apart is what lets a report say whether the
    # code is wrong or the test itself blew up.
    status = "passed"
    message: str | None = None
    for tag, mapped in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
        node = case.find(tag)
        if node is not None:
            status = mapped
            message = node.get("message") or (node.text or "").strip() or None
            break

    return TestOutcome(
        name=full_name,
        status=status,
        duration_ms=_duration_ms(case.get("time")),
        message=message,
    )


def _duration_ms(raw: str | None) -> int:
    if not raw:
        return 0
    try:
        # Surefire can emit locale-grouped numbers like "1,234.5".
        return int(float(raw.replace(",", "")) * 1000)
    except ValueError:
        return 0
