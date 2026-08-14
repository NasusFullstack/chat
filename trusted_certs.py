"""직접 확인하고 신뢰하기로 한 서버 인증서를 기억한다.

왜 필요한가: 개인이 운영하는 IRC 서버는 대개 **자체 서명 인증서**를 쓴다(정식 CA에서
받은 것이 아니다). 그러면 시스템은 "이 인증서를 믿을 수 없다"고 하고 접속이 막힌다.
실제로 home.pdlab.kr:6697이 그랬다 - 암호화(TLS 1.3)는 되는데 검증에서 끊겼다.

두 가지 나쁜 선택 대신 중간을 택한다.
- 검증을 아예 끄면: 누가 중간에서 가짜 서버 노릇을 해도 알 수 없다
- 검증을 고집하면: 그 서버에는 영영 못 붙는다

그래서 다른 IRC 클라이언트들이 하는 방식을 쓴다. **처음 한 번만 사람에게 묻고**, 사용자가
신뢰하기로 한 인증서의 지문을 적어둔다. 다음부터는 지문이 같으면 조용히 붙고, **지문이
바뀌면 다시 묻는다**(서버를 갈아탄 것일 수도, 누가 중간에 낀 것일 수도 있으므로).
"""
import json
import os

import app_paths

STORE_FILE = os.path.join(app_paths.data_dir(), "trusted_certs.json")


def _load() -> dict:
    if not os.path.exists(STORE_FILE):
        return {}
    try:
        with open(STORE_FILE, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict):
    try:
        with open(STORE_FILE, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
    except OSError:
        pass


def key_for(host: str, port: int) -> str:
    return f"{(host or '').lower()}:{int(port or 0)}"


def fingerprint_of(host: str, port: int) -> str:
    """그 서버에 대해 사용자가 신뢰하기로 한 지문(없으면 빈 문자열)."""
    return str(_load().get(key_for(host, port), ""))


def trust(host: str, port: int, fingerprint: str):
    data = _load()
    data[key_for(host, port)] = fingerprint
    _save(data)


def forget(host: str, port: int):
    data = _load()
    data.pop(key_for(host, port), None)
    _save(data)


def readable(fingerprint: str) -> str:
    """사람이 눈으로 비교할 수 있게 두 글자씩 끊어서 보여준다."""
    clean = (fingerprint or "").replace(":", "").replace(" ", "").upper()
    return ":".join(clean[i:i + 2] for i in range(0, len(clean), 2))
