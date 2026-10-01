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

/// 연결이 어떤 상태인가 - 화면이 이걸 보고 안내 문구를 바꾼다.
enum LinkState { idle, connecting, connected, closed, failed }

class IrcClient {
  IrcClient();

  Socket? _socket;
  StreamSubscription<List<int>>? _sub;

  /// 아직 줄이 안 된 조각. TCP는 줄 경계를 지켜주지 않는다
  final List<int> _buffer = [];

  final _lines = StreamController<String>.broadcast();
  final _state = StreamController<LinkState>.broadcast();

  /// 서버에서 온 줄(CR-LF는 떼어낸 상태).
  Stream<String> get lines => _lines.stream;

  Stream<LinkState> get state => _state.stream;

  String lastError = '';

  bool get isConnected => _socket != null;

  /// 서버에 붙는다. [secure]면 TLS로 붙는다(대부분의 IRC 서버가 6697 포트에서 쓴다).
  ///
  /// [allowBadCertificate]는 **직접 운영하는 서버**를 위한 것이다. 개인 서버는 자체
  /// 서명 인증서를 쓰는 경우가 흔한데, 그걸 무조건 막으면 아예 못 붙는다. 다만 켜면
  /// 중간에서 가로채는 것을 못 걸러내므로, 화면에서 사람에게 물어본 뒤에만 켜야 한다.
  Future<bool> connect({
    required String host,
    required int port,
    bool secure = true,
    bool allowBadCertificate = false,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    await close();
    _state.add(LinkState.connecting);
    try {
      final socket = secure
          ? await SecureSocket.connect(
              host,
              port,
              timeout: timeout,
              onBadCertificate: (_) => allowBadCertificate,
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
      lastError = _friendly(error);
      _state.add(LinkState.failed);
      return false;
    }
  }

  void send(String line) {
    final socket = _socket;
    if (socket == null) return;
    socket.add(encodeLine(line));
  }

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
      // 개인 서버는 자체 서명 인증서를 쓰는 일이 흔하다 - 그때 이 안내가 뜬다
      return '서버 인증서를 믿을 수 없습니다. 직접 운영하는 서버라면 '
          '"인증서 검사 건너뛰기"를 켜고 다시 시도해 주세요.';
    }
    return text;
  }
}
