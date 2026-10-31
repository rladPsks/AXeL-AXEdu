import { describe, expect, it } from "vitest";
import { recommendSupport, type SupportContact } from "./recommendations";
const contacts: SupportContact[] = ["교장", "교감", "행정실장", "생활부장", "교무부장"].map((label,i) => ({id:String(i),label,user_id:String(i),substitute_id:null,support_contact_id:String(i)}));
const eligible = contacts.map(c => c.user_id);
describe("support references", () => {
 it("shows support roles rather than ranking the response team", () => {
 const result = recommendSupport({classification:{infringement_flags:["REVIEW"]},routing:null},contacts,eligible);
 expect(result.map(r => r.role)).toEqual(["생활부장", "교무부장"]);
 });
 it("excludes unavailable users and resolves legacy role labels", () => {
 const intake={classification:{},routing:{action_role:"LIFE",role_labels:{LIFE:"생활인성부장"}}};
 expect(recommendSupport(intake,contacts,eligible).map(r=>r.role)).toContain("생활부장");
 expect(recommendSupport(intake,contacts,["4"]).map(r=>r.user_id)).toEqual(["4"]);
 expect(recommendSupport(undefined,contacts,eligible)).toEqual([]);
 });
});
