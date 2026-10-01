/// 새 버전 판단이 맞는가.
///
/// 여기가 틀리면 둘 중 하나가 된다: 업데이트가 **영영 안 뜨거나**, 최신인데도
/// **계속 뜨거나**. 둘 다 조용히 틀리는 종류라 검사로 못 박아둔다.
///
/// 특히 글자로 비교하면 안 된다 - `"2.10.0" < "2.9.0"` 이 참이 되어서, 10번째
/// 자리 버전이 나오는 순간 업데이트가 멈춘다.
library;

import 'package:flutter_test/flutter_test.dart';

import 'package:chupchat/net/updater.dart';

void main() {
  test('더 새 버전을 알아본다', () {
    expect(isNewer('2.6.3', '2.6.2'), isTrue);
    expect(isNewer('2.7.0', '2.6.9'), isTrue);
    expect(isNewer('3.0.0', '2.99.99'), isTrue);
  });

  test('같거나 옛 버전은 아니라고 한다', () {
    expect(isNewer('2.6.2', '2.6.2'), isFalse);
    expect(isNewer('2.6.1', '2.6.2'), isFalse);
    expect(isNewer('1.9.9', '2.0.0'), isFalse);
  });

  test('글자로 비교하지 않는다', () {
    // 글자로 비교하면 "2.10.0" < "2.9.0" 이라 업데이트가 영영 멈춘다
    expect(isNewer('2.10.0', '2.9.0'), isTrue);
    expect(isNewer('2.9.0', '2.10.0'), isFalse);
    expect(isNewer('10.0.0', '9.0.0'), isTrue);
  });

  test('태그의 v 와 베타 꼬리표를 떼고 본다', () {
    // 릴리즈 태그는 'v2.6.3' 모양으로 온다
    expect(isNewer('v2.6.3', '2.6.2'), isTrue);
    expect(isNewer('v2.6.2', '2.6.2'), isFalse);
    // 베타는 애초에 /releases/latest 에 안 잡히지만, 와도 숫자로만 본다
    expect(isNewer('v2.7.0-beta.1', '2.6.2'), isTrue);
  });

  test('이상한 값이 와도 안 죽는다', () {
    // 남이 만든 태그가 올 수도 있다. 터지는 것보다 "새 버전 아님"이 낫다
    expect(isNewer('', '2.6.2'), isFalse);
    expect(isNewer('아무거나', '2.6.2'), isFalse);
    expect(isNewer('2', '2.6.2'), isFalse);
    expect(isNewer('2.6.2.1', '2.6.2'), isFalse);
  });

  test('릴리즈에서 찾는 파일 이름이 워크플로와 같다', () {
    // 이름이 어긋나면 APK가 올라와 있어도 "새 버전 없음"으로 보인다.
    // .github/workflows/release.yml 의 "APK 이름 붙이기" 와 같아야 한다
    expect(apkAssetName, 'ChupChat.apk');
  });

  test('최신 **정식판**만 본다', () {
    // prerelease(테스트 버전)는 /releases/latest 에 안 잡힌다 - PC 업데이터와 같은 규칙.
    // 이 주소를 /releases 로 바꾸면 테스트 버전이 정식 사용자에게 내려간다
    expect(latestReleaseApi, endsWith('/releases/latest'));
  });
}
