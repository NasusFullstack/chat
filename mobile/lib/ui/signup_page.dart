/// 회원가입 - **따로 띄운다.**
///
/// 예전에는 로그인 화면에 '계정 만들기' 체크 하나였다. 같은 칸에 아이디와 비밀번호를
/// 적고 체크 하나로 뜻이 바뀌니, 지금 가입을 하는 건지 들어가는 건지 알기 어려웠다.
/// 가입은 한 번뿐이고 들어가기는 매번이라, 둘을 한 화면에 섞을 이유가 없다.
///
/// 여기서만 하는 것:
/// - **비밀번호를 두 번 받는다.** 기기에 저장하지 않으므로 오타가 나면 다음에 못
///   들어온다 - 만들 때 걸러야 한다
/// - 서버가 받아주는 모양인지 **보내기 전에** 본다(`accountProblem`)
/// - 만들고 나면 **그대로 들어간다.** 다시 로그인 화면으로 돌려보내지 않는다
library;

import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import '../app_state.dart';
import '../core/chat_port.dart';
import '../core/server_session.dart' show accountProblem;

class SignupPage extends StatefulWidget {
  const SignupPage({super.key, required this.state});

  final AppState state;

  @override
  State<SignupPage> createState() => _SignupPageState();
}

class _SignupPageState extends State<SignupPage> {
  final _id = TextEditingController();
  final _password = TextEditingController();
  final _again = TextEditingController();
  bool _busy = false;
  String _problem = '';

  @override
  void dispose() {
    _id.dispose();
    _password.dispose();
    _again.dispose();
    super.dispose();
  }

  Future<void> _make() async {
    final id = _id.text.trim();
    final problem = accountProblem(id, _password.text);
    if (problem.isNotEmpty) {
      setState(() => _problem = problem);
      return;
    }
    if (_password.text != _again.text) {
      // **기기에 저장하지 않으므로** 오타가 나면 다음에 못 들어온다
      setState(() => _problem = '비밀번호가 서로 다릅니다.');
      return;
    }
    setState(() {
      _busy = true;
      _problem = '';
    });

    final info = await PackageInfo.fromPlatform();
    final ok = await widget.state.connect(
      kind: ChatKind.server,
      makeAccount: true,
      host: '',
      port: 0,
      nick: id,
      password: _password.text,
      appVersion: info.version,
    );
    if (!mounted) return;
    setState(() => _busy = false);
    if (ok) {
      // 만들었고 들어왔다 - 부른 쪽(로그인 화면)이 채팅으로 넘긴다
      Navigator.pop(context, true);
    } else {
      setState(() => _problem = widget.state.statusText.isEmpty
          ? '계정을 만들지 못했습니다.'
          : widget.state.statusText);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('계정 만들기')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 420),
            child: ListView(
              padding: const EdgeInsets.all(20),
              shrinkWrap: true,
              children: [
                Text('춥채팅 서버에서 쓸 계정입니다.',
                    style: Theme.of(context).textTheme.bodyMedium),
                const SizedBox(height: 16),
                TextField(
                  controller: _id,
                  autofocus: true,
                  decoration: const InputDecoration(
                    labelText: '아이디',
                    helperText: '영문·숫자 2~24자 (_ . - 도 됩니다)',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _password,
                  obscureText: true,
                  decoration: const InputDecoration(
                    labelText: '비밀번호',
                    helperText: '4자 이상',
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _again,
                  obscureText: true,
                  decoration: const InputDecoration(labelText: '비밀번호 다시'),
                  onSubmitted: (_) => _make(),
                ),
                const SizedBox(height: 10),
                const Text(
                  '비밀번호는 기기에 저장하지 않습니다 - 켤 때마다 입력해야 하니 잊지 마세요.',
                  style: TextStyle(fontSize: 12),
                ),
                const SizedBox(height: 18),
                FilledButton(
                  onPressed: _busy ? null : _make,
                  child: _busy
                      ? const SizedBox(
                          height: 18,
                          width: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('만들고 들어가기'),
                ),
                if (_problem.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Text(
                    _problem,
                    style:
                        TextStyle(color: Theme.of(context).colorScheme.error),
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
