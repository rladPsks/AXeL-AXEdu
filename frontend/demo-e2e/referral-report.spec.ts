import { test, expect } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("referral evidence connects to an editable draft and revisions require fresh approval", async ({page,request},info)=>{
  const login=await request.post('/api/demo/login',{data:{account:'admin'}});
  const token=(await login.json()).token;
  const cid='demo-flow-20-17';
  const before=await request.get(`/api/cases/${cid}`,{headers:{Authorization:`Bearer ${token}`}});
  const version=(await before.json()).version;
  const decisions=await request.get(`/api/cases/${cid}/support-decisions`,{headers:{Authorization:`Bearer ${token}`}});
  const previous=(await decisions.json())[0];
  const decision=await request.post(`/api/cases/${cid}/support-decisions`,{
    headers:{Authorization:`Bearer ${token}`,'Idempotency-Key':crypto.randomUUID()},
    data:{expected_version:version,decision_type:'EXTERNAL_SUPPORT',reason:'[가상] 교직원 보호 전문 지원 필요성 검토',
      target:'관할 교육지원청 담당 부서 확인 필요',route:'학교 검토 후 공식 지원 문의',remaining_school_work:'학교 사실 확인과 교직원 보호 계속',
      observations:[{source_id:cid,kind:'UNVERIFIED',detail:'[가상] 지원 요건 확인 필요'}],
      input_refs:[{resource_type:'CASE',resource_id:cid,version}],supersedes_id:previous?.decision_id??null},
  });
  expect(decision.status()).toBe(201);
  await page.goto(`/cases/${cid}?tab=report`);
  await page.getByRole('button',{name:'김OO 교장 관리자',exact:true}).click();
  const body=page.getByRole('textbox',{name:'이관 검토 서류 본문',exact:true});
  await expect(body).toBeVisible();
  await page.getByRole('button',{name:'현재 기록으로 초안 다시 구성',exact:true}).click();
  await expect(body).toHaveValue(/이관 여부 미확정/);
  await page.getByRole('button',{name:'이 민원과 관련된 이관 근거 검색',exact:true}).click();
  await page.getByRole('button',{name:'이 근거를 편집 내용에 추가',exact:true}).first().click();
  await expect(body).toHaveValue(/학교 조치와 해당 민원의 연결 근거/);
  await expect(page.locator('form[data-dirty="true"]').filter({has:body})).toHaveCount(1);
  await body.fill((await body.inputValue()).replace('[담당자 작성 필요]','[가상] 학교 확인 기록과 보호 지원 필요성을 담당자가 대조합니다.'));
  const save=page.locator('form').filter({has:page.getByRole('button',{name:'새 초안 버전 저장',exact:true})});
  await save.getByLabel('수정·작성 사유',{exact:true}).fill('[가상] 원문·인용·학교 조치 대조');
  await save.getByRole('button',{name:'새 초안 버전 저장',exact:true}).click();
  const approve=page.locator('form').filter({has:page.getByRole('button',{name:'저장한 초안 검토 후 승인',exact:true})});
  await approve.getByLabel('확인 내용·승인 사유',{exact:true}).fill('[가상] 근거와 지원 판단 확인');
  await approve.getByRole('checkbox').check();
  await approve.getByRole('button',{name:'저장한 초안 검토 후 승인',exact:true}).click();
  const exportButton=page.getByRole('button',{name:'승인한 저장본 파일 내보내기',exact:true});
  await expect(exportButton).toBeEnabled();
  const revised=(await body.inputValue())+'\n[가상] 수정 후 내보내기 검증 문장';
  await body.fill(revised);
  await expect(exportButton).toBeDisabled();
  await save.getByLabel('수정·작성 사유',{exact:true}).fill('[가상] 승인 후 수정');
  await save.getByRole('button',{name:'새 초안 버전 저장',exact:true}).click();
  await expect(exportButton).toHaveCount(0);
  await approve.getByLabel('확인 내용·승인 사유',{exact:true}).fill('[가상] 수정된 본문 재검토');
  await approve.getByRole('checkbox').check();
  await approve.getByRole('button',{name:'저장한 초안 검토 후 승인',exact:true}).click();
  const exportForm=page.locator('form').filter({has:exportButton});
  await exportForm.getByLabel('내보내기 목적·제출 경로 확인',{exact:true}).fill('[가상] 시연 파일 확인');
  const download=page.waitForEvent('download');
  await exportButton.click();
  const artifact=await download;
  const path=info.outputPath('referral-report.md');await artifact.saveAs(path);
  expect(await readFile(path,'utf8')).toBe(revised);
});
