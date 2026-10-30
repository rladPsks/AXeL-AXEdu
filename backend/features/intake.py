from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from agent.classify import classify_complaint
from agent.routing import route_case
from agent.rules import apply_rules
from backend.access import authenticate, fail
from backend.commands import command_identity, replay_command, save_command
from backend.db import audit, now, uid
from backend.notifications import enqueue

router = APIRouter()


class IntakeCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    channel: Literal["phone", "message", "visit", "ieodream", "homepage", "external_transfer", "other"]
    complainant_name: str = Field(min_length=1, max_length=120)
    student_name: str | None = Field(default=None, max_length=120)
    complaint_type: str = Field(min_length=1, max_length=120)
    raw_text: str = Field(min_length=1, max_length=10000)
    related_people: list[str] = Field(default_factory=list, max_length=20)
    incident_context: str | None = Field(default=None, max_length=4000)
    received_at: datetime | None = None


def _routing_domain(cls: dict) -> str:
    if cls.get("nature") in {"SAFETY", "INFRINGEMENT_REVIEW"} or cls.get("stage") == 4:
        return "complex_or_sensitive"
    if cls.get("domain_p55") == "생활지도/상담" and cls.get("needs_fact_check"):
        return "student_counseling"
    if cls.get("nature") == "COUNSEL":
        return "student_counseling"
    if cls.get("nature") == "INFO_REQUEST" or cls.get("is_informational"):
        return "simple_inquiry"
    return "fact_check"


def _handling_route(cls: dict) -> str:
    special = set(cls.get("special_codes") or [])
    risky = bool(cls.get("infringement_flags") or special.intersection({
        "VERBAL_ABUSE_REVIEW", "THREAT_REVIEW", "SAFETY_RISK"
    }))
    if cls.get("urgency") == "HIGH" or risky or cls.get("nature") in {"SAFETY", "INFRINGEMENT_REVIEW"}:
        return "ADMIN_REVIEW"
    if cls.get("nature") == "INFO_REQUEST" and not cls.get("needs_fact_check"):
        return "FRONT_DESK_RESOLVE"
    return "STAFF_OR_TEAM"


def _role_user(db, school_id: str, label: str | None):
    if not label:
        return None
    row = db.execute(
        "SELECT user_id,substitute_id FROM school_responsibilities "
        "WHERE school_id=? AND label=? AND active=1 ORDER BY id LIMIT 1",
        (school_id, label),
    ).fetchone()
    if row is None:
        return None
    user_id = row["user_id"]
    absence = db.execute(
        "SELECT substitute_id FROM staff_absences WHERE school_id=? AND user_id=? AND active=1 "
        "AND starts_at<=? AND ends_at>?",
        (school_id, user_id, now(), now()),
    ).fetchone()
    return absence["substitute_id"] if absence else user_id


def _create_initial_task(db, *, case_id: str, actor_id: str, assignee_id: str,
                         question: str, callback_needed: str):
    task_id = uid()
    db.execute(
        "INSERT INTO tasks(id,case_id,type,assignee_id,requester_id,question,callback_needed,status,reply,created_at) "
        "VALUES (?,?,?,?,?,?,?,'REQUESTED',NULL,?)",
        (task_id, case_id, "FACT_CHECK", assignee_id, actor_id, question,
         callback_needed if callback_needed in {"REQUIRED","NOT_REQUIRED","UNDECIDED"} else "UNDECIDED", now()),
    )
    db.execute("INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)", (case_id, assignee_id))
    enqueue(db, case_id, assignee_id, "TASK_CREATED", task_id, f"intake-task:{task_id}:created")
    return task_id


@router.post("/api/intakes", status_code=201)
def create_intake(body: IntakeCreate, request: Request):
    identity = command_identity(request, body)

    # Authenticate and check replay before external generation.
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        replay = replay_command(db, actor, identity)
        if replay is not None:
            return replay

    # Classification happens outside the SQLite write transaction.
    cls = apply_rules(classify_complaint(body.raw_text), [])
    cls["core_demand"] = cls.get("summary_for_teacher") or body.raw_text[:180]
    cls["handling_route"] = _handling_route(cls)
    cls["escalation_level"] = 2 if cls["handling_route"] == "ADMIN_REVIEW" else 1
    routing = route_case(_routing_domain(cls), text=body.raw_text, classification=cls)

    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        replay = replay_command(db, actor, identity)
        if replay is not None:
            return replay

        owner = db.execute(
            "SELECT user_id FROM memberships WHERE school_id=? AND role='ADMIN' AND active=1 "
            "ORDER BY CASE WHEN user_id='admin' THEN 0 ELSE 1 END, user_id LIMIT 1",
            (actor["school_id"],),
        ).fetchone()
        if owner is None:
            fail(409, "NO_ACTIVE_ADMIN", "민원대응 총괄로 지정할 활성 관리자가 없습니다.")

        case_id = uid()
        title = f"[{body.complaint_type}] {body.raw_text.strip().replace(chr(10), ' ')[:60]}"
        received_at = (body.received_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
        source_type = "EXTERNAL_TRANSFER" if body.channel == "external_transfer" else "DIRECT"

        db.execute(
            "INSERT INTO cases(id,school_id,title,owner_id,status,version) VALUES (?,?,?,?, 'OPEN', 1)",
            (case_id, actor["school_id"], title, owner["user_id"]),
        )
        db.execute(
            "INSERT INTO case_intakes(case_id,received_at,channel,complainant_name,student_name,"
            "complaint_type,related_people,incident_context,raw_text,source_type,classification_json,"
            "routing_json,created_by,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                case_id, received_at, body.channel, body.complainant_name, body.student_name,
                body.complaint_type, json.dumps(body.related_people, ensure_ascii=False),
                body.incident_context, body.raw_text, source_type,
                json.dumps(cls, ensure_ascii=False), json.dumps(routing, ensure_ascii=False),
                actor["user_id"], now(),
            ),
        )
        db.execute("INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)", (case_id, actor["user_id"]))
        db.execute("INSERT OR IGNORE INTO case_participants(case_id,user_id) VALUES (?,?)", (case_id, owner["user_id"]))

        task_ids = []
        if cls["handling_route"] == "STAFF_OR_TEAM":
            labels = routing.get("role_labels") or {}
            primary_label = labels.get(routing.get("action_role"))
            primary_user = _role_user(db, actor["school_id"], primary_label) or owner["user_id"]
            question = "\n".join(cls.get("needs_fact_check") or ["민원 핵심 사실과 맥락을 확인해 주세요."])
            task_ids.append(_create_initial_task(
                db,
                case_id=case_id,
                actor_id=actor["user_id"],
                assignee_id=primary_user,
                question=question,
                callback_needed=routing.get("callback_needed", "UNDECIDED"),
            ))
            for role in routing.get("collaborators") or []:
                collaborator_label = labels.get(role)
                collaborator_user = _role_user(db, actor["school_id"], collaborator_label)
                if collaborator_user and collaborator_user != primary_user:
                    task_ids.append(_create_initial_task(
                        db,
                        case_id=case_id,
                        actor_id=actor["user_id"],
                        assignee_id=collaborator_user,
                        question=f"{collaborator_label or '협조 담당'} 사실 확인: {question}",
                        callback_needed=routing.get("callback_needed", "UNDECIDED"),
                    ))

        audit(db, actor, case_id, "CASE_INTAKE_CREATED", 1, {
            "channel": body.channel,
            "complaint_type": body.complaint_type,
            "handling_route": cls["handling_route"],
            "urgency": cls.get("urgency"),
            "owner_id": owner["user_id"],
            "task_ids": task_ids,
        })
        response = {
            "case_id": case_id,
            "version": 1,
            "classification": cls,
            "routing": routing,
        }
        save_command(db, actor, identity, response, 201)
        return response


@router.get("/api/cases/{case_id}/intake")
def get_intake(case_id: str, request: Request):
    from backend.access import accessible_case
    with request.app.state.db.transaction() as db:
        actor = authenticate(db, request)
        accessible_case(db, actor, case_id)
        row = db.execute("SELECT * FROM case_intakes WHERE case_id=?", (case_id,)).fetchone()
        if row is None:
            fail(404, "INTAKE_NOT_FOUND", "접수 기록을 찾을 수 없습니다.")
        item = dict(row)
        item["related_people"] = json.loads(item["related_people"])
        item["classification"] = json.loads(item.pop("classification_json")) if item.get("classification_json") else None
        item["routing"] = json.loads(item.pop("routing_json")) if item.get("routing_json") else None
        return item
