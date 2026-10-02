/// 서버 채팅(jsserv `/chat/ws`) 통로 - IRC 통로와 **같은 모양**으로 보인다.
///
/// PC 쪽 `gui/server_chat_link.py` 와 짝이다. 하는 일은 하나다 - 사전(Map)을 글자로
/// 바꿔 보내고, 온 글자를 사전으로 바꿔 올린다. **무슨 뜻인지는 여기서 안 본다**
/// (그건 `core/server_session.dart` 가 한다).
///
/// ## 주소를 받지 않는 이유
/// IRC 는 아무 서버에나 붙을 수 있어서 주소를 받는다. 서버 채팅은 우리 서버 하나뿐이라
/// 받은 값을 쓰지 않는다 - 사람이 주소를 잘못 적어 "왜 안 되지"가 되는 일이 없다.
/// PC 도 같게 해뒀다.
///
/// ## 인증서는 보통대로 검사한다
/// IRC 서버에 쓰는 지문 고정(`trusted_certs.dart`)을 여기 갖다 쓰면 안 된다. 중계
/// 서버는 정식 인증서라 그럴 이유가 없고, 통신사나 백신이 가로채는 자리에서는 지문이
/// 사람마다 달라져 **전부 못 붙게** 된다(전투 중계 `battle_link.dart` 에 같은 설명이 있다).
library;

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../core/relay.dart' as relay;
import 'chat_link.dart';

/// 이 안에 못 붙으면 포기한다.
///
/// 방화벽이 조용히 버리면 성공도 실패도 안 오고 매달린다 - 폰에서는 그게 "로그인
/// 버튼을 눌렀는데 아무 일도 안 일어난다"로 보인다.
const Duration connectTimeout = Duration(seconds: 12);

class ServerChatClient implements ChatLink {
  ServerChatClient();

  WebSocketChannel? _socket;
  StreamSubscription<dynamic>? _sub;

  final _incoming = StreamController<Object>.broadcast();
  final _state = StreamController<LinkState>.broadcast();

  @override
  Stream<Object> get incoming => _incoming.stream;

  @override
  Stream<LinkState> get state => _state.stream;

  @override
  String lastError = '';

  /// 서버 채팅은 정식 인증서를 쓴다 - 사람에게 물어볼 것이 없다(위 설명).
  @override
  String get pendingFingerprint => '';

  @override
  bool get fingerprintChanged => false;

  /// 일부러 끊는 중인가. 그 뒤에 오는 '끊겼다'는 사고가 아니다.
  bool _closing = false;

  @override
  Future<bool> connect({
    required String host,
    required int port,
    required bool secure,
  }) async {
    await close();
    _closing = false;
    lastError = '';
    _state.add(LinkState.connecting);
    try {
      final socket = WebSocketChannel.connect(Uri.parse(relay.chatWsUrl));
      // **붙기를 기다린다.** 안 기다리면 곧바로 보낸 줄이 조용히 버려진다
      await socket.ready.timeout(connectTimeout);
      _socket = socket;
      _sub = socket.stream.listen(_onFrame,
          onError: (Object _) => _dropped(), onDone: _dropped);
      _state.add(LinkState.connected);
      return true;
    } on TimeoutException {
      lastError = '서버 채팅에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요.';
      _state.add(LinkState.failed);
      return false;
    } on Object catch (error) {
      lastError = '서버 채팅에 연결하지 못했습니다: $error';
      _state.add(LinkState.failed);
      return false;
    }
  }

  @override
  void sendRaw(Object payload) {
    final socket = _socket;
    if (socket == null || payload is! Map) return;
    socket.sink.add(jsonEncode(payload));
  }

  @override
  Future<void> close() async {
    _closing = true;
    final socket = _socket;
    _socket = null;
    await _sub?.cancel();
    _sub = null;
    try {
      await socket?.sink.close();
    } on Object {
      // 이미 끊긴 것을 닫는 건 오류가 아니다
    }
  }

  @override
  void dispose() {
    close();
    _incoming.close();
    _state.close();
  }

  void _onFrame(dynamic frame) {
    if (frame is! String) return;
    final Object? read;
    try {
      read = jsonDecode(frame);
    } on FormatException {
      return; // 읽을 수 없는 줄은 조용히 버린다
    }
    if (read is Map) _incoming.add(read);
  }

  void _dropped() {
    if (_closing) return; // 일부러 끊은 것은 사고가 아니다
    _socket = null;
    _state.add(LinkState.closed);
  }
}
