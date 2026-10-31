from fastapi.testclient import TestClient

from backend.agents import Registry
from backend.main import create_app
from backend.seed import seed
from backend.seed_support import seed_support
from backend.seed_patterns import seed_patterns
from backend.seed_complaints import seed_complaints
from backend.seed_multilingual import seed_multilingual


def test_demo_order_hides_empty_case_and_keeps_pagination_and_access(tmp_path):
    path = tmp_path / 'listing.sqlite3'
    tokens = seed(path)['tokens']
    seed_support(path)
    seed_patterns(path)
    seed_complaints(path)
    seed_multilingual(path)
    app = create_app(path, agent_registry=Registry(), inbox_worker=False)
    app.state.demo_mode = True
    with TestClient(app) as client:
        def listing(user='admin', **params):
            return client.get('/api/cases', params={'order': 'demo', **params},
                headers={'Authorization': 'Bearer '+tokens[user]}).json()
        full = listing()['items']
        assert len(full) == 30
        assert 'demo-case' not in {r['id'] for r in full}
        assert [r['id'] for r in full[:6]] == [
            'demo-multilingual-zh', 'demo-flow-20-17', 'demo-flow-20-03',
            'demo-multilingual-mn', 'demo-flow-20-14', 'demo-multilingual-ru']
        loaded = []
        after = ''
        while True:
            page = listing(limit=2, after=after)
            loaded += page['items']
            after = page['next_cursor']
            if not after:
                break
        assert [r['id'] for r in loaded] == [r['id'] for r in full]
        assert listing('other-admin')['items'] == []
        assert not any(r['id'].startswith('demo-multilingual-') for r in listing('teacher')['items'])
        # Login integrity and the ordinary API cursor contract continue to work.
        assert any(r['id'] == 'demo-case' for r in listing(order='id')['items'])
