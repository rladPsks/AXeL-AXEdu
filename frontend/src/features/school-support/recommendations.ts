import { dutyName } from "../../shared/names";

export type SupportContact = { id: string; label: string; user_id: string; substitute_id: string | null; support_contact_id: string | null };
export type SupportIntake = {
  classification: { category?: string; urgency?: string; nature?: string; infringement_flags?: string[] } | null;
  routing: { action_role?: string; approver?: string; role_labels?: Record<string, string>; duty_label?: string } | null;
};

export function recommendSupport(intake: SupportIntake | undefined, contacts: SupportContact[], eligible: string[]) {
  if (!intake) return [];
  const cls = intake.classification ?? {};
  const routing = intake.routing ?? {};
  const risk = !!cls.infringement_flags?.length || cls.nature === "INFRINGEMENT_REVIEW";
  const urgent = cls.urgency === "HIGH" || cls.nature === "SAFETY";
  const primary = dutyName(routing.role_labels?.[routing.action_role ?? ""] ?? "");
  const order = risk || urgent ? ["교감", "교장", primary, "생활부장"]
    : cls.category === "ADMIN" || /시설|납부|급식비|제증명/.test(routing.duty_label ?? "")
      ? ["행정실장", primary, "업무지원", "교감"]
      : [primary, "교무부장", "업무지원", "교감"];
  const ranked: { user_id: string; role: string; reason: string }[] = [];
  for (const role of order.filter(Boolean)) {
    for (const contact of contacts.filter((c) => dutyName(c.label) === role)) {
      const id = contact.support_contact_id;
      if (!id || !eligible.includes(id) || ranked.some((r) => r.user_id === id)) continue;
      ranked.push({ user_id: id, role,
        reason: id !== contact.user_id ? `${role} 담당 부재 등을 반영한 지원 연결 대상`
          : risk ? "교육활동 침해 소지에 대한 공동 대응·이관 검토"
          : urgent ? "긴급 상황의 안전 확보와 학교 대응 조정"
          : `학교 업무분장의 ${role} 담당 · ${routing.duty_label ?? "민원 처리"} 지원` });
    }
  }
  return ranked.slice(0, 3);
}
