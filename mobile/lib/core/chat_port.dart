/// "채팅이 할 수 있는 일" - 어느 서버에 붙든 화면이 보는 창구는 이것뿐이다.
///
/// PC 의 `chat_core/ports.py` 의 `ProtocolPort` 와 같은 자리다. 여기를 두는 이유는
/// 하나다 - **화면과 상태가 "지금 IRC 인가 서버 채팅인가"를 몰라야 한다.**
/// 알게 되면 `if 서버면 ...` 가 화면 곳곳으로 번지고, 한쪽을 고칠 때 다른 쪽이 깨진다.
///
/// 지키는 규칙:
/// - **나오는 것은 같은 이벤트다**(`events.dart`). 두 쪽이 같은 말을 해야 화면이
///   하나로 끝난다
/// - 프로토콜마다 다른 것은 **구현이 갖는다**. 예를 들어 IRC 는 보낸 말을 서버가
///   안 돌려줘서 자기 화면에 직접 올려야 하고(로컬 에코), 서버 채팅은 돌려주므로
///   올리면 두 번 보인다
/// - 새 프로토콜을 더할 때 이 약속을 늘리지 말 것. 늘리면 모든 구현이 따라 바뀐다
library;

/// 어느 쪽에 붙어 있는가.
///
/// **이 값으로 갈리는 것**(한 군데라도 빠뜨리면 둘이 섞인다):
/// - 어느 통로로 붙나(`net/chat_link.dart`)
/// - 받은 것을 어떻게 읽나(이 파일의 구현들)
/// - 기록·이모티콘·프로필이 **어디에 쌓이나**(`relay.roomId` 가 프로토콜까지 해시한다)
/// - 기억해둔 접속 정보와 채널 목록(`login_store.dart`)
enum ChatKind {
  /// 실제 IRC 서버. 쓸 수 있게 그대로 둔다 - 서버 채팅이 생겨도 없애지 않는다
  irc,

  /// 춥채팅 서버(jsserv `/chat`). IRC 제약이 없는 쪽
  server,
}

extension ChatKindName on ChatKind {
  /// 자리를 계산할 때 쓰는 이름. **PC 와 같은 글자여야** 폰과 PC 가 같은 자리를 본다
  /// (PC 는 `chat_core/protocols/*.py` 의 `name`).
  String get wireName => this == ChatKind.server ? 'server' : 'irc';

  /// 사람에게 보여줄 이름. **탭 두 칸에 들어가야 해서 짧게 둔다**
  String get label => this == ChatKind.server ? '춥채팅 서버' : 'IRC 서버';
}

abstract class ChatPort {
  /// 서버가 확정해준 내 이름. 아직이면 빈 글자
  String get myId;

  /// 들어가기. IRC 는 닉네임만, 서버 채팅은 아이디+비밀번호다
  void login({String? password, String realname});

  /// 들어간다. [key]는 비밀번호가 걸린 방에만 쓴다.
  void joinChannel(String name, {String key = ''});

  /// 서버에 있는 방을 **보고 고를 수 있나.**
  ///
  /// 화면은 "지금 서버 채팅인가"가 아니라 **이것**을 묻는다. 그래야 화면이 프로토콜
  /// 이름을 몰라도 되고, 나중에 목록을 줄 수 있는 쪽이 늘어도 화면은 안 바뀐다.
  bool get canListRooms;

  /// 방 목록을 달라고 한다. 답은 `RoomListReceived` 로 온다.
  void requestRoomList();

  void leaveChannel(String channel);

  void sendChat(String channel, String text);

  /// 전투 방 번호를 채널에 알린다.
  ///
  /// IRC 는 CTCP 프레임으로, 서버 채팅은 그냥 채팅으로 보낸다 - 받는 쪽이 걸러낸다.
  /// **주소는 안 실린다**(번호만).
  void announceBattleRoom(String channel, String room);

  /// 조용할 때 "살아 있나" 하고 한 번 찔러본다.
  ///
  /// IRC 는 **서버가** 90초마다 물어봐서 할 일이 없다. 서버 채팅은 아무도 안 물으니
  /// 우리가 보낸다 - 대화가 없어도 뭔가 오가게 하는 것이 목적이다(통신사·공유기가
  /// 조용한 연결을 버리는 것을 막는다).
  void keepalive();

  /// 나간다고 알리고 끝낸다.
  void quit([String reason]);

  /// 서버에서 온 것 하나. IRC 는 줄(String), 서버 채팅은 사전(Map)이다.
  ///
  /// 받는 모양이 다른 것은 **구현이 알아서 한다** - 상태가 "지금 무슨 모양이 오지"를
  /// 알면 또 거기서 갈라진다.
  void handleIncoming(Object raw);
}
