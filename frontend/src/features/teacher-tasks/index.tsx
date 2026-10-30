import { useSession } from "../../app/providers";
import type { CaseDetail, Member } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { Badge, Empty, label, date } from "../../shared/ui";

export function TeacherTasks({
  record,
  members,
}: {
  record: CaseDetail;
  members: Member[];
}) {
  const { session } = useSession();
  return (
    <>
      <div className="section-heading">
        <h2>교사에게 요청한 업무</h2>
        <span>{record.tasks.length}건</span>
      </div>
      <p className="hint">확인·상담을 요청해도 사건 총괄자는 유지됩니다.</p>
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
              수행자 {task.assignee_id} · {label(task.callback_needed)} ·{" "}
              {date(task.created_at)}
            </p>
            {task.reply ? (
              <blockquote className="preserve">{task.reply}</blockquote>
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
                      {m.user_id} ({label(m.role)})
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label>
              확인할 내용
              <textarea name="question" required maxLength={10000} />
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
