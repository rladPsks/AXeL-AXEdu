"""Restore registered provenance without changing the saved retrieval excerpt."""
import json
from config import DATA_DIR


def with_source_metadata(evidence):
    registry = json.loads((DATA_DIR / 'source_registry.json').read_text(encoding='utf-8'))
    sources = {}
    for source in registry.get('sources', []):
        for key in [source['source_id'], *source.get('source_aliases', [])]:
            sources[key] = source
    result = []
    for item in evidence:
        source = sources.get(item.get('source_id'), {})
        enriched = dict(item)
        for key in ('title', 'issuer', 'official_url', 'uploaded_filename'):
            if not enriched.get(key) and source.get(key):
                enriched[key] = source[key]
        result.append(enriched)
    return result
