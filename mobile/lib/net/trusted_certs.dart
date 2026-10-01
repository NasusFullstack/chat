/// 한 번 믿기로 한 서버 인증서를 기억한다.
///
/// ## 왜 '검사 끄기'가 아니라 이 방식인가
/// 개인이 돌리는 IRC 서버는 대개 자체 서명 인증서를 쓴다(home.pdlab.kr 도 그렇다).
/// 무조건 막으면 그 서버에 못 붙고, **무조건 넘기면 가짜 서버를 구분할 수 없다.**
///
/// 그래서 PC 앱과 같은 방식을 쓴다 - 지문을 보여주고 한 번만 묻고, 신뢰하기로 하면
/// 기억해뒀다가 다음부터 조용히 붙는다. **지문이 바뀌면 다시 묻는다** - 서버를 바꾼
/// 것이 아니라면 누가 중간에 끼었다는 뜻이기 때문이다.
///
/// 이게 '인증서 검사 건너뛰기'보다 나은 점: 그 스위치는 **아무 인증서나** 받아들이지만,
/// 이 방식은 **내가 한 번 본 그 인증서만** 받아들인다.
library;

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:shared_preferences/shared_preferences.dart';

const String _key = 'trusted_certs';

/// 인증서의 지문 - 사람이 눈으로 맞춰볼 수 있는 모양.
///
/// 인증서 전체를 저장해 비교할 수도 있지만, 지문이면 충분하고 사람에게 보여주기도 좋다.
String fingerprintOf(X509Certificate cert) {
  final digest = sha256.convert(cert.der).toString().toUpperCase();
  // 두 글자씩 끊어 보여준다 - 눈으로 맞춰보라고 띄우는 것이므로 읽기 쉬워야 한다
  final pairs = <String>[];
  for (var i = 0; i < digest.length; i += 2) {
    pairs.add(digest.substring(i, i + 2));
  }
  return pairs.join(':');
}

String _place(String host, int port) => '${host.toLowerCase()}:$port';

/// 그 서버에 대해 전에 믿기로 한 지문(없으면 빈 값).
Future<String> knownFingerprint(String host, int port) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_key);
    if (saved == null || saved.isEmpty) return '';
    final map = jsonDecode(saved);
    if (map is! Map) return '';
    return '${map[_place(host, port)] ?? ''}';
  } on Object {
    return '';
  }
}

/// 이 서버의 이 인증서를 믿기로 한다.
Future<void> trust(String host, int port, String fingerprint) async {
  try {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_key);
    final map = <String, dynamic>{};
    if (saved != null && saved.isNotEmpty) {
      final old = jsonDecode(saved);
      if (old is Map) map.addAll(old.cast<String, dynamic>());
    }
    map[_place(host, port)] = fingerprint;
    await prefs.setString(_key, jsonEncode(map));
  } on Object {
    // 못 적어두면 다음에 또 묻는다. 번거롭지만 틀리게 믿는 것보다 낫다
  }
}
