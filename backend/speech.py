"""Azure AI Speech fast-transcription adapter. Consented audio leaves the server only through this module."""
import json
import os
import re

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .agents import Handler, ProviderFailure

API_VERSION = '2024-11-15'
UNKNOWN_SPEAKER = '미상'


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    id: str
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    # Automatic diarization numbers ("화자 1"), never a verified identity or role.
    speaker: str
    text: str
    confidence: float | None = None


class TranscriptResult(BaseModel):
    model_config = ConfigDict(extra='forbid')
    language: str | None
    duration_seconds: float | None
    segments: list[TranscriptSegment] = Field(min_length=1, max_length=2000)

    @model_validator(mode='after')
    def unique_segment_ids(self):
        ids = [segment.id for segment in self.segments]
        if len(set(ids)) != len(ids):
            raise ValueError('segment ids must be unique')
        return self


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class AzureSpeechAdapter:
    def __init__(self, key, endpoint, *, locale='ko-KR', api_version=API_VERSION, diarization=True,
                 client=None, timeout=120.0):
        if not endpoint.startswith('https://'):
            raise ValueError('Azure Speech endpoint must use https')
        self.key, self.endpoint, self.locale = key, endpoint.rstrip('/'), locale
        self.api_version, self.diarization = api_version, diarization
        self.client, self.timeout = client, timeout

    @property
    def metadata(self):
        return {'provider': 'azure-speech', 'api_version': self.api_version, 'locale': self.locale,
                'diarization': self.diarization}

    def transcribe(self, snapshot):
        audio = snapshot['audio']
        definition = {'locales': [self.locale]}
        if self.diarization:
            definition['diarization'] = {'enabled': True, 'maxSpeakers': 4}
        client = self.client or httpx.Client(timeout=httpx.Timeout(self.timeout, connect=10.0))
        try:
            response = client.post(
                f'{self.endpoint}/speechtotext/transcriptions:transcribe',
                params={'api-version': self.api_version},
                headers={'Ocp-Apim-Subscription-Key': self.key},
                files={'audio': (audio['filename'], audio['bytes'], audio['media_type'])},
                data={'definition': json.dumps(definition)})
        except (httpx.TimeoutException, httpx.TransportError):
            raise ProviderFailure('PROVIDER_CONNECTION', '음성 인식 서비스에 연결하지 못했습니다.', True) from None
        finally:
            if self.client is None:
                client.close()
        # Never echo the provider body: it may repeat parts of the recording.
        status = response.status_code
        if status == 429:
            raise ProviderFailure('PROVIDER_RATE_LIMIT', '음성 인식 서비스 요청 한도를 확인해 주세요.', True)
        if status >= 500:
            raise ProviderFailure('PROVIDER_UNAVAILABLE', '음성 인식 서비스가 일시적으로 응답하지 않습니다.', True)
        if status in (401, 403):
            raise ProviderFailure('PROVIDER_AUTH', '음성 인식 서비스의 키 또는 권한 설정을 확인해 주세요.')
        if status >= 400:
            raise ProviderFailure('STT_REQUEST_REJECTED', '음성 인식 요청이 거절되었습니다. 파일 형식과 길이를 확인해 주세요.')
        try:
            data = response.json()
            phrases = data.get('phrases') or []
        except (ValueError, AttributeError):
            raise ProviderFailure('PROVIDER_RESPONSE', '음성 인식 결과 형식을 확인할 수 없습니다.') from None
        segments = []
        for phrase in phrases:
            text = str(phrase.get('text') or '').strip()
            if not text:
                continue
            offset, length = phrase.get('offsetMilliseconds'), phrase.get('durationMilliseconds')
            if not number(offset) or not number(length):
                raise ProviderFailure('PROVIDER_RESPONSE', '구간 시각이 없는 음성 인식 결과입니다.')
            speaker = phrase.get('speaker')
            confidence = phrase.get('confidence')
            segments.append({
                'id': f'seg-{len(segments) + 1:04d}', 'start': round(offset / 1000, 3),
                'end': round((offset + length) / 1000, 3),
                'speaker': f'화자 {speaker}' if isinstance(speaker, int) and not isinstance(speaker, bool) else UNKNOWN_SPEAKER,
                'text': text, 'confidence': confidence if number(confidence) else None})
        if not segments:
            raise ProviderFailure('EMPTY_TRANSCRIPT', '음성에서 전사할 내용을 찾지 못했습니다.')
        duration = data.get('durationMilliseconds')
        locale = next((p.get('locale') for p in phrases if p.get('locale')), self.locale)
        return {'language': locale, 'duration_seconds': round(duration / 1000, 3) if number(duration) else None,
                'segments': segments}


def speech_handler(*, key=None, endpoint=None, region=None, locale=None, client=None):
    """Return the TRANSCRIBE_AUDIO handler, or None when Azure Speech is not configured on the server."""
    key = key or os.getenv('AZURE_SPEECH_KEY')
    endpoint = endpoint or os.getenv('AZURE_SPEECH_ENDPOINT')
    region = region or os.getenv('AZURE_SPEECH_REGION')
    if not endpoint and region:
        if not re.fullmatch(r'[a-z0-9]+', region):
            raise ValueError('AZURE_SPEECH_REGION must be a region id such as koreacentral')
        endpoint = f'https://{region}.api.cognitive.microsoft.com'
    if not key or not endpoint:
        return None
    adapter = AzureSpeechAdapter(
        key, endpoint, locale=locale or os.getenv('AZURE_SPEECH_LOCALE', 'ko-KR'),
        api_version=os.getenv('AZURE_SPEECH_API_VERSION', API_VERSION),
        diarization=os.getenv('AZURE_SPEECH_DIARIZATION', '1') == '1', client=client)
    return Handler('TRANSCRIBE_AUDIO', adapter.transcribe, TranscriptResult, version='azure-speech-fast-v1',
                   generation_mode='MODEL', metadata=adapter.metadata)
