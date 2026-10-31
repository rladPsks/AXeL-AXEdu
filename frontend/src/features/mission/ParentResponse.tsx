import { useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useScope, useSession } from "../../app/providers";
import type { CaseDetail } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { ErrorNotice, date } from "../../shared/ui";
import { useUnsavedChanges } from "../../shared/useUnsavedChanges";

type Product={id:string;revision:number;status:string;stale:boolean;content:{text:string};created_at:string};
type ResponseData={initial:{text:string};products:Product[]};
const states:Record<string,string>={DRAFT:"저장한 초안 · 검토 전",APPROVED:"저장본 검토·승인",DELIVERED:"실제 전달 기록 있음"};

export function ParentResponse({record}:{record:CaseDetail}) {
  const {api}=useSession();const scope=useScope();const queries=useQueryClient();const [editing,setEditing]=useState(false);
  const path=`/api/cases/${record.id}/work-products/RESPONSE`;
  const query=useQuery({queryKey:["work-products",...scope,record.id,"RESPONSE",record.version],
    queryFn:({signal})=>api.get<ResponseData>(path,signal)});
  if(query.isPending)return <p role="status">저장한 학부모 답변을 불러오는 중…</p>;
  if(query.error)return <ErrorNotice error={query.error}/>;
  const latest=query.data.products[0];
  const refresh=()=>{setEditing(false);void query.refetch();void queries.invalidateQueries({queryKey:["full-history",...scope,record.id]});};
  return <>
    <h2>학부모에게 보낼 답변 초안</h2>
    <p>아래에 답변을 직접 작성하세요. AI 초안 없이도 저장하고 나중에 이어서 수정할 수 있습니다.</p>
    {latest?<p>{states[latest.status]??latest.status} · 버전 {latest.revision}{editing?" · 편집 내용 미저장":""}</p>:<p className="hint">아직 저장한 답변이 없습니다. 빈 편집창에서 작성해 주세요.</p>}
    {latest?.stale?<p className="notice">민원 기록이 변경되었습니다. 답변 내용을 확인하고 새 초안을 저장하세요.</p>:null}
    <ResponseEditor key={latest?.id??"new"} record={record} path={path} initial={latest?.content.text??""}
      suggestion={query.data.initial.text} revision={latest?.revision??0} onDirty={setEditing} onSaved={refresh}/>
    {latest&&record.status!=="CLOSED"?<details className="work-item"><summary>저장본 검토·승인·실제 전달 기록</summary>
      <p className="hint">초안 저장이나 복사는 학부모에게 전송하지 않습니다. 실제 전달한 경우에만 전달 기록을 남기세요.</p>
      {editing?<p>편집한 답변을 먼저 새 초안으로 저장해 주세요.</p>:null}
      {latest.status==="DRAFT"?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`}
        button="저장한 답변 검토 후 승인" disabled={editing||latest.stale} onSaved={refresh}>
        <input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="APPROVED"/>
        <label>확인 내용·승인 사유<textarea name="reason" required maxLength={10000}/></label>
      </CommandForm>:null}
      {latest.status==="APPROVED"?<CommandForm caseId={record.id} version={record.version} path={`${path}/transition`}
        button="실제 전달 사실 기록" disabled={editing||latest.stale} onSaved={refresh}>
        <input type="hidden" name="revision" value={latest.revision}/><input type="hidden" name="action" value="DELIVERED"/>
        <label>실제로 전달한 경로·시각·확인 근거<textarea name="reason" required maxLength={10000}/></label>
      </CommandForm>:null}
    </details>:null}
    <details><summary>작성·수정 이력 ({query.data.products.length}건)</summary>{query.data.products.map(p=><article className="work-item" key={p.id}>
      <b>버전 {p.revision} · {states[p.status]??p.status}</b><p>{date(p.created_at)}</p><p className="preserve">{p.content.text}</p>
    </article>)}</details>
  </>;
}

function ResponseEditor({record,path,initial,suggestion,revision,onDirty,onSaved}:{record:CaseDetail;path:string;initial:string;suggestion:string;revision:number;
  onDirty:(value:boolean)=>void;onSaved:()=>void}) {
  const [text,setText]=useState(initial);const {dirty,setDirty}=useUnsavedChanges();
  const [copied,setCopied]=useState(false);const [error,setError]=useState<unknown>(null);
  const update=(value:string)=>{setText(value);setDirty(value!==initial);onDirty(value!==initial);setCopied(false);};
  const download=()=>{const url=URL.createObjectURL(new Blob([text],{type:"text/plain;charset=utf-8"}));
    const a=document.createElement("a");a.href=url;a.download=`학부모_답변초안_${record.id}.txt`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
  return <>
    <CommandForm caseId={record.id} version={record.version} path={path} button="학부모 답변 초안 저장"
      externalDirty={dirty} disabled={record.status==="CLOSED"}
      onSaved={()=>{setDirty(false);onDirty(false);onSaved();}}
      transformValues={v=>({previous_revision:revision,reason:v.reason||"학부모 답변 직접 작성·수정",content:{text,original:"",language:"ko"}})}>
      <label>학부모에게 보낼 답변<textarea required rows={14} maxLength={40000} value={text} onChange={e=>update(e.target.value)}
        placeholder="학부모에게 안내할 내용을 직접 작성하세요. 확인된 사실과 학교의 안내 사항을 적어 주세요."/></label>
      <label>작성·수정 메모 (선택)<input name="reason" maxLength={10000}/></label>
    </CommandForm>
    <div className="actions">
      <button type="button" disabled={!text.trim()} onClick={async()=>{try{await navigator.clipboard.writeText(text);setCopied(true);setError(null);}catch{setError(new Error("복사하지 못했습니다. 본문을 선택해 복사하거나 초안 파일을 내려받으세요."));}}}>현재 답변 복사</button>
      <button type="button" disabled={!text.trim()} onClick={download}>초안 텍스트 파일 받기</button>
    </div>
    {copied?<p role="status">현재 편집한 답변을 복사했습니다.</p>:null}{error?<ErrorNotice error={error}/>:null}
    <details className="work-item"><summary>기존 참고 초안 (선택)</summary>
      {suggestion?<><p className="preserve">{suggestion}</p><button type="button" disabled={record.status==="CLOSED"} onClick={()=>update(text?`${text}\n\n${suggestion}`:suggestion)}>참고 초안을 편집창에 추가</button></>:<p>저장된 참고 초안이 없습니다. 직접 작성은 바로 가능합니다.</p>}
      <Link to={`/cases/${record.id}?tab=agent-review`}>AI 지원 검토 열기 →</Link>
    </details>
  </>;
}
