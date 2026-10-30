import { useSession } from "../../app/providers";
import type { Task } from "../../lib/api/types";
import { CommandForm } from "../../shared/CommandForm";
import { koreanTime, localInput } from "../../shared/dates";
import { date } from "../../shared/ui";

export function Schedule({
  task,
  version,
  closed,
}: {
  task: Task;
  version: number;
  closed: boolean;
}) {
  const { session } = useSession();
  const schedule = task.schedule;
  return (
    <>
      {schedule?.reason ? (
        <p className="hint">일정 조정 사유 {schedule.reason}</p>
      ) : null}
      <p className="meta">
        예정{" "}
        {schedule?.planned_start_at ? date(schedule.planned_start_at) : "미정"}{" "}
        · 기한 {schedule?.due_at ? date(schedule.due_at) : "미정"}
      </p>
      {!closed &&
      task.status !== "COMPLETED" &&
      (session.role === "ADMIN" || task.assignee_id === session.user_id) ? (
        <details className="new-request">
          <summary>업무 일정 조정</summary>
          <CommandForm
            caseId={task.case_id}
            version={version}
            path={`/api/tasks/${encodeURIComponent(task.id)}/schedule`}
            method="PUT"
            button="일정 저장"
            transformValues={(values) => ({
              ...values,
              planned_start_at: koreanTime(values.planned_start_at),
              due_at: koreanTime(values.due_at),
            })}
          >
            <div className="form-row">
              <label>
                예정 일시 (한국시간)
                <input
                  type="datetime-local"
                  name="planned_start_at"
                  defaultValue={localInput(schedule?.planned_start_at)}
                />
              </label>
              <label>
                완료 기한 (한국시간)
                <input
                  type="datetime-local"
                  name="due_at"
                  defaultValue={localInput(schedule?.due_at)}
                />
              </label>
            </div>
            <label>
              일정 조정 사유
              <textarea required name="reason" maxLength={10000} />
            </label>
          </CommandForm>
        </details>
      ) : null}
    </>
  );
}
