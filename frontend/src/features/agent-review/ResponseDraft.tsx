export type DraftFields = {
  response_draft?: string;
  validation_checks?: string[];
  evidence_used?: string[];
};

export function ResponseDraft({ result }: { result: DraftFields }) {
  return <>
    <h3>AI가 준비한 보호자 답변</h3>
    <p className="preserve">{result.response_draft || "이전 결과에는 답변 초안이 없습니다."}</p>
    <h3>AI 점검 제안</h3>
    {result.validation_checks?.length
      ? <ul>{result.validation_checks.map((s, i) => <li key={i}>{s}</li>)}</ul>
      : <p>저장된 점검 결과가 없습니다. 담당자가 직접 확인해 주세요.</p>}
    <p className="hint">사용한 공식 근거: {result.evidence_used?.join(", ") || "직접 인용 근거 없음"} · 관리자 검토 전에는 발송되지 않습니다.</p>
  </>;
}
