/// 춥채팅 모바일 - 들어가는 곳.
///
/// PC 앱과 **같은 서버, 같은 사람들**이다. 무슨 일이 일어났는지 판단하는 규칙은
/// `core/`에 있고 PC의 파이썬 코드와 답을 대조해둔다(`test/`).
library;

import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'app_state.dart';
import 'net/updater.dart';
import 'ui/chat_page.dart';
import 'ui/login_page.dart';
import 'ui/update_sheet.dart';

void main() => runApp(const ChupChatApp());

class ChupChatApp extends StatefulWidget {
  const ChupChatApp({super.key});

  @override
  State<ChupChatApp> createState() => _ChupChatAppState();
}

class _ChupChatAppState extends State<ChupChatApp> {
  final AppState _state = AppState();
  final GlobalKey<NavigatorState> _nav = GlobalKey<NavigatorState>();
  bool _loggedIn = false;

  @override
  void initState() {
    super.initState();
    // 켤 때 한 번만 확인한다. 스토어가 없으니 아무도 대신 알려주지 않는다 -
    // 그냥 두면 사람마다 다른 버전을 쓰게 되고 "나만 안 보인다"가 생긴다
    WidgetsBinding.instance.addPostFrameCallback((_) => _checkUpdate());
  }

  Future<void> _checkUpdate() async {
    final updater = Updater();
    // 지난번에 받아둔 설치 파일이 있으면 먼저 치운다(50MB짜리가 남아 있을 이유가 없다).
    // 설치 직후에 지우면 설치 화면이 읽는 중이라 깨지므로 여기서 한다
    await updater.cleanLeftover();
    final info = await PackageInfo.fromPlatform();
    final found = await updater.check(info.version);
    if (found == null) return;      // 최신이거나 못 물어봤다 - 조용히 넘어간다
    // 물어보는 사이에 앱이 꺼졌을 수 있다. 그때 화면을 띄우려 하면 예외가 난다
    if (!mounted) return;
    final navigator = _nav.currentState;
    if (navigator == null || !navigator.mounted) return;
    await showUpdate(navigator.context, found);
  }

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      navigatorKey: _nav,
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
      home: _loggedIn
          ? ChatPage(state: _state)
          : LoginPage(
              state: _state,
              onDone: () => setState(() => _loggedIn = true),
            ),
    );
  }
}
