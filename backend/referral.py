"""Case-specific referral references; a search hit never confirms referral eligibility."""
import json
import re

from agent.citations import with_source_metadata
from agent.routing import load_school_duty_map, route_case


def find_referral_evidence(case, intake):
    from agent.retrieval import retrieve
    intake = dict(intake) if intake else {}
    workflow = json.loads(intake.get('workflow_json') or '{}')
    cls = json.loads(intake.get('classification_json') or '{}')
    raw = (workflow.get('multilingual') or {}).get('translated_text_ko') or intake.get('raw_text') or case['title']
    title = intake.get('complaint_type') or case['title']
    routing = route_case('fact_check', text=title+' '+raw, classification=cls)
    area = next((a for a in load_school_duty_map().get('areas', []) if a['id'] == routing.get('duty_area')), {})
    terms = list(area.get('keywords', []))
    if cls.get('nature') == 'INFRINGEMENT_REVIEW' or cls.get('infringement_flags') or area.get('id') == 'teacher_protection':
        terms += ['교육활동', '교권', '폭언', '모욕', '협박']
    if not terms:
        terms = [word for word in re.findall(r'[가-힣]{3,}', raw)
                 if word not in {'해주세요', '알려주세요', '부탁드립니다', '문의합니다', '요청합니다'}]
    query = title+' '+raw
    hits = with_source_metadata(retrieve(query, top_k=10, allowed_source_types={'official_manual', 'policy_plan'}))
    items = []
    for hit in hits:
        excerpt = str(hit.get('text') or '').strip()
        normalized = re.sub(r'\s+', '', excerpt)
        matched = [term for term in terms if re.sub(r'\s+', '', term) in normalized]
        # Unrelated material is excluded even if generic words such as "support"
        # made it a lexical search hit. Do not force a fixed number of citations.
        if not excerpt or not matched:
            continue
        location = hit.get('article') or hit.get('section_title') or hit.get('locator')
        if not location and hit.get('pdf_page'):
            location = f"PDF {hit['pdf_page']}쪽"
        if not location:
            continue
        external = any(word in excerpt for word in ('교육지원청', '교육청', '이관'))
        items.append({key: hit.get(key) for key in ('source_id', 'title', 'source_type', 'pdf_page',
            'printed_page', 'official_url', 'uploaded_filename', 'chunk_id', 'issuer', 'article', 'verification_status')})
        items[-1].update(location=location, excerpt=excerpt[:1800], external_support_mention=external,
            reason='민원 분야와 일치하는 표현: '+', '.join(dict.fromkeys(matched))+'. '+
                ('외부 기관 관련 문구의 적용 요건과 학교 선행 조치를 대조해야 합니다.' if external else
                 '학교 내부 대응 관련 자료이며 이 자료만으로 교육지원청 이관 요건을 충족한다고 볼 수 없습니다.'))
        if len(items) == 4:
            break
    return items


def report_citation(item):
    location = item.get('location') or item.get('article') or '위치 확인 필요'
    parts = [f"{item.get('title') or item.get('source_id')} · {location}",
        '출처 ID: '+str(item.get('source_id') or '미등록')]
    if item.get('uploaded_filename'):
        parts.append('원문 파일: '+item['uploaded_filename'])
    if item.get('official_url'):
        parts.append('원문 URL: '+item['official_url'])
    parts.append('자료 검수: '+('검수됨' if item.get('verification_status') in {'verified','corrected'} else '원문 검수 필요'))
    parts.append('인용: '+str(item.get('excerpt') or ''))
    parts.append('관련성 검토: '+str(item.get('reason') or '적용 요건 확인 필요'))
    return '\n'.join(parts)
