"""일부러 스택을 넘치게 해서(무한 재귀) 기록이 실제로 남는지 확인한다.

Gil의 증상("멈추더니 꺼진다")이 바로 이 종류다 - 파이썬 예외가 아니라 프로세스가
통째로 죽기 때문에 지금까지는 아무 기록도 안 남았다.
"""
import sys
import error_log
error_log.install()
sys.setrecursionlimit(10 ** 7)   # 파이썬 안전장치를 풀어 진짜 C 스택을 넘치게 함


def 무한히_파고들기(n=0):
    return 무한히_파고들기(n + 1)


무한히_파고들기()
