from agent.knowledge import _active_on


def test_scheduled_law_is_not_active_before_effective_date():
    chunk = {"status": "scheduled", "effective_from": "2026-12-03"}
    assert _active_on(chunk, "2026-10-30") is False


def test_scheduled_law_becomes_active_on_effective_date():
    chunk = {"status": "scheduled", "effective_from": "2026-12-03"}
    assert _active_on(chunk, "2026-12-03") is True


def test_expired_article_is_not_active():
    chunk = {"status": "in_force", "effective_from": "2026-01-01", "effective_to": "2026-06-30"}
    assert _active_on(chunk, "2026-07-01") is False
