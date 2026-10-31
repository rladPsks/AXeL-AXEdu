import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useSession } from "../../app/providers";
import { command } from "../../lib/api/client";
import type { CaseDetail } from "../../lib/api/types";
import { ErrorNotice } from "../../shared/ui";

type Evidence={source_id:string;title:string;source_type:string;location:string;pdf_page:number|null;official_url:string|null;excerpt:string;verification_status:string;reason:string};
export function ReferralEvidence({record,onApply}:{record:CaseDetail;onApply:(text:string)=>void}) {
 const {api}=useSession(); const [applied,setApplied]=useState(false);
 const query=useMutation({mutationFn:()=>api.execute<{items:Evidence[];notice:string}>(command(`/api/cases/${record.id}/referral-evidence`,{expected_version:record.version}))});
 return <section className="work-item"><h3>매뉴얼 조항으로 이관 근거 검토</h3><button type="button" className="primary" disabled={query.isPending||record.status==="CLOSED"} onClick={()=>query.mutate()}>{query.isPending?"관련 조항 찾는 중…":"매뉴얼 조항을 들어 이관 근거 제시 (이관 근거 추천)"}</button>
 {applied?<p role="status">아래 편집 내용에 추가했습니다. 해당 민원과의 연결 근거를 작성하고 저장하세요.</p>:null}
 {query.error?<ErrorNotice error={query.error}/>:null}
 {query.data?<><p className="hint">{query.data.notice}</p>{!query.data.items.length?<p>인용할 수 있는 조항을 찾지 못했습니다. 해당 매뉴얼 원문과 관할 기관의 요건을 확인하세요.</p>:null}{query.data.items.map((e,i)=><article className="work-item" key={`${e.source_id}-${i}`}><h4>{i+1}. {e.title} · {e.location}</h4><p className="meta">{e.source_type==="official_manual"?"매뉴얼":"정책자료 · 매뉴얼 조항과 구분"} · {e.pdf_page?`PDF ${e.pdf_page}쪽 · `:""}{["verified","corrected"].includes(e.verification_status)?"검수된 자료":"원문 검수 필요"}</p><blockquote className="preserve">{e.excerpt}</blockquote><p>{e.reason}</p>{e.official_url&&/^https?:\/\//.test(e.official_url)?<a href={e.official_url} target="_blank" rel="noreferrer">출처 원문 열기</a>:<p className="hint">원문 링크 미등록 · 출처 ID: {e.source_id}</p>}<button type="button" onClick={()=>{setApplied(true);onApply(`[이관 근거 검토 후보]\n${e.title} · ${e.location}${e.pdf_page?` (PDF ${e.pdf_page}쪽)`:""}\n출처: ${e.source_id} / ${e.source_type==="official_manual"?"매뉴얼":"정책자료"} / ${["verified","corrected"].includes(e.verification_status)?"검수됨":"원문 검수 필요"}\n인용: ${e.excerpt}\n적용 검토: ${e.reason}\n학교 조치와 해당 민원의 연결 근거: [담당자 작성 필요]`);}}>이 근거를 편집 내용에 추가</button></article>)}</>:null}</section>;
}
