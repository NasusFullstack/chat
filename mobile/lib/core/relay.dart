/// 중계 서버(jsserv)의 주소와 자리 이름 - 순수 계산만.
///
/// PC 앱의 `relay.py`를 옮긴 것이다. **여기가 한 글자라도 다르면 PC와 모바일이 서로
/// 다른 칸을 본다** - 같은 채널인데 기록이 따로 쌓이고, 같은 사람인데 얼굴이 안 보인다.
/// 그래서 `test/relay_test.dart`가 파이썬이 계산한 id와 하나하나 맞춘다.
///
/// 자리 이름을 해시로 만드는 이유는 PC 쪽과 같다: 중계 서버는 빌려 쓰는 남의 서버라,
/// 거기에 `#우리방`이나 `몽키` 같은 이름을 그대로 적으면 우리가 어디서 누구와 노는지가
/// 그 디스크에 남는다. 서버 주소까지 넣고 해시하므로 서버가 다르면 같은 이름이라도
/// 다른 자리가 된다(어느 IRC 서버에나 있는 `#general`이 한 칸에 섞이면 안 된다).
library;

import 'dart:convert';

import 'package:crypto/crypto.dart';

const String server = 'https://jsserv.pdlab.kr';
const String wsServer = 'wss://jsserv.pdlab.kr';

const String battleUrl = '$wsServer/battle/ws';
const String chatWsUrl = '$wsServer/chat/ws';
const String chatUrl = '$server/chat';
const String filesUrl = '$server/files';
const String logsUrl = '$server/logs';
const String profilesUrl = '$server/profiles';

/// 서버 채팅의 **고정된 자리**. 기록·이모티콘·프로필이 어디에 쌓이는지가 이 값으로
/// 정해지므로 **절대 바꾸면 안 된다** - 바꾸면 그동안 쌓인 것을 통째로 못 찾는다.
/// PC 의 `gui/login_request.py`(SERVER_HOST / SERVER_PORT)와 **같은 값**이어야
/// 폰과 PC 가 같은 자리를 본다.
const String serverChatHost = 'chupchat';
const int serverChatPort = 0;

/// 자리 계산에 쓰는 프로토콜 이름. IRC 와 서버 채팅이 섞이지 않는 까닭이 이것이다
/// (`roomId` 가 프로토콜까지 넣어 해시한다).
const String ircKindName = 'irc';
const String serverKindName = 'server';

/// 서버가 받아주는 자리 이름 길이. 서버 쪽 정규식(`^[0-9a-f]{24}$`)과 같아야 한다.
const int idChars = 24;

String _place(String kind, String protocol, String host, int port, String name) {
  // IRC는 채널 이름과 닉네임의 대소문자를 안 가린다. #General 과 #general 이 다른
  // 자리가 되지 않게 낮춰서 해시한다(파이썬은 casefold, 여기선 toLowerCase -
  // 우리가 쓰는 글자 범위에서는 결과가 같고, 검사가 그걸 확인한다)
  final raw = '$kind|$protocol|${host.toLowerCase()}|$port|${name.toLowerCase()}';
  return sha256.convert(utf8.encode(raw)).toString().substring(0, idChars);
}

/// 그 서버 그 채널의 기록이 쌓이는 자리.
String roomId(String protocol, String host, int port, String channel) =>
    _place('room', protocol, host, port, channel);

/// 그 서버의 그 사람 프로필이 놓이는 자리.
String whoId(String protocol, String host, int port, String nick) =>
    _place('who', protocol, host, port, nick);

/// 이모티콘을 같이 쓰는 무리 - 같은 채팅 서버에 붙어 있는 사람들.
String groupId(String protocol, String host, int port) =>
    _place('group', protocol, host, port, '');

const String _filePrefix = '$server/files/';

/// 우리 서버에 올린 파일 주소면 그 id, 아니면 빈 값.
String fileIdFrom(String url) {
  if (!url.startsWith(_filePrefix)) return '';
  final rest = url.substring(_filePrefix.length);
  final id = rest.split('/').first.split('?').first;
  // id는 24자리 16진수다. 여기서 걸러야 /files/emoji 같은 다른 경로를 파일로 안 본다
  if (id.length != idChars || !RegExp(r'^[0-9a-f]+$').hasMatch(id)) return '';
  return id;
}

String metaUrl(String fileId) => '$server/files/$fileId/meta';
