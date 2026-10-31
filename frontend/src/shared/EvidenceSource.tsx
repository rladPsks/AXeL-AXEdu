export type Evidence = {
  source_id?: string; chunk_id?: string; title?: string; issuer?: string;
  article?: string; pdf_page?: number; printed_page?: number; locator?: string;
  official_url?: string; file?: string; uploaded_filename?: string;
  section?: string; text?: string; reference_reason?: string;
};

export function EvidenceSource({ entry }: { entry: Evidence }) {
  const url = entry.official_url && /^https?:\/\//i.test(entry.official_url) ? entry.official_url : null;
  return <div className="evidence-source">
    <p><strong>{entry.title || entry.source_id || "출처 정보 확인 필요"}</strong></p>
    {entry.reference_reason ? <p>참고 이유: {entry.reference_reason}</p> : null}
    <p className="meta">출처: {entry.source_id || "문서 식별자 미등록"}
      {entry.issuer ? ` · 발행: ${entry.issuer}` : ""}
      {entry.article ? ` · ${entry.article}` : ""}
      {entry.pdf_page != null ? ` · PDF ${entry.pdf_page}쪽` : ""}
      {entry.printed_page != null ? ` · 인쇄 ${entry.printed_page}쪽` : ""}
      {entry.locator ? ` · 위치: ${entry.locator}` : ""}
      {entry.section ? ` · 항목: ${entry.section}` : ""}
      {entry.chunk_id ? ` · 청크: ${entry.chunk_id}` : ""}
      {entry.file || entry.uploaded_filename ? ` · 파일: ${entry.file || entry.uploaded_filename}` : ""}
    </p>
    {entry.text ? <p className="preserve">{entry.text}</p> : null}
    {url ? <a href={url} target="_blank" rel="noopener noreferrer">원문 출처 열기 ↗</a>
      : <p className="hint">원문 URL 미등록 · 위 문서·파일 식별자로 출처를 확인하세요.</p>}
  </div>;
}
