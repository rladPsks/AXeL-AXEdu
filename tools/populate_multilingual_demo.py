"""Add one fictional complaint per language and save an editable Korean translation draft."""
import argparse
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.seed_multilingual import SAMPLES, marker


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='https://axel-axedu-demo.onrender.com')
    args = parser.parse_args()
    token = None

    def call(path, body=None, key=None):
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        if key:
            headers['Idempotency-Key'] = key
        request = urllib.request.Request(args.base.rstrip('/') + path,
            data=json.dumps(body, ensure_ascii=False).encode() if body is not None else None, headers=headers)
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.load(response)

    token = call('/api/demo/login', {'account': 'admin'})['token']
    records = []
    cursor = ''
    while True:
        page = call('/api/cases?after=' + urllib.parse.quote(cursor))
        records.extend(page['items'])
        cursor = page.get('next_cursor')
        if not cursor:
            break
    receipts = []
    for sample in SAMPLES:
        found = [r for r in records if marker(sample) in r['title'] or r['id'] == 'demo-multilingual-'+sample['language']]
        if len(found) > 1:
            raise RuntimeError('Duplicate multilingual marker: ' + sample['language'])
        state = 'existing' if found else 'created'
        if found:
            cid = found[0]['id']
        else:
            result = call('/api/intakes', {'channel': 'homepage',
                'complainant_name': '가상보호자-'+sample['language'], 'student_name': '가상학생-'+sample['language'],
                'complaint_type': marker(sample), 'related_people': [],
                'incident_context': '다국어 가상 민원 시연 · 실제 인물·사건과 무관',
                'raw_text': sample['original']}, 'multilingual-demo-intake-v1-'+sample['language'])
            cid = result['case_id']
        intake = call(f'/api/cases/{cid}/intake')
        assert intake['raw_text'] == sample['original']
        path = f'/api/cases/{cid}/work-products/TRANSLATION'
        products = call(path)
        if not products['products']:
            case = call(f'/api/cases/{cid}')
            call(path, {'expected_version': case['version'], 'previous_revision': 0,
                'content': {'text': sample['korean'], 'original': sample['original'], 'language': sample['language']},
                'reason': '[가상 시연] 원문과 대조할 한국어 번역 예시 초안. 자동 번역 완료·사람 승인 결과가 아님.'},
                'multilingual-demo-translation-v1-'+sample['language'])
        products = call(path)['products']
        assert products and products[0]['content']['language'] == sample['language']
        assert products[0]['content']['original'] == sample['original']
        receipt = {'language': sample['label'], 'title': marker(sample), 'case_id': cid,
                   'state': state, 'translation_status': products[0]['status']}
        receipts.append(receipt)
        print(json.dumps(receipt, ensure_ascii=False), flush=True)
    assert len(receipts) == 3
    print('Verified: 3 original-language complaints with Korean translation drafts', flush=True)


if __name__ == '__main__':
    main()
