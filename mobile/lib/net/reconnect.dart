/// 끊겼을 때 **언제** 다시 붙을지만 정하는 부품.
///
/// 소켓도 세션도 화면도 모른다 - 실제로 접속하는 일과 안내를 띄우는 일은 받아온 함수에
/// 맡긴다. 그래서 이 정책만 따로 시험할 수 있다.
///
/// PC 앱의 `gui/reconnect.py`와 **같은 숫자, 같은 규칙**이다. 두 앱이 같은 서버에
/// 붙는데 한쪽만 금방 포기하면 "폰만 자꾸 끊긴다"가 된다.
///
/// 폰에서 특히 필요한 이유: 신호가 끊기는 자리(지하철·엘리베이터)가 PC 보다 훨씬 많고,
/// 안드로이드가 자리를 비우는 동안 프로세스를 정리할 수도 있다. 다시 안 붙으면 사람은
/// **죽은 채팅 화면**을 보게 되고, 앱을 끄고 다시 켜는 수밖에 없다.
library;

import 'dart:async';

/// 첫 재시도까지 기다리는 시간. 시도할수록 이 배수로 늘어난다
const Duration reconnectBase = Duration(seconds: 3);

/// 아무리 늘어도 이보다는 자주 시도한다(죽은 서버를 같은 속도로 계속 두드리지 않게)
const Duration reconnectMax = Duration(seconds: 30);

/// 이만큼 해보고 안 되면 포기하고 사람에게 알린다. 무한정 시도하면 배터리만 먹는다
const int reconnectMaxAttempts = 10;

/// 몇 번째 시도를 얼마나 기다릴지. PC 와 같은 식이다
Duration reconnectDelay(int attempt) {
  final millis = reconnectBase.inMilliseconds * attempt;
  return millis < reconnectMax.inMilliseconds
      ? Duration(milliseconds: millis)
      : reconnectMax;
}

class ReconnectPolicy {
  ReconnectPolicy({required this.connectNow, required this.notify});

  /// 실제로 접속을 시도하는 일.
  final Future<bool> Function() connectNow;

  /// 사람에게 보여줄 안내. 조용히 재시도하면 "먹통"으로 보인다
  final void Function(String text) notify;

  /// 지금 자동 재접속 중인가
  bool active = false;
  int attempt = 0;

  Timer? _timer;

  /// 돌아갈 채널. 다시 붙은 뒤 여기로 들어간다
  List<String> _rooms = const [];
  List<String> get pendingRooms => List<String>.of(_rooms);

  /// 끊김이 확인됐을 때 부른다. 이미 진행 중이면 false.
  bool start(Iterable<String> rooms) {
    if (active) return false;
    active = true;
    attempt = 0;
    _rooms = List<String>.of(rooms);
    notify('연결이 끊어졌습니다. 다시 연결하는 중...');
    schedule();
    return true;
  }

  /// 다음 시도를 예약한다. 한도를 넘으면 포기한다.
  void schedule() {
    attempt += 1;
    if (attempt > reconnectMaxAttempts) {
      active = false;
      notify('다시 연결하지 못했습니다. 앱을 다시 켜고 접속해 주세요.');
      return;
    }
    final wait = reconnectDelay(attempt);
    notify('다시 연결 시도 $attempt/$reconnectMaxAttempts '
        '(${wait.inSeconds}초 후)');
    _timer?.cancel();
    _timer = Timer(wait, () {
      if (!active) return;
      connectNow();
    });
  }

  /// 앱으로 돌아왔다 - 기다리지 말고 **지금** 해본다.
  ///
  /// 사람이 앱을 다시 보고 있다는 건 신호가 돌아왔을 가능성이 가장 큰 순간이다.
  /// 30초짜리 예약이 걸려 있는데 그걸 기다리면 먹통처럼 보인다.
  void tryNow() {
    if (!active) return;
    _timer?.cancel();
    connectNow();
  }

  /// 다시 로그인까지 됐을 때 - 돌아갈 채널을 돌려주고 정책을 끝낸다.
  List<String> succeeded() {
    _timer?.cancel();
    active = false;
    attempt = 0;
    notify('다시 연결되었습니다.');
    final rooms = _rooms;
    _rooms = const [];
    return rooms;
  }

  /// 일부러 끊는 경우(로그아웃·종료) - 재시도를 완전히 접는다.
  ///
  /// 이게 없으면 로그아웃하자마자 방금 나온 계정으로 다시 들어간다(PC 에서 실제로
  /// 겪은 사고다 - CLAUDE.md 10번).
  void cancel() {
    _timer?.cancel();
    _timer = null;
    active = false;
    attempt = 0;
    _rooms = const [];
  }
}
