"""
자체 서명(self-signed) TLS 인증서 자동 생성
- 서버 최초 실행 시 cert.pem(공개키, 인증서) / key.pem(개인키) 생성
- key.pem은 절대 외부에 공유하면 안 됨 (서버만 보관)
- cert.pem은 클라이언트들에게 나눠줘서 "진짜 이 서버가 맞는지" 검증하는 용도로 사용
"""
import datetime
import os

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

CERT_PATH = os.path.join(os.path.dirname(__file__), "cert.pem")
KEY_PATH = os.path.join(os.path.dirname(__file__), "key.pem")


def ensure_certificate():
    """cert.pem / key.pem이 없으면 새로 생성. 이미 있으면 그대로 사용."""
    if os.path.exists(CERT_PATH) and os.path.exists(KEY_PATH):
        return CERT_PATH, KEY_PATH

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "friend-chat-server")]
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.datetime.utcnow())
        .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("friend-chat-server")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    with open(KEY_PATH, "wb") as f:
        f.write(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )

    with open(CERT_PATH, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))

    return CERT_PATH, KEY_PATH
