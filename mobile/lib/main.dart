/// 춥채팅 모바일 - 들어가는 곳.
///
/// PC 앱과 **같은 서버, 같은 사람들**이다. 무슨 일이 일어났는지 판단하는 규칙은
/// `core/`에 있고 PC의 파이썬 코드와 답을 대조해둔다(`test/`).
library;

import 'package:flutter/material.dart';

import 'app_state.dart';
import 'ui/chat_page.dart';
import 'ui/login_page.dart';

void main() => runApp(const ChupChatApp());

class ChupChatApp extends StatefulWidget {
  const ChupChatApp({super.key});

  @override
  State<ChupChatApp> createState() => _ChupChatAppState();
}

class _ChupChatAppState extends State<ChupChatApp> {
  final AppState _state = AppState();
  bool _loggedIn = false;

  @override
  void dispose() {
    _state.dispose();
    super.dispose();
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
      home: _loggedIn
          ? ChatPage(state: _state)
          : LoginPage(
              state: _state,
              onDone: () => setState(() => _loggedIn = true),
            ),
    );
  }
}
