/// 홈으로 나가도 **접속이 끊기지 않게** 붙잡아 두는 일.
///
/// ## 왜 필요한가
/// 안드로이드 11부터는 화면에서 사라진 앱의 프로세스를 아예 **얼린다**(cached app
/// freezer). 소켓은 열려 있는데 우리가 움직이지 못하니 서버가 보내는 PING 에 PONG 을
/// 못 보내고, 서버는 응답 없는 손님으로 보고 연결을 끊는다. 실제로 홈 버튼을 누르면
/// 접속이 끊긴다는 신고가 그것이다.
///
/// 얼지 않으려면 "지금 사용자를 위해 일하고 있다"고 안드로이드에 알려야 한다 -
/// 그게 포그라운드 서비스이고, 대가로 **"실행 중" 알림 하나를 띄워야 한다**(규칙이다,
/// 우리가 숨길 수 없다).
///
/// ## 앱을 완전히 끄면 같이 끊긴다
/// 최근 앱 목록에서 밀어서 끄면 서비스도 스스로 멈춘다(`ChatService.onTaskRemoved`).
/// 그래야 "끈 줄 알았는데 계속 접속되어 있는" 상태가 안 생긴다.
library;

import 'package:flutter/services.dart';

/// 안드로이드 쪽 서비스와 이야기하는 통로.
const MethodChannel _channel = MethodChannel('chupchat/service');

/// 접속을 붙잡기 시작한다. 되면 true.
///
/// 이미 돌고 있으면 그냥 true 다(두 번 불러도 알림이 두 개가 되지 않는다).
Future<bool> hold() async {
  try {
    return await _channel.invokeMethod<bool>('start') ?? false;
  } on Object {
    // 안드로이드가 아니거나 권한이 없다. 그래도 앱은 돌아야 한다
    return false;
  }
}

/// 붙잡기를 그만둔다(로그아웃·설정을 끈 경우).
Future<void> release() async {
  try {
    await _channel.invokeMethod<void>('stop');
  } on Object {
    // 안 돌고 있었으면 멈출 것도 없다
  }
}
