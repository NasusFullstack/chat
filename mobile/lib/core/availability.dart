/// 지금 **무엇을 열어두나** - 한 곳에서 정한다(화면도 소켓도 모르는 순수 표).
///
/// 당분간 막아둔 것들(2026-10-08 사용자 요청):
///
/// - **춥채팅 서버**: 로그인 화면 탭에 **보이기는 하되 못 고른다.** jsserv 에서
///   꺼뒀다(2026-10-06). 고를 수 있게 두면 "눌렀는데 안 붙는다"가 된다
/// - **사진·파일 올리기**: pdlab IRC 의 `#pdlab` 채널에서만 된다
///
/// 되살리는 법: 아래 표 두 개만 고치면 된다. 화면 쪽은 이 표를 묻기만 한다.
/// **PC 에도 같은 표가 있다**(`gui/availability.py`) - 한쪽만 고치면 PC 와 폰이
/// 다르게 막는다(`tests/test_availability.py` 가 둘을 대조한다).
library;

import 'chat_port.dart';

/// 로그인 화면에서 고를 수 있는 쪽. 여기 없는 쪽은 **보이되 흐리게** 둔다
const Set<ChatKind> enabledKinds = {ChatKind.irc};

/// 사진·파일을 올릴 수 있는 방 - (프로토콜, 서버 주소, 채널).
/// 포트는 안 본다 - 같은 서버에 평문(6667)·보안(6697) 두 길로 붙을 수 있다
const List<(String, String, String)> uploadRooms = [
  ('irc', 'home.pdlab.kr', '#pdlab'),
];

/// 막혔을 때 사람에게 보여줄 말. 왜 안 되는지 모르면 고장난 줄 안다
const String uploadBlockedText = '지금은 #pdlab 채널에서만 사진·파일을 올릴 수 있습니다.';
const String kindBlockedText = '지금은 IRC 서버만 쓸 수 있습니다.';

/// 로그인 화면에서 이쪽을 고를 수 있나.
bool kindEnabled(ChatKind kind) => enabledKinds.contains(kind);

/// 이 방에서 사진·파일을 올릴 수 있나.
///
/// **대소문자를 안 가린다** - IRC 는 채널 이름(#PDLab 과 #pdlab)도 서버 주소도
/// 대소문자를 안 가린다. 가리면 같은 방인데 어떤 때는 되고 어떤 때는 안 된다.
bool uploadAllowed(String protocol, String host, String channel) {
  final key = (
    protocol.toLowerCase(),
    host.trim().toLowerCase(),
    channel.trim().toLowerCase(),
  );
  return uploadRooms.contains(key);
}
