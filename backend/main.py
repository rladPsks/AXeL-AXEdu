from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from agent.workflow import (
    complete_task,
    create_case,
    generate_support_report,
    get_case_snapshot,
    get_case_evidence,
    get_case_explanation,
    request_support,
    review_case_history,
)
from db import init_db, list_cases

from .schemas import (
    CaseCreateRequest,
    CaseSnapshotResponse,
    SupportRequestCreate,
    TaskCompleteRequest,
)


def _frontend_origins() -> list[str]:
    raw = os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    )
    return [x.strip() for x in raw.split(",") if x.strip()]


def create_app() -> FastAPI:
    init_db()
    app = FastAPI(
        title="AXeL School Complaint Agent API",
        version="0.1.0",
        description=(
            "학교 민원 사건 생성, Agent 업무 생성, 교직원 회신, 지원 요청, "
            "반복 맥락 검토 및 지원 보고서 초안을 제공하는 서비스 API"
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_frontend_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/cases", response_model=CaseSnapshotResponse, status_code=201)
    def create_case_endpoint(body: CaseCreateRequest):
        try:
            return create_case(body.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/cases")
    def list_cases_endpoint() -> dict:
        return {"items": list_cases()}

    @app.get("/cases/{case_id}", response_model=CaseSnapshotResponse)
    def get_case_endpoint(case_id: str):
        try:
            return get_case_snapshot(case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/cases/{case_id}/tasks/{task_id}/complete", response_model=CaseSnapshotResponse)
    def complete_task_endpoint(case_id: str, task_id: str, body: TaskCompleteRequest):
        try:
            snapshot = get_case_snapshot(case_id)
            if not any(t["id"] == task_id for t in snapshot["tasks"]):
                raise ValueError("해당 사건의 업무를 찾을 수 없습니다.")
            return complete_task(task_id, body.result_text, actor=body.actor)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/cases/{case_id}/support", response_model=CaseSnapshotResponse, status_code=201)
    def request_support_endpoint(case_id: str, body: SupportRequestCreate):
        try:
            return request_support(
                case_id,
                requested_by=body.requested_by,
                support_type=body.support_type,
                note=body.note,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/cases/{case_id}/evidence")
    def evidence_endpoint(case_id: str) -> dict:
        try:
            return get_case_evidence(case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/cases/{case_id}/explanation")
    def explanation_endpoint(case_id: str) -> dict:
        try:
            return get_case_explanation(case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/cases/{case_id}/history-review")
    def history_review_endpoint(case_id: str) -> dict:
        try:
            return review_case_history(case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/cases/{case_id}/support-report")
    def support_report_endpoint(case_id: str) -> dict:
        try:
            return generate_support_report(case_id)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    return app


app = create_app()
