/// 춥채팅 모바일 - 들어가는 곳.
///
/// PC 앱과 **같은 서버, 같은 사람들**이다. 무슨 일이 일어났는지 판단하는 규칙은
/// `core/`에 있고 PC의 파이썬 코드와 답을 대조해둔다(`test/`).
///
/// 화면 흐름은 PC 앱과 같다:
///
///     시작화면(로고·버전 확인) --> 로그인 --> 채팅
///
/// 시작화면을 먼저 두는 이유는 PC 앱과 같다 - 새 버전 확인에 잠깐 걸리는데, 그동안
/// 로그인 화면이 떠 있으면 사람이 이름을 치기 시작하고 그 위로 업데이트 안내가 덮친다.
library;

import 'package:flutter/material.dart';

import 'app_state.dart';
import 'prefs.dart';
import 'ui/chat_page.dart';
import 'ui/login_page.dart';
import 'ui/splash_page.dart';

void main() => runApp(const ChupChatApp());

/// 지금 어느 장면인가. 화면은 이 셋뿐이다(mobile/README.md 의 약속).
enum _Scene { splash, login, chat }

class ChupChatApp extends StatefulWidget {
  const ChupChatApp({super.key});

  @override
  State<ChupChatApp> createState() => _ChupChatAppState();
}

class _ChupChatAppState extends State<ChupChatApp>
    with WidgetsBindingObserver {
  final AppState _state = AppState();
  _Scene _scene = _Scene.splash;

  @override
  void initState() {
    super.initState();
    // 홈으로 나갔다 돌아온 것을 알아야 한다 - 그때 다시 붙는다
    WidgetsBinding.instance.addObserver(this);
    Prefs.load().then((loaded) {
      if (mounted) _state.prefs = loaded;
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _state.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState phase) {
    // 홈으로 나가면 안드로이드가 우리를 멈춰서 접속이 끊긴다. 돌아왔을 때 **바로**
    // 다시 붙어야 사람 눈에 먹통으로 안 보인다
    if (phase == AppLifecycleState.resumed) {
      _state.cameBack();
    } else if (phase == AppLifecycleState.paused ||
        phase == AppLifecycleState.hidden) {
      _state.wentBackground();
    }
  }

  /// 버전 확인과 업데이트 안내는 시작화면이 한다(여기서 또 하지 말 것 - 두 번 묻게 된다).
  Widget _page() {
    switch (_scene) {
      case _Scene.splash:
        return SplashPage(onDone: () => setState(() => _scene = _Scene.login));
      case _Scene.login:
        return LoginPage(
          state: _state,
          onDone: () => setState(() => _scene = _Scene.chat),
        );
      case _Scene.chat:
        return ChatPage(state: _state);
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: '춥채팅',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          // PC 앱의 강조색(#7c6cf0)과 같은 계열
          seedColor: const Color(0xFF7C6CF0),
          brightness: Brightness.dark,
        ),
      ),
      home: _page(),
    );
  }
}
