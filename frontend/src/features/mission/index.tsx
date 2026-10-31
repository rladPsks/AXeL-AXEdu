import { useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { ErrorNotice, date, label } from "../../shared/ui";
import { personName } from "../../shared/names";
import "./mission.css";

export function LevelGuide({ caseId }: { caseId?: string }) {
  const { session } = useSession();
  const base = caseId ? `/cases/${encodeURIComponent(caseId)}` : "/cases";
  const groups = [
    { level: "Level 1", title: "분류하고 답변하기", links: [["원문·유형·긴급도", `${base}?tab=intake`], ["근거 답변·표현 조절", `${base}?tab=response`], ["전체 처리 이력", `${base}?tab=timeline`]] },
    { level: "Level 2", title: "반복의 맥락 살피기", links: [["민원인·누적 패턴", "/patterns"], ["같은 사안·새 사실 비교", `${base}?tab=comparison`], ["지원·이관 판단", `${base}?tab=support-decisions`]] },
    { level: "Level 3", title: "학교 밖 지원까지 연결", links: [["교육지원청 이관 서류", `${base}?tab=report`], ["교사 노출도·처리시간", "/dashboard"], ["다국어 원문 대조", `${base}?tab=translation`], ["동의 녹취·요약", `${base}?tab=recordings`]] },
  ];
  if (session.role !== "ADMIN" || !caseId) return null;
  return <section className="level-guide" aria-label="Level 1부터 3까지 업무 흐름">{groups.map((group) => <article key={group.level}><span className="meta">{group.level}</span><h3>{group.title}</h3>{group.links.map(([title,url]) => <Link key={url} to={url}>{title} →</Link>)}</article>)}</section>;
}

type PatternCase = { id: string; title: string; received_at: string; issue_key: string; raw_text: string; response_recorded: boolean; signals: string[]; compare_case_id?: string };
type Patterns = { window_days: number; minimum_count: number; unlinked_count: number; notice: string; groups: { person_key: string; display_name: string; count: number; issue_count: number; repeat_candidate: boolean; unanswered_count: number; cases: PatternCase[] }[] };
export function PatternsPage({ caseId }: { caseId?: string }) {
  const { api, session } = useSession(); const scope = useScope();
  const [filter,setFilter] = useState("");
  const query=useQuery({ queryKey:["patterns",...scope], enabled:session.role==="ADMIN", queryFn:({signal})=>api.get<Patterns>("/api/school/complainant-patterns",signal) });
  if(session.role!=="ADMIN") return <p>관리자만 민원인 누적 패턴을 조회할 수 있습니다.</p>;
  if(query.isPending) return <p role="status">동일인·동일 사안 기록을 모으는 중…</p>;
  if(query.error) return <ErrorNotice error={query.error}/>;
  const data=query.data;
  const groups=data.groups.filter(g=>(!caseId||g.cases.some(c=>c.id===caseId))&&(!filter||`${g.display_name} ${g.person_key}`.includes(filter)));
  return <><div className="page-heading"><div><h1>민원인·반복 누적 패턴</h1><p>최근 {data.window_days}일 · 같은 사안 {data.minimum_count}회 이상은 맥락 검토 후보</p></div><button onClick={()=>void query.refetch()} disabled={query.isFetching}>새로고침</button></div>
    <p className="notice">{data.notice}</p>
    <label>민원인 검색<input value={filter} onChange={e=>setFilter(e.target.value)} placeholder="가상민원인 이름 또는 식별키" /></label>
    {!groups.length?<p>연결된 동일인 기록이 없습니다. 민원 상세의 ‘반복·새 사실 비교’에서 식별키를 확인할 수 있습니다.</p>:null}
    {groups.map(g=><section className="panel pattern-person" key={g.person_key}><h2>{g.display_name} <span className="badge">{g.count}건 · {g.issue_count}개 사안</span></h2><p>답변 전달 미기록 {g.unanswered_count}건 · {g.repeat_candidate?"동일 사안 누적 검토 후보":"누적 검토 기준 미도달"}</p><p className="hint">확인된 동일인 식별키: {g.person_key}</p>
      <ol className="pattern-sequence">{g.cases.map((c,index)=><li key={c.id}><div><b>{index+1}차 접수</b> · {date(c.received_at)} <span className="badge">{c.response_recorded?"답변 전달 기록 있음":"답변 전달 미기록"}</span></div><h3><Link to={`/cases/${c.id}?tab=comparison`}>{c.title} →</Link></h3><p className="meta">사안: {c.issue_key}</p><ul>{c.signals.map(signal=><li key={signal}>{signal}</li>)}</ul><details><summary>원문·관련 민원 대조</summary><p className="preserve">{c.raw_text}</p>{c.compare_case_id?<Link to={`/cases/${c.id}?tab=comparison`}>이전 민원과 대조·연결 검토 →</Link>:null}</details></li>)}</ol>
    </section>)}<p className="hint">동일인 확인 전 민원 {data.unlinked_count}건은 이름만으로 자동 합치지 않습니다.</p>
    {caseId?<Link to={`/cases/${caseId}?tab=comparison`}>식별키·동일 사안 연결/분리 관리 →</Link>:null}
  </>;
}

type History = {id:string;action:string;actor_id:string;created_at:string;source:string;payload:Record<string,unknown>};
export function FullHistory({caseId}:{caseId:string}) {
  const {api}=useSession(); const scope=useScope(); const [search,setSearch]=useState("");
  const query=useQuery({queryKey:["full-history",...scope,caseId],queryFn:({signal})=>api.get<History[]>(`/api/cases/${caseId}/full-history`,signal)});
  const items=query.data?.filter(e=>JSON.stringify(e).includes(search))??[];
  return <><div className="section-heading"><h2>전체 처리 이력</h2><button onClick={()=>void query.refetch()} disabled={query.isFetching}>이력 새로고침</button></div><p>접수·업무·지원·사람의 판단·AI 실행·자료 정정·답변·서류 내보내기를 한 흐름으로 확인합니다.</p><label>이력 검색<input value={search} onChange={e=>setSearch(e.target.value)} placeholder="행동, 담당자 또는 기록 내용"/></label>{query.error?<ErrorNotice error={query.error}/>:query.isPending?<p>기록을 불러오는 중…</p>:<ol className="timeline">{items.map(e=><li key={`${e.source}-${e.id}`}><div><strong>{label(e.action)}</strong><span>{date(e.created_at)}</span></div><p>{personName(e.actor_id)} · {e.source}</p>{["reason","reply","result","note","content","summary"].map(key=>typeof e.payload[key]==="string"?<p className="preserve" key={key}>{String(e.payload[key])}</p>:null)}<details><summary>기록 상세 · 원본 보존</summary><pre className="history-payload">{JSON.stringify(e.payload,null,2)}</pre></details></li>)}</ol>}</>;
}

type Kind="REPORT"|"RESPONSE"|"TRANSLATION";
type Content={text:string;original:string;language:string};
type Product={id:string;revision:number;status:string;stale:boolean;content:Content;created_by:string;created_at:string};
type Products={initial:Content;products:Product[];decision:{stale:boolean;snapshot:{reason:string;target:string;route:string;remaining_school_work:string}}|null;evidence:{title?:string;source_id?:string;text?:string}[]};
const titles:Record<Kind,string>={REPORT:"교육지원청 이관 서류",RESPONSE:"근거 답변·표현 조절",TRANSLATION:"다국어 원문·번역 대조"};
const states:Record<string,string>={DRAFT:"검토 전 초안",APPROVED:"관리자 승인",EXPORTED:"내보내기 기록",DELIVERED:"답변 전달 기록"};
export function WorkProduct({record,kind}:{record:CaseDetail;kind:Kind}) {
 const {api}=useSession();const scope=useScope();const queries=useQueryClient();
 const path=`/api/cases/${record.id}/work-products/${kind}`;
 const query=useQuery({queryKey:["work-products",...scope,record.id,kind,record.version],queryFn:({signal})=>api.get<Products>(path,signal)});
 if(query.isPending)return <p>민원 기록으로 초안을 준비하는 중…</p>;
 if(query.error)return <ErrorNotice error={query.error}/>;
 const data=query.data;const latest=data.products[0];
 const refresh=()=>{void query.refetch();void queries.invalidateQueries({queryKey:["full-history",...scope,record.id]});void queries.invalidateQueries({queryKey:["patterns",...scope]});};
 const download=()=>{if(!latest)return;const url=URL.createObjectURL(new Blob([latest.content.text],{type:"text/markdown;charset=utf-8"}));const a=document.createElement("a");a.href=url;a.download=`교육지원청_이관검토_${record.id}_v${latest.revision}.md`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
 return <><h2>{titles[kind]}</h2><p className="hint">{kind==="REPORT"?"민원·학교 조치·관리자 판단·참고 근거를 모아 편집 가능한 서류를 준비합니다. 기관 전송은 연결되지 않았으며 파일로 내보냅니다.":kind==="RESPONSE"?"근거와 원문을 대조해 표현을 다듬고, 승인한 버전의 실제 전달 사실을 기록합니다. 이 버튼이 외부로 발송하지는 않습니다.":"원문과 한국어 번역을 대조하고 요구·날짜·인물·부정 표현의 의미를 확인합니다."}</p>
 {latest?<p><span className="badge">{states[latest.status]} · 버전 {latest.revision}</span>{latest.stale?" · 민원이 변경됨: 다시 검토 필요":""}</p>:null}
 {kind==="REPORT"?<div className="notice">{data.decision?<><b>학교의 지원 판단</b><p>{data.decision.snapshot.reason}</p><p>대상: {data.decision.snapshot.target} · 경로: {data.decision.snapshot.route}</p><p>학교 후속 업무: {data.decision.snapshot.remaining_school_work}</p>{data.decision.stale?<p>이 판단 이후 기록이 변경되었습니다. 새 판단을 남긴 후 서류를 검토하세요.</p>:null}</>:<p>승인·내보내기 전에 관리자 지원 판단을 등록해 주세요.</p>}<Link to={`/cases/${record.id}?tab=support-decisions`}>지원 대상·사유·후속 업무 판단 →</Link></div>:null}
 <ProductEditor key={`${kind}-${latest?.id??"new"}`} record={record} kind={kind} path={path} initial={latest?.content??data.initial} revision={latest?.revision??0} onSaved={refresh}/>
 {kind==="REPORT"&&latest?<details open><summary>서류 미리보기</summary><article className="report-preview preserve">{latest.content.text}</article></details>:null}
 {data.evidence.length?<details><summary>답변·서류의 참고 근거</summary>{data.evidence.map((e,i)=><blockquote key={i}><b>{e.title??e.source_id}</b><p>{e.text}</p></blockquote>)}</details>:null}
 {latest&&record.status!=="CLOSED"?<section className="work-item"><h3>검토·승인·기록</h3>{latest.status==="DRAFT"?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`} button={kind==="TRANSLATION"?"번역 검토 확정":"검토 후 승인"} disabled={latest.stale||(kind==="REPORT"&&(!data.decision||data.decision.stale))} onSaved={refresh}><input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="APPROVED"/><label>확인 내용·승인 사유<textarea name="reason" required maxLength={10000}/></label><label><span><input type="checkbox" required style={{width:"auto"}}/> 원문·사실·날짜·약속·민감정보와 근거를 대조했습니다.</span></label></CommandForm>:null}
 {kind==="RESPONSE"&&latest.status==="APPROVED"?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`} button="실제 전달 사실 기록" disabled={latest.stale} onSaved={refresh}><input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="DELIVERED"/><label>전달한 경로·시각·확인 근거<textarea name="reason" required placeholder="학교 시스템에서 실제 전달한 사실을 기록하세요." maxLength={10000}/></label></CommandForm>:null}
 {kind==="REPORT"&&["APPROVED","EXPORTED"].includes(latest.status)?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`} button="승인 서류 파일 내보내기" disabled={latest.stale} onSaved={()=>{download();refresh();}}><input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="EXPORTED"/><label>내보내기 목적·제출 경로 확인<textarea name="reason" required maxLength={10000}/></label></CommandForm>:null}</section>:null}
 <details><summary>문서 수정·승인 이력 ({data.products.length}건)</summary>{data.products.map(p=><article className="work-item" key={p.id}><b>버전 {p.revision} · {states[p.status]}</b><p>{personName(p.created_by)} · {date(p.created_at)}</p><p className="preserve">{p.content.text}</p></article>)}</details>
 </>;
}
function ProductEditor({record,kind,path,initial,revision,onSaved}:{record:CaseDetail;kind:Kind;path:string;initial:Content;revision:number;onSaved:()=>void}) {
 const [text,setText]=useState(initial.text);
 return <>{kind==="RESPONSE"?<ToneAssist record={record} revision={revision} onApply={setText}/>:null}<CommandForm caseId={record.id} version={record.version} path={path} button="새 초안 버전 저장" disabled={record.status==="CLOSED"} onSaved={onSaved} transformValues={v=>({previous_revision:revision,reason:v.reason,content:{text,original:initial.original||initial.text,language:String(v.language??initial.language??"ko")}})}>
 {kind!=="REPORT"?<div className="draft-compare"><section><h3>{kind==="TRANSLATION"?"접수 원문":"다듬기 전 문장"}</h3><p className="preserve">{initial.original||initial.text||"아직 생성된 초안이 없습니다. AI 지원 검토에서 먼저 생성할 수 있습니다."}</p></section><label>{kind==="TRANSLATION"?"검토한 한국어 번역":"검토·수정 답변"}<textarea required rows={12} value={text} onChange={e=>setText(e.target.value)} maxLength={40000}/></label></div>:<label>이관 서류 본문<textarea required rows={18} value={text} onChange={e=>setText(e.target.value)} maxLength={40000}/></label>}
 {kind==="TRANSLATION"?<label>원문 언어<input name="language" defaultValue={initial.language} required maxLength={40}/></label>:null}
 {kind==="RESPONSE"?<><p className="hint">감정 완화 표현을 사용하되 확인되지 않은 잘못 인정·보상·기한 약속을 추가하지 마세요.</p><Link to={`/cases/${record.id}?tab=agent-review`}>AI 근거 답변 생성·검토 →</Link></>:null}
 <label>수정·작성 사유<textarea name="reason" required maxLength={10000}/></label>
 </CommandForm></>;
}


type ToneRun={run_id:string;purpose:string;status:string;stale:boolean;error:{message:string}|null;result:{response_draft:string;original:string;source_revision:number;changes:string[];meaning_checks:string[]}|null};
function ToneAssist({record,revision,onApply}:{record:CaseDetail;revision:number;onApply:(text:string)=>void}) {
 const {api}=useSession();const scope=useScope();
 const runs=useQuery({queryKey:["runs",...scope,record.id],queryFn:({signal})=>api.get<ToneRun[]>(`/api/cases/${record.id}/agent-runs`,signal),refetchInterval:q=>q.state.data?.some(r=>r.purpose==="TONE_REWRITE"&&["QUEUED","RUNNING"].includes(r.status))?1500:false});
 const latest=runs.data?.find(r=>r.purpose==="TONE_REWRITE");
 const result=latest?.result;
 return <details className="work-item"><summary>AI로 감정 완화 표현 제안받기</summary><p>저장한 답변 버전을 기준으로 표현을 다듬습니다. 사실·약속·책임 범위가 유지되는지 대조한 후 편집창에 적용하세요.</p>
 <CommandForm caseId={record.id} version={record.version} path={`/api/cases/${record.id}/agent-runs`} button="저장한 답변의 표현 조절 요청" disabled={!revision||record.status==="CLOSED"||["QUEUED","RUNNING"].includes(latest?.status??"")} transformValues={()=>({purpose:"TONE_REWRITE",input_refs:[{resource_type:"CASE",resource_id:record.id,version:record.version}]})} onSaved={()=>void runs.refetch()}/>
 {latest?<p role="status">{label(latest.status)}{latest.error?` · ${latest.error.message}`:""}</p>:null}
 {result?<><div className="draft-compare"><section><h3>다듬기 전</h3><p className="preserve">{result.original}</p></section><section><h3>AI 표현 제안</h3><p className="preserve">{result.response_draft}</p></section></div><ul>{[...result.changes,...result.meaning_checks].map((t,i)=><li key={i}>{t}</li>)}</ul><button type="button" disabled={latest?.stale||result.source_revision!==revision} onClick={()=>onApply(result.response_draft)}>대조한 제안을 편집창에 적용</button>{result.source_revision!==revision?<p>답변 버전이 변경되었습니다. 현재 버전으로 다시 요청하세요.</p>:null}<p className="hint">적용 후 아래에서 수정 사유와 함께 새 버전을 저장해야 반영됩니다.</p></>:null}
 {runs.error?<ErrorNotice error={runs.error}/>:null}</details>;
}
