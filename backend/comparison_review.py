"""Explicit two-case inputs, structured proposals and human review provenance."""
import json
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from .access import accessible_case, admin, authenticate, fail
from .commands import mutate
from .comparisons import settings
from .db import now, uid
from .files import file_access
from .models import Command, Identifier, Text

router=APIRouter()


class ComparisonFinding(BaseModel):
    model_config=ConfigDict(extra='forbid')
    category:Literal['NEW_FACT','NEW_EVIDENCE','UNANSWERED_FOLLOWUP','UNFULFILLED_ACTION','REPEATED_CONTENT','REPORTING_LANGUAGE','NEEDS_CONFIRMATION']
    assessment:Literal['FACT','CLAIM','UNVERIFIED']
    detail:str
    source_ids:list[str]


class ComparisonResult(BaseModel):
    model_config=ConfigDict(extra='forbid')
    summary:str
    findings:list[ComparisonFinding]
    missing_information:list[str]
    follow_up_questions:list[str]


class ScopedRef(BaseModel):
    model_config=ConfigDict(extra='forbid')
    case_id:Identifier
    resource_type:Literal['CASE','TASK','SUPPORT_REQUEST','FILE','DOCUMENT_VERSION']
    resource_id:Identifier
    version:int=Field(ge=1)


class InputCreate(Command):
    related_case_id:Identifier
    expected_related_version:int=Field(ge=1)
    source_refs:list[ScopedRef]=Field(min_length=2,max_length=20)


class HumanFinding(ComparisonFinding):
    detail:Text
    source_ids:list[Identifier]=Field(min_length=1,max_length=20)


class ReviewCreate(Command):
    input_id:Identifier
    reason:Text
    findings:list[HumanFinding]=Field(min_length=1,max_length=40)
    reviewed_run_id:Identifier|None=None
    supersedes_id:Identifier|None=None


def validate_citations(findings,sources):
    allowed={source['ref']['resource_id'] for source in sources}
    return all(item.source_ids and len(item.source_ids)==len(set(item.source_ids)) and
               all(source_id in allowed for source_id in item.source_ids) and item.detail.strip() for item in findings)


def input_access(db,actor,input_id):
    admin(actor)
    row=db.execute('SELECT i.* FROM comparison_inputs i JOIN cases c ON c.id=i.case_id WHERE i.id=? AND c.school_id=?',
                   (input_id,actor['school_id'])).fetchone()
    if row is None:
        fail(404,'COMPARISON_INPUT_NOT_FOUND','저장된 비교 자료를 찾을 수 없습니다.')
    accessible_case(db,actor,row['case_id'])
    accessible_case(db,actor,row['related_case_id'])
    saved=json.loads(row['snapshot'])
    for source in saved['sources']:
        if source['ref']['resource_type']=='FILE':
            file_access(db,actor,source['ref']['resource_id'])
        elif source['ref']['resource_type']=='DOCUMENT_VERSION':
            from .evidence import document_version
            document_version(db,actor,source['ref']['resource_id'])
    return {**saved,'id':row['id'],'case_id':row['case_id'],'related_case_id':row['related_case_id'],
            'case_version':row['case_version'],'related_case_version':row['related_case_version'],
            'requested_by':row['requested_by'],'created_at':row['created_at']}


def input_stale(db,actor,saved,ignore_anchor=False):
    current=accessible_case(db,actor,saved['case_id'])
    related=accessible_case(db,actor,saved['related_case_id'])
    return ((not ignore_anchor and current['version']!=saved['case_version']) or related['version']!=saved['related_case_version']
            or settings(db,actor['school_id'])!=saved['criteria'])


def fresh_input(db,actor,input_id):
    saved=input_access(db,actor,input_id)
    if input_stale(db,actor,saved):
        fail(409,'STALE_COMPARISON_INPUT','비교 민원이나 학교 기준이 변경되었습니다. 현재 자료로 비교를 다시 준비하세요.')
    return saved


def latest_review(db,case_id,related_case_id):
    return db.execute('SELECT * FROM comparison_reviews WHERE case_id=? AND related_case_id=? ORDER BY revision DESC LIMIT 1',
                      (case_id,related_case_id)).fetchone()


def review_access(db,actor,review_id):
    admin(actor)
    row=db.execute('SELECT r.* FROM comparison_reviews r JOIN cases c ON c.id=r.case_id WHERE r.id=? AND c.school_id=?',
                   (review_id,actor['school_id'])).fetchone()
    if row is None:
        fail(404,'COMPARISON_REVIEW_NOT_FOUND','비교 검토 기록을 찾을 수 없습니다.')
    saved=json.loads(row['snapshot'])
    input_access(db,actor,row['input_id'])
    if saved['reviewed_ai']:
        from .agents import run_access
        run_access(db,actor,saved['reviewed_ai']['run_id'])
    return {**saved,'id':row['id'],'case_id':row['case_id'],'related_case_id':row['related_case_id'],
            'revision':row['revision'],'input_id':row['input_id'],'recorded_case_version':row['recorded_case_version'],
            'related_case_version':row['related_case_version'],'recorded_by':row['recorded_by'],'created_at':row['created_at']}


def review_dependency_stale(db,actor,saved):
    latest=latest_review(db,saved['case_id'],saved['related_case_id'])
    return latest['id']!=saved['id'] or input_stale(db,actor,saved['input'],ignore_anchor=True)


def review_stale(db,actor,saved):
    return review_dependency_stale(db,actor,saved) or accessible_case(db,actor,saved['case_id'])['version']!=saved['recorded_case_version']


def fresh_review(db,actor,review_id):
    saved=review_access(db,actor,review_id)
    if review_stale(db,actor,saved):
        fail(409,'STALE_COMPARISON_REVIEW','민원이나 비교 검토가 변경되었습니다. 최신 자료를 검토해 새 기록을 남기세요.')
    return saved


@router.post('/api/cases/{case_id}/comparison-inputs',status_code=201)
def prepare_input(case_id:str,body:InputCreate,request:Request):
    def operation(db,actor,case):
        from .agents import InputRef,snapshot
        admin(actor)
        if case_id==body.related_case_id:
            fail(422,'SELF_CASE_RELATION','서로 다른 민원을 선택하세요.')
        related=accessible_case(db,actor,body.related_case_id)
        if related['version']!=body.expected_related_version:
            fail(409,'RELATED_VERSION_CONFLICT','비교 민원의 최신 버전을 확인하세요.')
        if {item.case_id for item in body.source_refs}!={case_id,body.related_case_id}:
            fail(422,'COMPARISON_SOURCE_SCOPE','비교할 두 민원에서 출처를 각각 선택하세요.')
        keys=[(item.resource_type,item.resource_id) for item in body.source_refs]
        if len(keys)!=len(set(keys)):
            fail(422,'DUPLICATE_COMPARISON_SOURCE','같은 출처를 중복 선택할 수 없습니다.')
        sources=[]
        for selected_case in (case,related):
            refs=[InputRef(**item.model_dump(exclude={'case_id'})) for item in body.source_refs if item.case_id==selected_case['id']]
            sources.extend(snapshot(db,actor,selected_case,refs)['sources'])
        saved={'sources':sources,'criteria':settings(db,actor['school_id'])}
        encoded=json.dumps(saved,ensure_ascii=False)
        if len(encoded.encode())>1024*1024:
            fail(413,'COMPARISON_INPUT_TOO_LARGE','선택한 비교 자료가 너무 큽니다.')
        input_id=uid()
        db.execute('INSERT INTO comparison_inputs(id,case_id,related_case_id,case_version,related_case_version,requested_by,snapshot,created_at) VALUES (?,?,?,?,?,?,?,?)',
                   (input_id,case_id,related['id'],case['version'],related['version'],actor['user_id'],encoded,now()))
        return {'comparison_input_id':input_id,'related_case_version':related['version']}
    return mutate(request,case_id,body,'COMPARISON_INPUT_PREPARED',operation,201,advance_case=False)


@router.get('/api/cases/{case_id}/comparison-inputs')
def inputs(case_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        accessible_case(db,actor,case_id)
        return [{**(saved:=input_access(db,actor,row['id'])),'stale':input_stale(db,actor,saved)}
                for row in db.execute('SELECT id FROM comparison_inputs WHERE case_id=? ORDER BY created_at DESC,id DESC',(case_id,)).fetchall()]


@router.post('/api/cases/{case_id}/comparison-reviews',status_code=201)
def record_review(case_id:str,body:ReviewCreate,request:Request):
    def operation(db,actor,case):
        admin(actor)
        saved_input=fresh_input(db,actor,body.input_id)
        if saved_input['case_id']!=case_id:
            fail(422,'COMPARISON_SOURCE_SCOPE','현재 민원의 비교 자료를 선택하세요.')
        previous=latest_review(db,case_id,saved_input['related_case_id'])
        if body.supersedes_id!=(previous['id'] if previous else None):
            fail(409,'COMPARISON_REVIEW_CHAIN','최신 비교 검토 기록을 확인하세요.')
        if not validate_citations(body.findings,saved_input['sources']):
            fail(422,'INVALID_COMPARISON_CITATION','검토 내용에 선택한 실제 출처를 지정하세요.')
        reviewed_ai=None
        if body.reviewed_run_id:
            from .agents import require_usable_result,run_access
            result=require_usable_result(db,actor,case,body.reviewed_run_id,'COMPARE_CASES')
            run,_=run_access(db,actor,body.reviewed_run_id)
            refs=json.loads(run['snapshot'])['sources']
            if len(refs)!=1 or refs[0]['ref']['resource_id']!=body.input_id:
                fail(422,'COMPARISON_RUN_MISMATCH','이 자료 묶음으로 검토한 AI 결과를 선택하세요.')
            reviewed_ai={'run_id':body.reviewed_run_id,'result':result}
        saved={'input':saved_input,'findings':[item.model_dump() for item in body.findings],'reason':body.reason,'reviewed_ai':reviewed_ai}
        encoded=json.dumps(saved,ensure_ascii=False)
        if len(encoded.encode())>1024*1024:
            fail(413,'COMPARISON_REVIEW_TOO_LARGE','검토 기록이 너무 큽니다.')
        review_id=uid()
        db.execute('INSERT INTO comparison_reviews(id,case_id,related_case_id,revision,supersedes_id,input_id,recorded_case_version,related_case_version,recorded_by,snapshot,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                   (review_id,case_id,saved_input['related_case_id'],previous['revision']+1 if previous else 1,body.supersedes_id,body.input_id,case['version']+1,saved_input['related_case_version'],actor['user_id'],encoded,now()))
        return {'comparison_review_id':review_id}
    return mutate(request,case_id,body,'CASE_COMPARISON_REVIEW_RECORDED',operation,201)


@router.get('/api/cases/{case_id}/comparison-reviews')
def reviews(case_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        admin(actor)
        accessible_case(db,actor,case_id)
        return [{**(saved:=review_access(db,actor,row['id'])),'stale':review_stale(db,actor,saved)}
                for row in db.execute('SELECT id FROM comparison_reviews WHERE case_id=? ORDER BY recorded_case_version DESC,id DESC',(case_id,)).fetchall()]


@router.get('/api/comparison-reviews/{review_id}')
def get_review(review_id:str,request:Request):
    with request.app.state.db.transaction() as db:
        actor=authenticate(db,request)
        saved=review_access(db,actor,review_id)
        return {**saved,'stale':review_stale(db,actor,saved)}
