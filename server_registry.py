"""등록된 공용서버 목록 관리 (클라이언트 로컬 저장)
- GUI/CLI 클라이언트가 공용으로 사용
- 실행 파일과 같은 폴더의 servers.json에 저장 - 한 번 등록해두면 계속 재사용 가능
"""
import json
import os
import sys

import app_paths




SERVERS_FILE = os.path.join(app_paths.data_dir(), "servers.json")


def load_servers() -> list[dict]:
    if not os.path.exists(SERVERS_FILE):
        return []
    try:
        with open(SERVERS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return []
    return data.get("servers", [])


def save_servers(servers: list[dict]):
    with open(SERVERS_FILE, "w", encoding="utf-8") as f:
        json.dump({"servers": servers}, f, ensure_ascii=False, indent=2)


def add_server(
    name: str, host: str, port: int, cert_path: str = "", ssl: bool = True, protocol: str = "custom"
) -> list[dict]:
    servers = [s for s in load_servers() if s["name"] != name]
    servers.append(
        {"name": name, "host": host, "port": port, "cert_path": cert_path, "ssl": ssl, "protocol": protocol}
    )
    save_servers(servers)
    return servers


def remove_server(name: str) -> list[dict]:
    servers = [s for s in load_servers() if s["name"] != name]
    save_servers(servers)
    return servers
