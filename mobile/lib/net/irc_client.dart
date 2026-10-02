/// 서버와의 연결 - 줄 단위로 주고받는 일만 한다. 무슨 일인지는 판단하지 않는다.
///
/// PC 앱의 `gui/network.py`에 해당한다. 판단은 `core/session.dart`가 하고 여기는
/// **줄을 넘겨주기만** 한다 - 그래야 판단 쪽을 소켓 없이 시험할 수 있다.
///
/// ## 줄이 쪼개져 오는 것을 여기서 막는다
/// TCP는 "한 번 보낸 것이 한 번에 온다"를 보장하지 않는다. 한 줄이 두 번에 나뉘어
/// 오기도 하고, 세 줄이 한 번에 붙어 오기도 한다. 받은 것을 모아뒀다가 CR-LF를
/// 만날 때만 잘라서 올린다.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import '../core/irc_protocol.dart';
import 'chat_link.dart';
import 'trusted_certs.dart' as certs;

// 연결 상태(`LinkState`)는 **약속 쪽으로 옮겼다**(chat_link.dart). 서버 채팅 통로도
// 같은 말을 써야 하는데, 그걸 여기서 가져가면 구현이 구현에 기대는 모양이 된다.
// 예전처럼 이 파일에서 import 해 온 곳들이 안 바뀌게 그대로 내보낸다.
export 'chat_link.dart' show LinkState;

class IrcClient implements ChatLink {
  IrcClient();

  Socket? _socket;
  StreamSubscription<List<int>>? _sub;

  /// 아직 줄이 안 된 조각. TCP는 줄 경계를 지켜주지 않는다
  final List<int> _buffer = [];

  final _lines = StreamController<String>.broadcast();
  final _state = StreamController<LinkState>.broadcast();

  /// 서버에서 온 줄(CR-LF는 떼어낸 상태).
  Stream<String> get lines => _lines.stream;

  /// 통로 약속이 부르는 이름. IRC 가 올리는 것은 **줄 하나**다.
  @override
  Stream<Object> get incoming => _lines.stream;

  @override
  Stream<LinkState> get state => _state.stream;

  @override
  String lastError = '';

  /// 처음 보는 인증서를 만났을 때 그 지문. 화면이 사람에게 보여주고 물어본다
  @override
  String pendingFingerprint = '';

  /// 전에 믿기로 한 것과 **달라졌는가**. 서버를 바꾼 게 아니라면 위험하다
  @override
  bool fingerprintChanged = false;

  bool get isConnected => _socket != null;

  /// 서버에 붙는다. [secure]면 TLS로 붙는다(대부분의 IRC 서버가 6697 포트에서 쓴다).
  ///
  /// 개인이 돌리는 서버는 대개 자체 서명 인증서를 쓴다. 무조건 막으면 못 붙고,
  /// 무조건 넘기면 가짜 서버를 구분할 수 없다.
  ///
  /// 그래서 **전에 믿기로 한 그 인증서만** 받아들인다(trusted_certs.dart). 처음 보는
  /// 것이면 붙지 않고 지문만 남긴다 - 화면이 사람에게 보여주고 물어본 뒤 다시 부른다.
  @override
  Future<bool> connect({
    required String host,
    required int port,
    bool secure = true,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    await close();
    pendingFingerprint = '';
    fingerprintChanged = false;
    _state.add(LinkState.connecting);
    final known = secure ? await certs.knownFingerprint(host, port) : '';
    try {
      final socket = secure
          ? await SecureSocket.connect(
              host,
              port,
              timeout: timeout,
              onBadCertificate: (cert) {
                final seen = certs.fingerprintOf(cert);
                if (known.isNotEmpty && seen == known) {
                  return true;      // 전에 내가 보고 믿기로 한 바로 그 인증서다
                }
                // 모르는 인증서다. 붙지 않고 사람에게 물어볼 거리만 남긴다
                pendingFingerprint = seen;
                fingerprintChanged = known.isNotEmpty;
                return false;
              },
            )
          : await Socket.connect(host, port, timeout: timeout);
      socket.setOption(SocketOption.tcpNoDelay, true);
      _socket = socket;
      _buffer.clear();
      _sub = socket.listen(
        _onBytes,
        onError: (Object error) {
          lastError = '$error';
          _state.add(LinkState.failed);
          close();
        },
        onDone: () {
          _state.add(LinkState.closed);
          close();
        },
        cancelOnError: true,
      );
      _state.add(LinkState.connected);
      return true;
    } on Object catch (error) {
      lastError = pendingFingerprint.isEmpty ? _friendly(error) : '';
      _state.add(LinkState.failed);
      return false;
    }
  }

  void send(String line) {
    final socket = _socket;
    if (socket == null) return;
    socket.add(encodeLine(line));
  }

  /// 통로 약속이 부르는 이름. IRC 로 가는 것은 **줄 하나**뿐이다.
  @override
  void sendRaw(Object payload) {
    if (payload is String) send(payload);
  }

  @override
  Future<void> close() async {
    final socket = _socket;
    _socket = null;
    await _sub?.cancel();
    _sub = null;
    try {
      await socket?.close();
    } on Object {
      // 이미 끊긴 소켓을 닫는 건 오류가 아니다
    }
  }

  @override
  void dispose() {
    close();
    _lines.close();
    _state.close();
  }

  // ------------------------------------------------------------------
  void _onBytes(List<int> chunk) {
    _buffer.addAll(chunk);
    while (true) {
      final cut = _findLineEnd();
      if (cut < 0) break;
      final raw = _buffer.sublist(0, cut);
      // CR-LF 둘 다 지운다. 서버에 따라 LF만 보내는 경우도 있다
      var drop = cut;
      while (drop < _buffer.length &&
          (_buffer[drop] == 13 || _buffer[drop] == 10)) {
        drop += 1;
      }
      _buffer.removeRange(0, drop);
      if (raw.isEmpty) continue;
      // 서버가 UTF-8이 아닌 글자를 섞어 보내도 연결이 끊기면 안 된다
      _lines.add(utf8.decode(raw, allowMalformed: true));
    }
  }

  int _findLineEnd() {
    for (var i = 0; i < _buffer.length; i++) {
      if (_buffer[i] == 13 || _buffer[i] == 10) return i;
    }
    return -1;
  }

  static String _friendly(Object error) {
    final text = '$error';
    if (error is SocketException) {
      if (text.contains('timed out') || text.contains('timeout')) {
        return '서버가 응답하지 않습니다. 주소와 포트를 확인해 주세요.';
      }
      return '서버에 연결하지 못했습니다. 인터넷 연결과 주소를 확인해 주세요.';
    }
    if (error is HandshakeException) {
      // 지문을 못 읽은 경우에만 여기까지 온다(읽었으면 화면이 물어본다)
      return '서버와 암호화 연결을 맺지 못했습니다. 주소와 포트를 확인해 주세요.';
    }
    return text;
  }
}
