"""Gemini 기반 민폐도 산출.

민폐도는 어디서도 측정해 주지 않는 값이라 모델이 추론한다.
- 결정론에 가깝게: temperature 0 + 고정 루브릭 + responseSchema
- 장소별 디스크 캐시 (정적 속성만 쓰므로 재호출이 거의 없다)
- 백그라운드 스레드, 실패 시 규칙 기반(ai.score_nuisance) 으로 폴백
- 사용자 키가 없으면 CoolMap 서버(supabase/functions/ai)를 거친다.
  서버에도 같은 루브릭이 있으므로 RUBRIC·SCHEMA·_describe 를 고치면 그쪽도 고친다.
"""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

from .. import secrets
from . import backend
from ..paths import cache_dir

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-2.0-flash"]

RUBRIC = """당신은 '민폐도' 평가자입니다.
민폐도 = 볼일 없이 더위만 피하러 들어가 오래 머무를 때 느끼는 눈치·부담 (0~100 정수).
낮을수록 마음 편히 오래 있을 수 있습니다.

**가장 중요한 원칙: 공식 지정 무더위쉼터라 하더라도, 시설의 '본래 목적'과
방문 목적(더위 피하기)이 어긋나면 실제로는 눈치가 보입니다.**
공식 지정 여부만 보고 무조건 낮게 주지 마세요. 그 공간에 낯선 사람이 볼일 없이
한 시간 앉아 있을 때 직원과 다른 이용객이 어떻게 느낄지를 기준으로 판단하세요.

유형별 현실적인 기준:
  · 도서관, 주민센터·행정복지센터, 복지관, 공공 라운지
      → 누구나 머무르라고 만든 공간. 10~25.
  · 야외 그늘 쉼터·정자
      → 애초에 쉬는 곳. 0~15.
  · 버스정류장 (그늘막 정류장 · 냉방되는 스마트쉼터 포함)
      → 길가의 공용 시설이라 누가 서 있든 아무도 신경 쓰지 않는다. 0~10.
        다만 좁고 버스를 기다리는 사람이 오가므로 장시간 점유는 피해야 한다.
        직원도 안내데스크도 없으니 그런 조언은 하지 말 것.
  · 대형마트
      → 매장 안 고객 휴게공간은 비교적 자유롭지만 상업시설이다. 40~60.
  · 경로당·마을회관
      → 공식 쉼터여도 사실상 지역 어르신들의 사랑방. 외부인이나 젊은 층이
        불쑥 들어가 오래 있기는 어색하다. 40~60.
  · 은행·새마을금고·농협 등 금융기관
      → 창구 업무를 보러 오는 곳. 볼일 없이 로비 소파에서 바람만 쐬고 있으면
        직원 시선이 분명히 느껴진다. 짧게 더위를 식히는 정도만 무난하다. 55~75.
  · 편의점·상점·카페
      → 구매가 사실상 전제. 65~85.
  · 병원 로비
      → 환자 동선이라 배려가 필요하다. 50~70.

난방(한파 대피) 모드에서는 폭염 때와 사회적 맥락이 조금 다릅니다.
한파는 생명과 직결된다는 인식이 있어 공공시설의 수용 태도가 더 관대하고,
특히 경로당·주민센터는 한파 시 적극적으로 개방합니다. 같은 시설이라도
난방 모드에서는 냉방 모드보다 5~15점 낮게 잡으세요.
다만 은행·상점처럼 본래 목적이 다른 곳은 여전히 부담이 큽니다.

stay_minutes 는 '이 정도면 무난하다'고 볼 수 있는 권장 체류 시간(분)입니다.
민폐도가 높으면 짧게(10~30분), 낮으면 길게(2~5시간) 잡으세요.
reason 은 한 문장, tips 는 실용적인 조언 2~3개. 모두 한국어 존댓말."""

SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "stay_minutes": {"type": "integer"},
        "reason": {"type": "string"},
        "tips": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["score", "stay_minutes", "reason", "tips"],
}


def _capacity_band(n: int) -> str:
    """수용 인원을 구간으로 뭉갠다 (캐시 재사용률을 높이기 위해)."""
    for limit, label in ((20, "소형(20명 이하)"), (60, "중형(20~60명)"),
                         (200, "대형(60~200명)")):
        if n <= limit:
            return label
    return "초대형(200명 초과)"


def _profile(place, mode: str) -> dict:
    """민폐도를 좌우하는 '시설 성격'만 뽑는다. 개별 시설명은 제외한다."""
    return {
        "mode": "냉방(폭염 대피)" if mode == "cooling" else "난방(한파 대피)",
        "category": place.category_label,
        "official": "예" if place.official else "아니오",
        "purchase": "예" if place.purchase_required else "아니오",
        "capacity": _capacity_band(place.capacity),
        "always_open": "예" if place.always_open else "아니오",
        "quiet": round(place.quiet, 1),
    }


def _describe(place, mode: str) -> str:
    p = _profile(place, mode)
    return (
        f"시설 유형: {p['category']}\n"
        f"이용 목적: {p['mode']} 쉼터\n"
        f"공식 지정 무더위·한파 쉼터: {p['official']}\n"
        f"음료·물품 구매 필요: {p['purchase']}\n"
        f"규모: {p['capacity']}\n"
        f"24시간 개방: {p['always_open']}\n"
        f"정숙도(0~1): {p['quiet']}\n\n"
        "개별 시설이 아니라 이 '유형'의 일반적인 특성을 기준으로 평가하세요."
    )


def _cache_key(place, mode: str) -> str:
    """시설 유형 단위 캐시 키.

    쉼터가 6만 곳이라 장소마다 호출하면 감당이 안 된다.
    민폐도는 개별 시설명이 아니라 '어떤 종류의 공간인가'로 거의 결정되므로,
    유형·공식지정·구매필요·규모 조합으로 캐시해 호출 수를 수십 건으로 줄인다.
    """
    p = _profile(place, mode)
    raw = "|".join(f"{k}={v}" for k, v in sorted(p.items()))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


class NuisanceAI(QObject):
    """장소별 민폐도를 Gemini 로 산출. 캐시 우선, 없으면 백그라운드 요청."""

    scored = Signal(str)          # place_id

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}
        self._pending: set[str] = set()
        self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="gemini")
        self._dir = cache_dir("nuisance")
        self._enabled = True
        self._error = ""
        self._calls = 0
        self._model = MODELS[0]

    # -- 상태 --------------------------------------------------------------
    @property
    def own_key(self) -> bool:
        return bool(secrets.gemini_key())

    @property
    def use_backend(self) -> bool:
        """사용자 키가 없으면 CoolMap 서버를 거친다."""
        return not self.own_key and backend.enabled()

    @property
    def has_key(self) -> bool:
        return self.own_key or backend.enabled()

    @property
    def enabled(self) -> bool:
        return self._enabled and self.has_key

    def set_enabled(self, on: bool) -> None:
        self._enabled = on

    @property
    def error(self) -> str:
        return self._error

    @property
    def calls(self) -> int:
        return self._calls

    @property
    def model(self) -> str:
        return self._model

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    # -- 조회 --------------------------------------------------------------
    def get(self, place, mode: str) -> dict | None:
        """캐시된 결과. 없으면 백그라운드 요청 후 None."""
        if not self.enabled:
            return None
        key = _cache_key(place, mode)
        with self._lock:
            hit = self._mem.get(key)
            if hit is not None:
                return hit
            if key in self._pending:
                return None

        path = self._dir / f"{key}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            with self._lock:
                self._mem[key] = data
            return data
        except (OSError, ValueError):
            pass

        with self._lock:
            self._pending.add(key)
        self._pool.submit(self._fetch, key, place, mode)
        return None

    def _fetch(self, key: str, place, mode: str) -> None:
        if self.use_backend:
            result = self._ask_backend(place, mode)
        else:
            result = self._ask_gemini(place, mode)

        if result is not None:
            result = _sanitize(result)
            try:
                (self._dir / f"{key}.json").write_text(
                    json.dumps(result, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass
            with self._lock:
                self._mem[key] = result

        with self._lock:
            self._pending.discard(key)
        self.scored.emit(place.id)

    def _ask_backend(self, place, mode: str) -> dict | None:
        try:
            d = backend.call("ai", {"task": "nuisance", "profile": _profile(place, mode)})
            self._model = d.get("model") or self._model
            self._calls += 1
            self._error = ""
            return d.get("result")
        except Exception as exc:
            self._error = f"{type(exc).__name__}: {exc}"
            return None

    def _ask_gemini(self, place, mode: str) -> dict | None:
        payload = {
            "systemInstruction": {"parts": [{"text": RUBRIC}]},
            "contents": [{"parts": [{"text": _describe(place, mode)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        body = json.dumps(payload).encode("utf-8")
        result = None
        for model in MODELS:
            try:
                req = urllib.request.Request(
                    API.format(model=model),
                    data=body,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": secrets.gemini_key(),
                    },
                )
                with urllib.request.urlopen(req, timeout=60) as r:
                    raw = json.loads(r.read().decode("utf-8", "replace"))
                text = raw["candidates"][0]["content"]["parts"][0]["text"]
                result = json.loads(text)
                self._model = model
                self._calls += 1
                self._error = ""
                break
            except Exception as exc:
                self._error = f"{type(exc).__name__}: {exc}"
        return result

    def warm(self, places, mode: str) -> None:
        """미리 채워두기 (앱 시작 시 호출)."""
        for p in places:
            self.get(p, mode)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)

    def clear_cache(self) -> None:
        with self._lock:
            self._mem.clear()
        for p in self._dir.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass


def _sanitize(d: dict) -> dict:
    """모델 응답을 앱이 쓰는 범위로 정규화."""
    try:
        score = int(round(float(d.get("score", 50))))
    except (TypeError, ValueError):
        score = 50
    try:
        stay = int(round(float(d.get("stay_minutes", 60))))
    except (TypeError, ValueError):
        stay = 60
    tips = d.get("tips") or []
    if not isinstance(tips, list):
        tips = [str(tips)]
    return {
        "score": max(0, min(100, score)),
        "stay_minutes": max(5, min(480, stay)),
        "reason": str(d.get("reason", "")).strip()[:300],
        "tips": [str(t).strip()[:200] for t in tips[:4] if str(t).strip()],
    }
