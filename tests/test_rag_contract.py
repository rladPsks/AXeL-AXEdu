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
