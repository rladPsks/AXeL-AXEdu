from agent.retrieval import load_corpus, retrieve

def test_legacy_manual_chunks_are_canonicalized_to_manual_source():
    corpus = load_corpus()
    manual = [x for x in corpus if x.get("chunk_id") == "M-10-ROUTING"]
    assert manual
    assert manual[0]["source_id"] == "MOE-MANUAL-2026"
    assert "routing" in manual[0]["retrieval_tags"]

def test_life_guidance_retrieval_can_surface_manual_routing():
    results = retrieve("생활지도 민원대응팀 담당자 협조 사실 확인", top_k=8)
    assert any(x.get("source_id") == "MOE-MANUAL-2026" for x in results)

def test_parsed_corpus_does_not_hide_curated_legacy_baseline(monkeypatch):
    import agent.retrieval as retrieval
    parsed = [{"chunk_id":"PARSED-ONLY","source_id":"MOE-POLICY-2026-01",
               "source_type":"policy_plan","title":"parsed","text":"parsed","locator":"p13"}]
    monkeypatch.setattr(retrieval, "_load_chunk_files",
                        lambda folder: parsed if folder == retrieval.CHUNKS_DIR else [])
    corpus = retrieval.load_corpus()
    assert any(x.get("chunk_id") == "M-10-ROUTING" for x in corpus)
    assert any(x.get("chunk_id") == "PARSED-ONLY" for x in corpus)
