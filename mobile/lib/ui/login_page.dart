/// 로그인 화면 - 서버 주소와 쓸 이름을 받는다.
library;

import 'package:flutter/material.dart';

import '../app_state.dart';
import '../core/irc_protocol.dart';
import '../net/irc_client.dart';

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
  bool _allowBadCert = false;
  bool _busy = false;

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
    // 서버가 거절할 이름을 **보내기 전에** 막는다. 그냥 보내면 서버가 432로 막고
    // 앱은 그걸 "사용 중"으로 보고 _ 를 붙여 다시 시도하다 조용히 포기한다 -
    // 사람 눈에는 "눌렀는데 아무 일도 안 일어남"으로만 보인다
    final problem = nickProblem(nick);
    if (problem.isNotEmpty) {
      setState(() => widget.state.statusText = problem);
      return;
    }
    setState(() => _busy = true);
    final ok = await widget.state.connect(
      host: _host.text.trim(),
      port: int.tryParse(_port.text.trim()) ?? 6697,
      nick: nick,
      password: _password.text,
      secure: _secure,
      allowBadCertificate: _allowBadCert,
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) widget.onDone();
  }

  @override
  Widget build(BuildContext context) {
    final state = widget.state;
    final failed = state.link == LinkState.failed;
    return Scaffold(
      body: SafeArea(
        child: Center(
          // 폴드를 펴면 화면이 넓어지는데 입력칸이 끝까지 늘어나면 보기 나쁘다.
          // 폼은 읽기 좋은 폭에서 멈춘다
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              padding: const EdgeInsets.all(20),
              shrinkWrap: true,
              children: [
                Text('춥채팅', style: Theme.of(context).textTheme.headlineMedium),
                const SizedBox(height: 4),
                Text('PC 앱과 같은 방에서 이야기합니다',
                    style: Theme.of(context).textTheme.bodySmall),
                const SizedBox(height: 24),
                TextField(
                  controller: _nick,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: '쓸 이름',
                    helperText: '채팅방에서 보이는 이름입니다 (영문·숫자만)',
                  ),
                  onSubmitted: (_) => _connect(),
                ),
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
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '비밀번호 (없으면 비워두세요)',
                  ),
                ),
                SwitchListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _secure,
                  onChanged: (v) => setState(() => _secure = v),
                  title: const Text('암호화해서 연결'),
                  subtitle: const Text('보통 6697 포트에서 씁니다'),
                ),
                // 개인 서버는 자체 서명 인증서를 쓰는 일이 흔하다. 다만 켜면 중간에서
                // 가로채는 것을 못 걸러내므로 **사람이 직접 켜게** 둔다
                if (_secure)
                  SwitchListTile(
                    contentPadding: EdgeInsets.zero,
                    value: _allowBadCert,
                    onChanged: (v) => setState(() => _allowBadCert = v),
                    title: const Text('인증서 검사 건너뛰기'),
                    subtitle: const Text('직접 운영하는 서버일 때만 켜세요'),
                  ),
                const SizedBox(height: 16),
                FilledButton(
                  onPressed: _busy ? null : _connect,
                  child: _busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('들어가기'),
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
    );
  }
}
