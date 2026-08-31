from app.monitoring.poller import poll_once


def test_poll_once_reports_negative_one_for_unknown_project():
    results = poll_once(["does-not-exist"])
    assert results == {"does-not-exist": -1}


def test_poll_once_continues_after_one_project_fails(monkeypatch):
    from app.jobs import pipeline

    def fake_detect_changes(project_id: str):
        if project_id == "bad":
            raise RuntimeError("boom")
        return [1, 2, 3]

    monkeypatch.setattr(pipeline, "detect_changes", fake_detect_changes)

    results = poll_once(["bad", "good"])
    assert results == {"bad": -1, "good": 3}
