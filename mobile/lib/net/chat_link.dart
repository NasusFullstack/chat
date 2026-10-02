/// "서버와 이어진 줄" - 무엇으로 이어졌는지는 여기서 끝낸다.
///
/// PC 쪽 `gui/server_chat_link.py` 와 같은 자리다. 거기서 한 것과 같은 이유로 둔다 -
/// **접속 절차를 건드리지 않고 전송 수단만 바꾸기** 위해서다. `AppState` 는 지금 붙어
/// 있는 것이 TLS 소켓(IRC)인지 WebSocket(서버 채팅)인지 몰라도 된다.
///
/// 짝이 되는 약속은 `core/chat_port.dart`(받은 것을 무슨 일로 읽을지)다. 둘을 나눈
/// 이유는 바뀌는 까닭이 다르기 때문이다 - 통로는 "어떻게 주고받나", 포트는 "그게
/// 무슨 뜻인가".
library;

/// 통로가 지금 어떤 상태인가.
///
/// **여기 있는 이유**: 예전에는 `net/irc_client.dart` 안에 있었는데, 그러면 서버 채팅
/// 통로가 IRC 파일을 가져다 써야 한다(구현이 구현에 기대는 모양). 약속 쪽으로 옮겨
/// 두고 `irc_client.dart` 가 그대로 내보내므로, 예전처럼 import 해 온 곳은 안 바뀐다.
enum LinkState { idle, connecting, connected, closed, failed }

abstract class ChatLink {
  /// 붙었나 끊겼나.
  Stream<LinkState> get state;

  /// 서버에서 온 것 하나.
  ///
  /// **모양이 프로토콜마다 다르다** - IRC 는 줄 하나(String), 서버 채팅은 사전(Map).
  /// 여기서 하나로 맞추지 않는 이유: 맞추려면 한쪽을 다른 쪽 모양으로 꾸며야 하고,
  /// 그 꾸미는 코드가 또 "지금 어느 쪽이지"를 알게 된다. 읽는 일은 포트가 한다
  /// (`ChatPort.handleIncoming`).
  Stream<Object> get incoming;

  /// 붙는다. 서버 채팅은 주소를 **우리가 알고 있어서** 받은 값을 쓰지 않는다.
  Future<bool> connect({
    required String host,
    required int port,
    required bool secure,
  });

  /// 보낸다. IRC 는 줄(String), 서버 채팅은 사전(Map)이 온다.
  void sendRaw(Object payload);

  Future<void> close();

  void dispose();

  /// 왜 못 붙었는지 사람에게 보여줄 말.
  String get lastError;

  /// 처음 보는 인증서를 만났으면 그 지문. 서버 채팅은 **늘 빈 값**이다 -
  /// 정식 인증서를 쓰므로 사람에게 물어볼 것이 없다.
  String get pendingFingerprint;

  /// 전에 믿기로 한 것과 달라졌는가. 서버 채팅은 늘 거짓.
  bool get fingerprintChanged;
}
