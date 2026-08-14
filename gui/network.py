"""서버와의 TLS 소켓 통신 (커스텀 JSON 프로토콜 / 실제 IRC 프로토콜 둘 다 지원)."""
import json
import time
from collections import deque

# 사고 직전에 서버가 뭘 보냈는지 알아보려고 남겨두는 줄 수
RECENT_LINE_COUNT = 40

from PySide6.QtCore import Signal
from PySide6.QtCore import QCryptographicHash
from PySide6.QtNetwork import QSslSocket, QSslCertificate, QSslConfiguration, QSslError

import irc_protocol
import trusted_certs


class ChatClient(QSslSocket):
    """서버와의 TLS 소켓 통신 + 라인 프로토콜 파싱을 담당 (커스텀 JSON 프로토콜 / 실제 IRC 프로토콜 둘 다 지원)"""

    message_received = Signal(dict)
    irc_line_received = Signal(object)
    connection_failed = Signal(str)
    # 서버 인증서를 확인할 수 없을 때(자체 서명 등). 사람에게 물어보라는 뜻이다.
    # (주소, 포트, 지문, 이유)
    certificate_untrusted = Signal(str, int, str, str)

    def __init__(self):
        super().__init__()
        self._buffer = b""
        self.last_rx_at = time.time()
        # 서버에서 받은 마지막 줄들. 채널에서 빠지거나 화면이 비는 사고가 났을 때
        # "그 직전에 서버가 뭘 보냈는지"를 알아야 원인을 찾을 수 있다(재현이 안 되는
        # 증상이라 이 기록이 유일한 단서다). 개수를 제한해서 메모리는 늘지 않는다.
        self._recent = deque(maxlen=RECENT_LINE_COUNT)
        self._mode = "custom"
        self._pinned_cert = False
        self.readyRead.connect(self._on_ready_read)
        self.errorOccurred.connect(self._on_error)
        self.sslErrors.connect(self._on_ssl_errors)
        # 끊김을 알려주는 경로가 없어서, 서버가 죽어도 화면상으론 멀쩡해 보였음
        self.disconnected.connect(self._on_disconnected)
        self.encrypted.connect(self._on_encrypted)
        self._pending_host = ""
        self._pending_port = 0
        self._trusted_fingerprint = ""

    def recent_lines(self) -> list[str]:
        """서버에서 받은 마지막 줄들(오래된 것부터). 사고 원인을 찾을 때 씀."""
        return list(self._recent)

    def _on_disconnected(self):
        # 다시 붙을 때 이전 연결의 남은 조각이 섞이지 않도록 버퍼를 비움
        self._buffer = b""

    def set_mode(self, mode: str):
        """연결 시작 전에 호출: "custom"(친구 채팅 서버 JSON) 또는 "irc"(실제 IRC 서버)"""
        self._mode = mode

    def connect_to_server(self, host: str, port: int, cert_path: str, use_ssl: bool):
        if not use_ssl:
            self.connectToHost(host, port)
            return
        self._pinned_cert = bool(cert_path)
        config = QSslConfiguration.defaultConfiguration()
        if cert_path:
            certs = QSslCertificate.fromPath(cert_path)
            if not certs:
                self.connection_failed.emit(f"인증서 파일을 읽을 수 없습니다: {cert_path}")
                return
            config.setCaCertificates(certs)
        # setSslConfiguration()이 peerVerifyMode를 기본값으로 되돌려버리므로,
        # 반드시 setSslConfiguration() 이후에 setPeerVerifyMode()를 호출해야 함
        # (먼저 호출하면 아래에서 덮어써져 무시됨).
        self.setSslConfiguration(config)
        self._pending_host = host
        self._pending_port = port
        self._trusted_fingerprint = trusted_certs.fingerprint_of(host, port)
        if self._trusted_fingerprint:
            # 사용자가 예전에 직접 확인하고 신뢰하기로 한 서버다. 시스템 검증은 통과하지
            # 못하지만(자체 서명), 대신 **지문이 그때와 같은지** 우리가 직접 확인한다.
            # 검증을 끄고 붙은 뒤 encrypted 시점에 지문을 대조한다 - 윈도우 기본 TLS
            # 백엔드에서는 ignoreSslErrors()로 이 오류를 넘길 수 없기 때문이다
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
        elif cert_path or self._mode == "irc":
            # cert.pem을 지정한 경우(우리 서버, 자체 서명 인증서 핀닝) 뿐 아니라
            # 실제 IRC 서버 모드도 표준 방식으로 검증한다 (정식 CA 인증서를 쓰는 서버는
            # 이 경로로 조용히 통과한다). 자체 서명 서버라면 아래 sslErrors에서 걸리고,
            # 그때 사용자에게 한 번 물어본다
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyPeer)
        else:
            # Windows 기본 TLS 백엔드(Schannel)는 QueryPeer + ignoreSslErrors()로
            # "루트 인증서 미신뢰" 오류를 무시하지 못하고 핸드셰이크를 그대로 실패시킴.
            # 인증서 검증 자체를 생략하는 VerifyNone을 써야 암호화만 하는 접속이 실제로 됨.
            self.setPeerVerifyMode(QSslSocket.PeerVerifyMode.VerifyNone)
        self.connectToHostEncrypted(host, port)

    def send_cmd(self, payload: dict):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        self.write(data)

    def send_irc(self, line: str):
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        self.write(irc_protocol.encode_line(line))

    def flush_pending(self, timeout_ms: int = 700):
        """쓴 내용이 실제로 나갈 때까지 잠깐 기다린다.

        write()는 바로 보내는 게 아니라 예약만 한다. 종료 직전에 QUIT을 쓰고 곧바로
        소켓을 닫으면 그 줄이 나가지 못하고 사라진다 - 그러면 QUIT을 보낸 의미가 없다.
        """
        if self.state() != QSslSocket.SocketState.ConnectedState:
            return
        self.flush()
        self.waitForBytesWritten(timeout_ms)

    def _on_ready_read(self):
        # 마지막으로 뭔가 받은 시각. TCP는 상대가 조용히 사라져도 한참 모르기 때문에,
        # "얼마나 조용했는가"가 연결이 살아 있는지 판단하는 유일한 근거다
        self.last_rx_at = time.time()
        self._buffer += bytes(self.readAll())
        if self._mode == "irc":
            self._process_irc_buffer()
        else:
            self._process_custom_buffer()

    def _process_custom_buffer(self):
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            if not line.strip():
                continue
            try:
                msg = json.loads(line.decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            self.message_received.emit(msg)

    def _process_irc_buffer(self):
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            text = line.decode("utf-8", errors="replace")
            if not text.strip():
                continue
            self._recent.append(text[:200])
            msg = irc_protocol.parse_line(text)
            if msg.command == "PING":
                # 연결 유지의 핵심 - UI 상태와 무관하게 즉시 응답해야 서버가 끊지 않음
                self.write(irc_protocol.encode_line(irc_protocol.format_pong(msg.trailing)))
                continue
            self.irc_line_received.emit(msg)

    def _on_encrypted(self):
        """암호화 연결이 맺어졌다. 신뢰하기로 한 서버면 지문이 그대로인지 본다.

        지문이 바뀌었다면 서버를 갈아탄 것일 수도, 누가 중간에 낀 것일 수도 있다.
        어느 쪽이든 사람이 다시 확인해야 하므로 그냥 잇지 않는다.
        """
        if not self._trusted_fingerprint:
            return
        certificate = self.peerCertificate()
        now = ""
        if certificate is not None and not certificate.isNull():
            now = bytes(certificate.digest(QCryptographicHash.Algorithm.Sha256)).hex()
        if now and now != self._trusted_fingerprint:
            self.abort()
            self.certificate_untrusted.emit(self._pending_host, self._pending_port, now,
                                            "예전에 확인한 인증서와 다릅니다")

    def _on_error(self, _error):
        # state()는 handshake 실패 시점에도 여전히 ConnectedState를 보고하는 경우가 있어
        # (Qt가 Closing/Unconnected로 전이하기 전에 errorOccurred를 먼저 emit) 상태로
        # 판단하지 않고 항상 알림. 로그인 이후 발생하는 에러는 MainWindow 쪽에서
        # _connecting 플래그로 걸러낸다.
        self.connection_failed.emit(self.errorString())

    def _on_ssl_errors(self, errors: list[QSslError]):
        if (self._mode == "irc" and not self._pinned_cert
                and self.peerVerifyMode() == QSslSocket.PeerVerifyMode.VerifyPeer):
            # 개인 서버는 대개 자체 서명 인증서를 쓴다. 무조건 막으면 그 서버에는 영영
            # 못 붙고, 무조건 넘기면 가짜 서버를 구분할 수 없다. 그래서 **한 번 묻는다**
            certificate = self.peerCertificate()
            fingerprint = ""
            if certificate is not None and not certificate.isNull():
                fingerprint = bytes(
                    certificate.digest(QCryptographicHash.Algorithm.Sha256)).hex()
            reasons = "; ".join(error.errorString() for error in errors)
            self.abort()
            self.certificate_untrusted.emit(self._pending_host, self._pending_port,
                                            fingerprint, reasons)
            return
        if self.peerVerifyMode() == QSslSocket.PeerVerifyMode.VerifyNone:
            # cert.pem 없이 접속: 암호화만 하고 신원 검증은 생략
            self.ignoreSslErrors()
            return
        if not self._pinned_cert:
            # cert.pem 지정 없이 VerifyPeer인 경우 = 실제 IRC 서버 표준 검증 모드.
            # 우리가 지정한 CA 목록이 없으므로 시스템 신뢰 판단을 그대로 따른다
            # (아무것도 무시하지 않음 - 위조/무효 인증서는 그대로 거부되어야 정상).
            return
        # cert.pem으로 검증하는 경우: CaCertificates에 등록해둔 바로 그 인증서와
        # 일치하는지는 반드시 확인하되, 다음 두 오류만 무시한다.
        # - HostNameMismatch: 자체 서명 인증서라 IP/도메인이 뭐든 같은 인증서를 씀
        # - SelfSignedCertificate: 우리가 CaCertificates로 정확히 이 인증서를 이미
        #   신뢰 목록에 넣었으므로 자체 서명이라는 사실 자체는 문제가 아님
        # (다른/가짜 인증서를 준 경우엔 CertificateUntrusted 등 다른 오류가 남기 때문에
        # 여전히 거부됨 - 등록한 인증서와 다르면 접속이 실패해야 정상)
        ignorable = {QSslError.SslError.HostNameMismatch, QSslError.SslError.SelfSignedCertificate}
        real_errors = [e for e in errors if e.error() not in ignorable]
        if not real_errors:
            self.ignoreSslErrors()
