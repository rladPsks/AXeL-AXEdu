import { personName } from "../../shared/names";
import { useScope, useSession } from "../../app/providers";
import { useQuery } from "@tanstack/react-query";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, Empty, label, date } from "../../shared/ui";
import { Schedule } from "./Schedule";

export function TeacherTasks({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { api, session } = useSession();
  const scope = useScope();
  const brief = useQuery({
    queryKey: ["intake", ...scope, record.id],
    enabled: session.role === "ADMIN",
    queryFn: ({ signal }) => api.get<{ workflow: { teacher_card?: { summary: string; action: string } } | null }>(`/api/cases/${encodeURIComponent(record.id)}/intake`, signal),
  });
  const card = brief.data?.workflow?.teacher_card;
  return (
    <>
      <div className="section-heading">
        <h2>교사에게 요청한 업무</h2>
        <span>{record.tasks.length}건</span>
      </div>
      <p className="hint">확인·상담을 요청해도 민원 총괄자는 유지됩니다.</p>
      {record.tasks.length === 0 ? (
        <Empty>
          아직 요청한 업무가 없습니다. 필요한 사실 확인이나 상담을 요청하세요.
        </Empty>
      ) : (
        record.tasks.map((task) => (
          <article className="work-item" key={task.id}>
            <div className="item-top">
              <strong>{label(task.type)}</strong>
              <Badge value={task.status} />
            </div>
            <p className="preserve">{task.question}</p>
            <p className="meta">
              수행자 {personName(task.assignee_id)} ·{" "}
              {label(task.callback_needed)} · {date(task.created_at)}
            </p>
            {task.reply ? (
              <blockquote className="preserve">{task.reply}</blockquote>
            ) : null}
            <Schedule
              task={task}
              version={record.version}
              closed={record.status === "CLOSED"}
            />
            {record.status === "OPEN" &&
            task.status !== "COMPLETED" &&
            session.role === "ADMIN" ? (
              <details className="new-request">
                <summary>업무 수행자 변경</summary>
                <CommandForm
                  caseId={record.id}
                  version={record.version}
                  path={`/api/tasks/${encodeURIComponent(task.id)}/reassign`}
                  button="수행자 변경 저장"
                >
                  <label>
                    새 수행자
                    <select required name="assignee_id" defaultValue="">
                      <option value="" disabled>
                        구성원 선택
                      </option>
                      {members
                        .filter((person) => person.user_id !== task.assignee_id)
                        .map((person) => (
                          <option key={person.user_id} value={person.user_id}>
                            {personName(person.user_id)}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    수행자 변경 사유
                    <textarea required name="reason" maxLength={10000} />
                  </label>
                </CommandForm>
              </details>
            ) : null}
            {record.status === "OPEN" &&
            task.assignee_id === session.user_id &&
            task.status !== "COMPLETED" ? (
              <CommandForm
                caseId={record.id}
                version={record.version}
                path={`/api/tasks/${encodeURIComponent(task.id)}`}
                method="PATCH"
                button="회신 저장"
              >
                <label>
                  처리 상태
                  <select name="status">
                    <option value="COMPLETED">완료 회신</option>
                    <option
                      disabled={task.status !== "REQUESTED"}
                      value="ACKNOWLEDGED"
                    >
                      확인함
                    </option>
                  </select>
                </label>
                <label>
                  회신 내용
                  <textarea
                    name="reply"
                    required
                    maxLength={10000}
                    placeholder="확인한 내용과 필요한 후속 조치를 적어 주세요."
                  />
                </label>
              </CommandForm>
            ) : null}
          </article>
        ))
      )}
      {session.role === "ADMIN" && record.status === "OPEN" ? (
        <details className="new-request" open>
          <summary>새 업무 요청</summary>
          <CommandForm
            caseId={record.id}
            version={record.version}
            path={`/api/cases/${encodeURIComponent(record.id)}/tasks`}
            button="업무 요청 보내기"
          >
            <div className="form-row">
              <label>
                요청 종류
                <select name="type">
                  {["FACT_CHECK", "COUNSEL", "CALLBACK", "FOLLOW_UP"].map(
                    (t) => (
                      <option key={t} value={t}>
                        {label(t)}
                      </option>
                    ),
                  )}
                </select>
              </label>
              <label>
                수행자
                <select name="assignee_id" required defaultValue="">
                  <option value="" disabled>
                    구성원 선택
                  </option>
                  {members.map((m) => (
                    <option key={m.user_id} value={m.user_id}>
                      {personName(m.user_id)} ({label(m.role)})
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              확인할 내용
              <textarea key={brief.dataUpdatedAt} name="question" required maxLength={10000} defaultValue={card ? `${card.summary}\n\n필요한 행동: ${card.action}` : ""} />
            </label>
            <label>
              콜백 필요 여부
              <select name="callback_needed" defaultValue="UNDECIDED">
                {["UNDECIDED", "REQUIRED", "NOT_REQUIRED"].map((t) => (
                  <option key={t} value={t}>
                    {label(t)}
                  </option>
                ))}
              </select>
            </label>
          </CommandForm>
        </details>
      ) : null}
    </>
  );
}
