/// 로그인 화면 - 위에 로고, 아래에 버전.
///
/// **들어가기는 소켓이 붙는 것으로 끝나지 않는다.** IRC 는 서버가 001 을 보내줘야
/// '등록된 사용자'가 된다. 그 전에 채팅 화면으로 넘어가면, 채널 입장을 눌러도 서버가
/// 조용히 무시해서 "눌렀는데 아무 일도 안 일어남"이 된다. 그래서 로그인이 끝난 뒤에만
/// 넘어간다(app_state.dart 의 connect 가 거기까지 기다린다).
library;

import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../app_state.dart';
import '../core/chat_port.dart';
import '../core/irc_protocol.dart';
import '../core/server_session.dart' show accountProblem;
import '../login_store.dart';
import '../net/irc_client.dart';
import '../net/trusted_certs.dart' as certs;
import 'splash_page.dart' show developer;

class LoginPage extends StatefulWidget {
  const LoginPage({super.key, required this.state, required this.onDone});

  final AppState state;
  final VoidCallback onDone;

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  // PC 앱과 같은 기본값. 여기 처음 오는 사람이 아무것도 안 고치고 들어갈 수 있게
  final _host = TextEditingController(text: 'home.pdlab.kr');
  final _port = TextEditingController(text: '6697');
  final _nick = TextEditingController();
  final _password = TextEditingController();
  bool _secure = true;
  bool _busy = false;

  /// IRC 로 갈까 서버 채팅으로 갈까. **앞단계**다 - 이 고름에 따라 아래 칸이 바뀐다
  ChatKind _kind = ChatKind.irc;

  /// 서버 채팅에서 **계정부터 만들까**. 가입이 끝나면 이어서 알아서 들어간다
  bool _makeAccount = false;

  /// 기억해둔 이름이 있으면 **알아서 들어간다.** 폰에서 글자 치는 것은 번거로워서,
  /// 켤 때마다 이름을 다시 받으면 그것만으로 안 쓰게 된다
  bool _ready = false;

  /// 버전은 **앱이 스스로 읽는다.** 화면에 숫자를 적어두면 올릴 때마다 여기도 고쳐야
  /// 하고, 한 번만 빠뜨려도 엉뚱한 버전이 표시된다
  String _version = '';

  @override
  void initState() {
    super.initState();
    PackageInfo.fromPlatform().then((info) {
      if (mounted) setState(() => _version = info.version);
    });
    _restore();
  }

  /// 지난번 접속을 되살린다. 자동이 켜져 있으면 그대로 들어간다.
  ///
  /// **어느 쪽이었는지를 먼저 읽는다.** 설정이 쪽마다 따로라서, 쪽을 모르면 어느
  /// 칸을 채워야 할지도 모른다
  Future<void> _restore() async {
    final kind = await loadLastKind();
    final last = await loadLastLogin(kind);
    if (!mounted) return;
    setState(() {
      _kind = kind;
      _fill(last);
      _ready = true;
    });
    if (last.canAuto) await _connect();
  }

  /// 기억해둔 값을 칸에 넣는다.
  void _fill(LastLogin last) {
    _host.text = last.host;
    _port.text = '${last.port}';
    _nick.text = last.nick;
    _secure = last.secure;
    widget.state.rememberLogin = last.remember;
    widget.state.autoLogin = last.auto;
  }

  /// 쪽을 바꿨다 - **그쪽이 기억해둔 것으로 갈아 끼운다.**
  ///
  /// 칸을 그대로 두면 IRC 닉네임이 서버 채팅 아이디 칸에 남아 있게 되고, 그걸
  /// 그대로 보내면 로그인이 실패한다. 설정을 나눠둔 뜻이 여기서 드러난다
  Future<void> _switchKind(ChatKind kind) async {
    if (kind == _kind) return;
    final last = await loadLastLogin(kind);
    if (!mounted) return;
    setState(() {
      _kind = kind;
      _makeAccount = false;
      _password.clear();
      _fill(last);
      widget.state.statusText = '';
    });
  }

  @override
  void dispose() {
    _host.dispose();
    _port.dispose();
    _nick.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _connect() async {
    final nick = _nick.text.trim();
    // 서버가 거절할 것을 **보내기 전에** 막는다. IRC 는 그냥 보내면 서버가 432 로
    // 막고, 앱은 그걸 "사용 중"으로 보고 _ 를 붙여 다시 시도하다 조용히 포기한다.
    // 규칙이 쪽마다 다르므로 묻는 곳도 다르다(한쪽 규칙을 양쪽에 쓰면 안 된다)
    final problem = _kind == ChatKind.server
        ? accountProblem(nick, _password.text)
        : nickProblem(nick);
    if (problem.isNotEmpty) {
      setState(() => widget.state.statusText = problem);
      return;
    }
    setState(() => _busy = true);

    final host = _host.text.trim();
    final port = int.tryParse(_port.text.trim()) ?? 6697;
    // 참여자 목록에 춥채팅 배지와 폰 표시를 띄우려면 우리 버전을 알려줘야 한다
    final info = await PackageInfo.fromPlatform();

    var ok = await _tryConnect(host, port, nick, info.version);

    // 처음 보는 인증서라 못 붙은 경우 - 지문을 보여주고 한 번만 묻는다.
    // **서버 채팅에는 이 길이 없다**(정식 인증서라 물어볼 것이 없다 - 늘 빈 값)
    if (!ok && widget.state.pendingFingerprint.isNotEmpty && mounted) {
      final agreed = await _askTrust(
          host, widget.state.pendingFingerprint, widget.state.fingerprintChanged);
      if (agreed) {
        await certs.trust(host, port, widget.state.pendingFingerprint);
        ok = await _tryConnect(host, port, nick, info.version);
      } else if (mounted) {
        setState(() => widget.state.statusText = '보안 접속을 취소했습니다.');
      }
    }

    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) widget.onDone();
  }

  Future<bool> _tryConnect(String host, int port, String nick, String version) {
    return widget.state.connect(
      kind: _kind,
      makeAccount: _kind == ChatKind.server && _makeAccount,
      host: host,
      port: port,
      nick: nick,
      password: _password.text,
      secure: _secure,
      appVersion: version,
    );
  }

  /// 자체 서명 인증서를 만났을 때 - 지문을 보여주고 한 번만 묻는다.
  ///
  /// 개인이 돌리는 서버는 대개 이렇다. 무조건 막으면 못 붙고, 무조건 넘기면 가짜
  /// 서버를 구분할 수 없다. 그래서 사람이 한 번 보고 정하고, 그 뒤로는 기억한다.
  Future<bool> _askTrust(String host, String fingerprint, bool changed) async {
    final answer = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(changed ? '인증서가 달라졌습니다' : '처음 접속하는 서버입니다'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(changed
                ? '$host의 인증서가 예전과 다릅니다.\n'
                    '서버를 바꾼 것이 아니라면 위험합니다.'
                : '$host은(는) 자체 서명 인증서를 씁니다.\n'
                    '개인이 운영하는 서버는 대부분 이렇습니다.'),
            const SizedBox(height: 12),
            Text('인증서 지문', style: Theme.of(ctx).textTheme.labelMedium),
            const SizedBox(height: 4),
            SelectableText(fingerprint,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 11)),
          ],
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false), child: const Text('취소')),
          FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('이 서버 신뢰')),
        ],
      ),
    );
    return answer ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final failed = state.link == LinkState.failed;
    final server = _kind == ChatKind.server;
    return Scaffold(
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: Center(
                // 폴드를 펴면 화면이 넓어지는데 입력칸이 끝까지 늘어나면 보기 나쁘다.
                // 폼은 읽기 좋은 폭에서 멈춘다
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 420),
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                    shrinkWrap: true,
                    children: [
                      Center(
                        child: Image.asset('assets/logo.png',
                            width: 92,
                            height: 92,
                            filterQuality: FilterQuality.medium),
                      ),
                      const SizedBox(height: 10),
                      Center(
                        // 로고 바로 아래는 "이게 무슨 앱이고 몇 버전인가" 자리다.
                        // 버전을 아직 못 읽었으면 이름만 - 빈 줄이 깜빡이지 않게
                        child: Text(
                          _version.isEmpty ? '춥채팅' : '춥채팅 v$_version',
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                      ),
                      const SizedBox(height: 18),
                      // **어디로 갈까**가 먼저다. 이 고름에 따라 아래 칸이 바뀐다 -
                      // IRC 는 주소를 적어야 하고, 서버 채팅은 적을 것이 없다
                      SegmentedButton<ChatKind>(
                        segments: [
                          ButtonSegment(
                            value: ChatKind.server,
                            label: Text(ChatKind.server.label),
                            icon: const Icon(Icons.chat_bubble_outline, size: 18),
                          ),
                          ButtonSegment(
                            value: ChatKind.irc,
                            label: Text(ChatKind.irc.label),
                            icon: const Icon(Icons.dns_outlined, size: 18),
                          ),
                        ],
                        selected: {_kind},
                        onSelectionChanged:
                            _busy ? null : (picked) => _switchKind(picked.first),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        server
                            ? '한글 이름·긴 글·큰 아이콘이 되고, 지난 대화가 들어갈 때 같이 옵니다.'
                            : '아무 IRC 서버에나 붙을 수 있습니다. 한글 이름은 서버가 거절합니다.',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color:
                                  Theme.of(context).colorScheme.onSurfaceVariant,
                            ),
                      ),
                      const SizedBox(height: 16),
                      TextField(
                        controller: _nick,
                        // 기억해둔 이름이 있으면 자판을 올리지 않는다 - 알아서
                        // 들어가는 중에 자판이 올라왔다 내려가면 어지럽다
                        autofocus: _ready && _nick.text.isEmpty,
                        decoration: InputDecoration(
                          labelText: server ? '아이디' : '쓸 이름',
                          helperText: server
                              ? '로그인에 쓰는 아이디입니다 (영문·숫자 2~24자)'
                              : '채팅방에서 보이는 이름입니다 (영문·숫자만)',
                        ),
                        onSubmitted: (_) => _connect(),
                      ),
                      // 주소·포트·암호화는 **IRC 에만 있다.** 서버 채팅은 우리 서버
                      // 하나뿐이라 적을 것이 없다(잘못 적어 "왜 안 되지"가 될 여지도 없다)
                      if (!server) ...[
                        const SizedBox(height: 12),
                        TextField(
                          controller: _host,
                          decoration: const InputDecoration(labelText: '서버 주소'),
                        ),
                        const SizedBox(height: 12),
                        TextField(
                          controller: _port,
                          keyboardType: TextInputType.number,
                          decoration: const InputDecoration(labelText: '포트'),
                        ),
                      ],
                      const SizedBox(height: 12),
                      TextField(
                        controller: _password,
                        obscureText: true,
                        decoration: InputDecoration(
                          labelText: server ? '비밀번호' : '비밀번호 (없으면 비워두세요)',
                          // 기기에 안 남기므로 켤 때마다 받아야 한다
                          helperText: server
                              ? '기기에 저장하지 않습니다 - 켤 때마다 입력해 주세요'
                              : null,
                        ),
                        onSubmitted: (_) => _connect(),
                      ),
                      if (server)
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          controlAffinity: ListTileControlAffinity.leading,
                          dense: true,
                          value: _makeAccount,
                          onChanged: (on) =>
                              setState(() => _makeAccount = on ?? false),
                          title: const Text('계정 만들기'),
                          subtitle:
                              const Text('처음이라면 켜세요. 만든 뒤 바로 들어갑니다'),
                        ),
                      if (!server)
                        SwitchListTile(
                          contentPadding: EdgeInsets.zero,
                          value: _secure,
                          onChanged: (v) => setState(() => _secure = v),
                          title: const Text('암호화해서 연결'),
                          subtitle: const Text('보통 6697 포트에서 씁니다'),
                        ),
                      // 폰에서 글자 치는 것은 번거롭다. 기본은 기억하는 쪽이고,
                      // 끄면 적어둔 이름을 지운다
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        controlAffinity: ListTileControlAffinity.leading,
                        dense: true,
                        value: widget.state.rememberLogin,
                        onChanged: (on) => setState(() {
                          widget.state.rememberLogin = on ?? true;
                          // 이름을 안 기억하면 알아서 들어갈 수도 없다
                          if (!widget.state.rememberLogin) {
                            widget.state.autoLogin = false;
                          }
                        }),
                        title: const Text('이름 기억하기'),
                      ),
                      // **서버 채팅은 알아서 들어갈 수 없다** - 비밀번호를 기기에
                      // 안 남기기 때문이다. 켜 둘 수 있게 보여주면 거짓말이 된다
                      if (!server)
                        CheckboxListTile(
                          contentPadding: EdgeInsets.zero,
                          controlAffinity: ListTileControlAffinity.leading,
                          dense: true,
                          value: widget.state.autoLogin,
                          onChanged: widget.state.rememberLogin
                              ? (on) => setState(
                                  () => widget.state.autoLogin = on ?? true)
                              : null,
                          title: const Text('켤 때 알아서 들어가기'),
                        ),
                      const SizedBox(height: 10),
                      FilledButton(
                        onPressed: _busy ? null : _connect,
                        child: _busy
                            ? const SizedBox(
                                height: 18,
                                width: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : Text(server && _makeAccount
                                ? '계정 만들고 들어가기'
                                : '들어가기'),
                      ),
                      if (state.statusText.isNotEmpty) ...[
                        const SizedBox(height: 14),
                        Text(
                          state.statusText,
                          style: TextStyle(
                            color: failed
                                ? Theme.of(context).colorScheme.error
                                : Theme.of(context).colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
            // 버전은 로고 아래에 있으므로 여기서 또 적지 않는다 - 한 화면에 같은
            // 글자가 둘이면 어느 쪽을 봐야 할지 헷갈린다. 만든 사람만 남긴다
            Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: Text(
                'made by $developer',
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onSurfaceVariant,
                    ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
