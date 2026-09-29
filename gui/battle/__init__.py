"""배틀크루저 전투 - 화면 쪽 부품들.

규약과 판정은 화면을 모른다(`battle_protocol.py`, `battle_sim.py`). 여기 있는 것들은
**그리는 일과 사람이 누르는 것**만 담당한다.

    net.py      중계 서버와 주고받기(QWebSocket)
    lobby.py    대기방 - 정원/색 고르고 참가자 보고 시작
    hp_bar.py   스타1 방식 도트 체력바 그리기

부품끼리 서로를 모른다 - 무엇을 할지는 창이 정한다(gui/components/ 규칙과 같다).
"""
