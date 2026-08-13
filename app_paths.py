"""앱이 자기 파일(설정·기록·아이콘)을 두는 폴더 한 곳.

같은 함수가 11개 파일에 복사돼 있었다. 복사본이 많으면 "테스트에서만 다른 폴더를 쓰게
하자" 같은 변경을 할 수가 없다 - 실제로 그래서 테스트들이 개발자 컴퓨터의 진짜 설정
파일(login_prefs.json 등)을 함께 쓰고 있었고, 앞 테스트가 남긴 로그인 정보를 뒤 테스트가
물려받아 엉뚱하게 실패했다(기본 서버 주소 검사가 그렇게 깨져 있었다).

`CHUPCHAT_DATA_DIR`을 정해두면 그 폴더를 쓴다. 테스트 러너가 이걸 임시 폴더로 잡아서,
테스트가 서로 간섭하지 않고 사람이 쓰던 설정도 안 건드린다.
"""
import os
import sys

ENV_KEY = "CHUPCHAT_DATA_DIR"


def data_dir() -> str:
    """앱 데이터가 모여 있는 폴더(설치 폴더 / 소스 실행 시 저장소 루트)."""
    override = os.environ.get(ENV_KEY)
    if override:
        os.makedirs(override, exist_ok=True)
        return override
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))



def asset_dir() -> str:
    """같이 배포되는 파일(아이콘, 인증서)이 있는 폴더.

    데이터 폴더와 **다른 개념이다.** 데이터는 테스트나 사용자가 다른 곳으로 돌릴 수 있지만,
    아이콘·인증서는 프로그램과 함께 설치된 자리에 있다. 한때 이 둘을 한 함수로 합쳤다가
    테스트가 임시 폴더를 데이터 폴더로 쓰는 순간 아이콘을 못 찾아 창 아이콘이 빈칸이 됐다.
    그래서 여기는 환경 변수로 바뀌지 않는다.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))
