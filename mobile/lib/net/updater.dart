/// 새 버전 확인 → 받기 → 설치. 스토어 없이 앱이 스스로 한다.
///
/// ## 왜 직접 하나
/// 스토어에 안 올리므로 아무도 대신 업데이트해 주지 않는다. 그냥 두면 사람들이 각자
/// 다른 버전을 쓰게 되고, 그러면 "나만 안 보인다"가 생긴다. PC 앱이 스스로 업데이트하는
/// 것과 같은 이유다.
///
/// ## 어디서 확인하나
/// GitHub 릴리즈의 **최신 정식판**(`/releases/latest`)을 본다. 테스트 버전(prerelease)은
/// 거기 안 잡히므로, 정식 사용자에게 테스트판이 내려갈 일이 없다 - PC 업데이터와 같은 규칙이다.
///
/// ## 설치는 사람이 누른다
/// 안드로이드는 앱이 몰래 다른 앱을 설치할 수 없다. 우리가 할 수 있는 건 APK를 받아
/// **설치 화면을 열어주는 것**까지이고, 마지막 "설치" 버튼은 사람이 누른다. 처음 한 번은
/// "이 앱의 설치 허용"도 켜줘야 한다(안드로이드 8부터).
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';

/// 릴리즈에 올라가는 APK 이름. **워크플로가 붙이는 이름과 같아야 한다**
/// (`.github/workflows/release.yml`의 "APK 이름 붙이기").
const String apkAssetName = 'ChupChat.apk';

const String latestReleaseApi =
    'https://api.github.com/repos/NasusFullstack/chat/releases/latest';

/// 새 버전이 있는가 - 있으면 그 정보.
class Available {
  const Available({required this.version, required this.url, required this.notes});

  final String version;
  final String url;
  final String notes;
}

/// `2.6.2` 같은 버전을 숫자로 갈라 비교할 수 있게.
///
/// 글자로 비교하면 안 된다 - `2.10.0`이 `2.9.0`보다 작다고 나온다.
List<int> _parts(String version) => version
    .replaceAll(RegExp(r'^v'), '')
    .split('-')
    .first
    .split('.')
    .map((p) => int.tryParse(p) ?? 0)
    .toList();

/// [candidate]가 [current]보다 새 버전인가.
bool isNewer(String candidate, String current) {
  final a = _parts(candidate);
  final b = _parts(current);
  for (var i = 0; i < 3; i++) {
    final x = i < a.length ? a[i] : 0;
    final y = i < b.length ? b[i] : 0;
    if (x != y) return x > y;
  }
  return false;
}

class Updater {
  static const MethodChannel _channel = MethodChannel('chupchat/installer');

  /// 새 버전이 있으면 알려준다. 못 물어봤으면 null(조용히 넘어간다).
  Future<Available?> check(String currentVersion) async {
    try {
      final response = await http
          .get(Uri.parse(latestReleaseApi),
              headers: {'Accept': 'application/vnd.github+json'})
          .timeout(const Duration(seconds: 12));
      if (response.statusCode != 200) return null;
      final body = jsonDecode(utf8.decode(response.bodyBytes));
      if (body is! Map) return null;

      final tag = '${body['tag_name'] ?? ''}';
      if (tag.isEmpty || !isNewer(tag, currentVersion)) return null;

      // APK가 안 올라간 릴리즈일 수도 있다(PC만 낸 경우). 그러면 알릴 이유가 없다
      final assets = body['assets'];
      if (assets is! List) return null;
      for (final asset in assets) {
        if (asset is Map && asset['name'] == apkAssetName) {
          return Available(
            version: tag.replaceAll(RegExp(r'^v'), ''),
            url: '${asset['browser_download_url']}',
            notes: '${body['body'] ?? ''}',
          );
        }
      }
      return null;
    } on Object {
      // 인터넷이 없거나 GitHub이 느릴 수 있다. 업데이트 확인 때문에 앱이
      // 멈추거나 경고가 뜨면 안 된다
      return null;
    }
  }

  /// APK를 받는다. [onProgress]로 받은 바이트/전체를 알려준다.
  ///
  /// 받아가며 바로 파일에 쓴다 - 50MB를 통째로 메모리에 들고 있을 이유가 없다.
  Future<File?> download(String url, void Function(int got, int total) onProgress,
      {bool Function()? cancelled}) async {
    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/$apkAssetName');
      if (await file.exists()) await file.delete();

      final client = http.Client();
      final request = http.Request('GET', Uri.parse(url));
      final response = await client.send(request);
      if (response.statusCode != 200) {
        client.close();
        return null;
      }
      final total = response.contentLength ?? 0;
      var got = 0;
      final sink = file.openWrite();
      await for (final chunk in response.stream) {
        if (cancelled?.call() ?? false) {
          await sink.close();
          client.close();
          if (await file.exists()) await file.delete();
          return null;
        }
        got += chunk.length;
        sink.add(chunk);
        onProgress(got, total);
      }
      await sink.close();
      client.close();
      return file;
    } on Object {
      return null;
    }
  }

  /// 지난번에 받아둔 APK를 치운다. **앱을 켤 때** 부른다.
  ///
  /// 설치 직후에 지우면 안 된다 - 시스템 설치 화면이 아직 그 파일을 읽고 있어서
  /// 설치가 깨진다. 다 끝난 다음 실행에서 치우는 것이 안전하다.
  ///
  /// 받을 때 같은 이름으로 덮어쓰므로 여러 개가 쌓이지는 않는다. 그래도 50MB짜리가
  /// 하나 남아 있을 이유는 없다.
  Future<void> cleanLeftover() async {
    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/$apkAssetName');
      if (await file.exists()) await file.delete();
    } on Object {
      // 못 지워도 앱 캐시 폴더라 안드로이드가 공간이 부족하면 알아서 비운다
    }
  }

  /// 설치 화면을 연다. 마지막 '설치'는 사람이 누른다(안드로이드 규칙).
  ///
  /// 처음에는 "이 앱의 설치 허용"이 꺼져 있어서, 그때는 그 설정 화면으로 보낸다.
  Future<String> install(File apk) async {
    try {
      final problem = await _channel.invokeMethod<String>('install', apk.path);
      return problem ?? '';
    } on PlatformException catch (error) {
      return error.message ?? '설치 화면을 열지 못했습니다.';
    } on MissingPluginException {
      return '이 기기에서는 앱 안에서 설치할 수 없습니다.';
    }
  }
}
