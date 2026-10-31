import { useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { EvidenceSource, type Evidence } from "../../shared/EvidenceSource";
import { ErrorNotice, date } from "../../shared/ui";
import { useUnsavedChanges } from "../../shared/useUnsavedChanges";
import { ReferralEvidence } from "./ReferralEvidence";

type Product = {id:string;revision:number;status:string;stale:boolean;content:{text:string};created_at:string};
type Data = {
  initial:{text:string}; products:Product[];
  decision:{stale:boolean;snapshot:{decision_type:string;reason:string;target:string;route:string;remaining_school_work:string}}|null;
  evidence:(Evidence & {excerpt?:string;location?:string;reason?:string})[];
};
const status:Record<string,string> = {DRAFT:"검토 전 초안",APPROVED:"저장본 승인",EXPORTED:"파일 내보내기 기록"};

export function ReportWorkspace({record}:{record:CaseDetail}) {
  const {api}=useSession(); const scope=useScope(); const queries=useQueryClient();
  const [editing,setEditing]=useState(false);
  const path=`/api/cases/${record.id}/work-products/REPORT`;
  const query=useQuery({queryKey:["work-products",...scope,record.id,"REPORT",record.version],
    queryFn:({signal})=>api.get<Data>(path,signal)});
  if(query.isPending)return <p role="status">현재 민원의 조치·판단·관련 근거로 초안을 준비하는 중…</p>;
  if(query.error)return <ErrorNotice error={query.error}/>;
  const data=query.data; const latest=data.products[0];
  const decisionReady=!!data.decision&&!data.decision.stale&&["EXTERNAL_SUPPORT","SPECIALIST_SUPPORT"].includes(data.decision.snapshot.decision_type);
  const refresh=()=>{setEditing(false);void query.refetch();void queries.invalidateQueries({queryKey:["full-history",...scope,record.id]});};
  const download=(result:Record<string,unknown>)=>{
    if(typeof result.text!=="string")return;
    const url=URL.createObjectURL(new Blob([result.text],{type:"text/markdown;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=`교육지원청_이관검토_${record.id}_v${result.revision}.md`;a.click();
    setTimeout(()=>URL.revokeObjectURL(url),1000);refresh();
  };
  return <>
    <h2>교육지원청 지원·이관 검토 서류</h2>
    <p className="notice">검토용 초안입니다. 근거 검색·문서 작성·파일 내보내기가 이관 확정이나 기관 제출을 뜻하지 않습니다.</p>
    <p>{latest?`저장본: ${status[latest.status]??latest.status} · 버전 ${latest.revision}`:"작성 상태: 아직 저장하지 않은 초안"}{editing?" · 편집 중인 내용은 미저장·미승인":""}</p>
    {latest?.stale?<p className="notice">민원 기록이 변경되었습니다. 현재 기록으로 초안을 다시 구성하고 새 버전을 저장하세요.</p>:null}
    <section className="work-item"><h3>연결된 학교 지원 판단</h3>
      {data.decision?<><p>{data.decision.snapshot.reason}</p><p>대상: {data.decision.snapshot.target} · 경로: {data.decision.snapshot.route}</p><p>남은 학교 업무: {data.decision.snapshot.remaining_school_work}</p></>:<p>지원 판단이 아직 등록되지 않았습니다. 초안부터 작성할 수 있습니다.</p>}
      {!decisionReady?<p className="hint">승인·내보내기 전에는 최신 외부·전문 지원 판단을 기록해야 합니다.</p>:null}
      <Link to={`/cases/${record.id}?tab=support-decisions`}>지원 대상·사유·후속 업무 검토 →</Link>
    </section>
    <ReportEditor key={latest?.id??"new"} record={record} path={path} initial={latest?.content.text??data.initial.text}
      revision={latest?.revision??0} onDirty={setEditing} onSaved={refresh}
      rebuild={async()=>{const result=await query.refetch();if(result.error)throw result.error;if(!result.data)throw new Error("초안을 불러오지 못했습니다.");return result.data.initial.text;}}/>
    <details><summary>현재 민원과 관련된 참고 근거 ({data.evidence.length}건)</summary>
      {data.evidence.length?data.evidence.map((e,i)=><EvidenceSource key={i} entry={{...e,text:e.excerpt??e.text,locator:e.location??e.locator,reference_reason:e.reason}}/>):<p>해당 민원과 관련성을 확인한 자료가 없습니다. 관계없는 자료를 자동으로 채우지 않습니다.</p>}
    </details>
    {latest&&record.status!=="CLOSED"?<section className="work-item"><h3>저장본 검토·승인·내보내기</h3>
      {editing?<p className="hint">본문이나 인용을 변경했습니다. 새 초안 버전을 저장한 뒤 승인·내보내기를 진행하세요.</p>:null}
      {latest.status==="DRAFT"?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`} button="저장한 초안 검토 후 승인"
        disabled={editing||latest.stale||!decisionReady} onSaved={refresh}>
        <input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="APPROVED"/>
        <label>확인 내용·승인 사유<textarea name="reason" required maxLength={10000}/></label>
        <label><span><input type="checkbox" required style={{width:"auto"}}/> 해당 민원의 사실·근거·지원 판단과 본문을 대조했습니다.</span></label>
      </CommandForm>:null}
      {["APPROVED","EXPORTED"].includes(latest.status)?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`} button="승인한 저장본 파일 내보내기"
        disabled={editing||latest.stale||!decisionReady} onSaved={download}>
        <input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="EXPORTED"/>
        <label>내보내기 목적·제출 경로 확인<textarea name="reason" required maxLength={10000}/></label>
      </CommandForm>:null}
    </section>:null}
    <details><summary>서류 수정·승인 이력 ({data.products.length}건)</summary>{data.products.map(p=><article className="work-item" key={p.id}>
      <b>버전 {p.revision} · {status[p.status]??p.status}</b><p>{date(p.created_at)}</p><p className="preserve">{p.content.text}</p>
    </article>)}</details>
  </>;
}

function ReportEditor({record,path,initial,revision,onDirty,onSaved,rebuild}:{record:CaseDetail;path:string;initial:string;revision:number;
  onDirty:(value:boolean)=>void;onSaved:()=>void;rebuild:()=>Promise<string>}) {
  const [text,setText]=useState(initial);const {dirty,setDirty}=useUnsavedChanges();
  const [building,setBuilding]=useState(false);const [error,setError]=useState<unknown>(null);
  const update=(value:string)=>{setText(value);setDirty(value!==initial);onDirty(value!==initial);};
  return <>
    <h3>편집 가능한 검토 초안</h3>
    <button type="button" disabled={building||record.status==="CLOSED"} onClick={async()=>{
      setBuilding(true);setError(null);try{update(await rebuild());}catch(e){setError(e);}finally{setBuilding(false);}
    }}>{building?"현재 기록 확인 중…":"현재 기록으로 초안 다시 구성"}</button>
    <p className="hint">다시 구성하면 편집창을 현재 민원·학교 조치·지원 판단·관련 근거로 교체합니다. 저장·승인은 별도로 진행합니다.</p>
    {error?<ErrorNotice error={error}/>:null}
    <ReferralEvidence record={record} onApply={citation=>update(`${text}\n\n${citation}`)}/>
    <CommandForm caseId={record.id} version={record.version} path={path} button="새 초안 버전 저장" externalDirty={dirty}
      disabled={building||record.status==="CLOSED"} onSaved={()=>{setDirty(false);onDirty(false);onSaved();}}
      transformValues={v=>({previous_revision:revision,reason:v.reason,content:{text,original:"",language:"ko"}})}>
      <label>이관 검토 서류 본문<textarea value={text} onChange={e=>update(e.target.value)} required rows={18} maxLength={40000}/></label>
      <label>수정·작성 사유<textarea name="reason" required maxLength={10000}/></label>
    </CommandForm>
  </>;
}
