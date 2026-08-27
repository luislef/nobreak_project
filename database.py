"""
Persistência SQLite para cadastro de nobreaks e histórico de leituras.
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional

BASE_DIR = Path(__file__).resolve().parent


def get_db_path() -> str:
    return os.environ.get("NOBREAK_DB_PATH", str(BASE_DIR / "nobreaks.db"))


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nobreaks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                auth_required INTEGER NOT NULL DEFAULT 0,
                protocol TEXT NOT NULL DEFAULT 'legacy'
            );

            CREATE TABLE IF NOT EXISTS leituras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nobreak_id INTEGER NOT NULL REFERENCES nobreaks(id) ON DELETE CASCADE,
                collected_at TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetch_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_leituras_nobreak_collected
                ON leituras (nobreak_id, collected_at DESC);

            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nobreak_id INTEGER NOT NULL REFERENCES nobreaks(id) ON DELETE CASCADE,
                event_date TEXT NOT NULL,
                data_hora TEXT NOT NULL,
                codigo TEXT,
                descricao TEXT,
                fetched_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_eventos_nobreak_date
                ON eventos (nobreak_id, event_date);

            CREATE TABLE IF NOT EXISTS medidores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ip TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                loja TEXT,
                device_type TEXT NOT NULL,
                api_path TEXT NOT NULL,
                page_path TEXT,
                auth_required INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS medicoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                medidor_id INTEGER NOT NULL REFERENCES medidores(id) ON DELETE CASCADE,
                collected_at TEXT NOT NULL,
                status TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                fetch_error TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_medicoes_medidor_collected
                ON medicoes (medidor_id, collected_at DESC);
            """
        )
        # Migração leve: instalações antigas podem não ter a coluna protocol
        cols = {row[1] for row in conn.execute("PRAGMA table_info(nobreaks)").fetchall()}
        if "protocol" not in cols:
            conn.execute(
                "ALTER TABLE nobreaks ADD COLUMN protocol TEXT NOT NULL DEFAULT 'legacy'"
            )
            # Defaults conhecidos do firmware novo (JSON), antes da coluna existir
            for special_ip in ("192.168.105.168", "192.168.115.168"):
                conn.execute(
                    "UPDATE nobreaks SET protocol = 'special' WHERE ip = ?",
                    (special_ip,),
                )


def sync_nobreaks(
    ips: list,
    names: dict,
    auth_required_ips: Iterable[str],
    special_ips: Optional[Iterable[str]] = None,
) -> None:
    """
    Insere nobreaks novos com defaults.
    Em conflito, só atualiza o nome — protocol/auth ficam sob controle do usuário.
    """
    auth_set = set(auth_required_ips)
    special_set = set(special_ips or [])
    rows = [
        (
            ip,
            names.get(ip, ip),
            1 if ip in auth_set else 0,
            "special" if ip in special_set else "legacy",
        )
        for ip in ips
    ]
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO nobreaks (ip, display_name, auth_required, protocol)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                display_name = excluded.display_name
            """,
            rows,
        )


def get_nobreak_configs() -> list:
    """Lista configs de todos os nobreaks (protocolo + auth)."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT ip, display_name, auth_required, protocol
            FROM nobreaks
            ORDER BY ip
            """
        )
        return [
            {
                "ip": row["ip"],
                "name": row["display_name"],
                "auth_required": bool(row["auth_required"]),
                "protocol": row["protocol"] or "legacy",
            }
            for row in cur.fetchall()
        ]


def get_nobreak_config_map() -> Dict[str, dict]:
    return {cfg["ip"]: cfg for cfg in get_nobreak_configs()}


def update_nobreak_config(
    ip: str,
    protocol: Optional[str] = None,
    auth_required: Optional[bool] = None,
) -> Optional[dict]:
    """Atualiza protocol e/ou auth_required de um nobreak. Retorna a config ou None."""
    allowed = {"legacy", "special"}
    with _connect() as conn:
        cur = conn.execute(
            "SELECT ip, display_name, auth_required, protocol FROM nobreaks WHERE ip = ?",
            (ip,),
        )
        row = cur.fetchone()
        if row is None:
            return None

        new_protocol = row["protocol"] or "legacy"
        new_auth = int(row["auth_required"])
        if protocol is not None:
            if protocol not in allowed:
                raise ValueError(f"protocol inválido: {protocol}")
            new_protocol = protocol
        if auth_required is not None:
            new_auth = 1 if auth_required else 0

        conn.execute(
            """
            UPDATE nobreaks
            SET protocol = ?, auth_required = ?
            WHERE ip = ?
            """,
            (new_protocol, new_auth, ip),
        )
        return {
            "ip": ip,
            "name": row["display_name"],
            "auth_required": bool(new_auth),
            "protocol": new_protocol,
        }


def is_special_protocol(ip: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("SELECT protocol FROM nobreaks WHERE ip = ?", (ip,))
        row = cur.fetchone()
        if row is None:
            return False
        return (row["protocol"] or "legacy") == "special"


def needs_auth(ip: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("SELECT auth_required FROM nobreaks WHERE ip = ?", (ip,))
        row = cur.fetchone()
        return bool(row["auth_required"]) if row else False


def _nobreak_id(conn: sqlite3.Connection, ip: str) -> Optional[int]:
    cur = conn.execute("SELECT id FROM nobreaks WHERE ip = ?", (ip,))
    row = cur.fetchone()
    return int(row["id"]) if row else None


def save_leitura(ip: str, data: dict) -> None:
    """Grava uma leitura completa (estrutura retornada por fetch_data / get_error_data)."""
    payload = json.dumps(data, ensure_ascii=False)
    err = data.get("error")
    collected = datetime.now().isoformat(timespec="seconds")

    with _connect() as conn:
        nid = _nobreak_id(conn, ip)
        if nid is None:
            conn.execute(
                "INSERT INTO nobreaks (ip, display_name, auth_required) VALUES (?, ?, 0)",
                (ip, ip),
            )
            nid = _nobreak_id(conn, ip)
        conn.execute(
            """
            INSERT INTO leituras (nobreak_id, collected_at, payload_json, fetch_error)
            VALUES (?, ?, ?, ?)
            """,
            (nid, collected, payload, err),
        )


def save_leituras_batch(ip_to_data: Dict[str, dict]) -> None:
    """Grava várias leituras na mesma transação."""
    collected = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        for ip, data in ip_to_data.items():
            payload = json.dumps(data, ensure_ascii=False)
            err = data.get("error")
            nid = _nobreak_id(conn, ip)
            if nid is None:
                conn.execute(
                    "INSERT INTO nobreaks (ip, display_name, auth_required) VALUES (?, ?, 0)",
                    (ip, ip),
                )
                nid = _nobreak_id(conn, ip)
            conn.execute(
                """
                INSERT INTO leituras (nobreak_id, collected_at, payload_json, fetch_error)
                VALUES (?, ?, ?, ?)
                """,
                (nid, collected, payload, err),
            )


def save_eventos_from_results(results: list, event_date: str) -> None:
    """
    Substitui os eventos armazenados para cada nobreak na data informada
    pelos resultados de fetch_all_event_logs.
    """
    fetched = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        for result in results:
            ip = result.get("ip")
            if not ip:
                continue
            nid = _nobreak_id(conn, ip)
            if nid is None:
                conn.execute(
                    "INSERT INTO nobreaks (ip, display_name, auth_required) VALUES (?, ?, 0)",
                    (ip, ip),
                )
                nid = _nobreak_id(conn, ip)
            conn.execute(
                "DELETE FROM eventos WHERE nobreak_id = ? AND event_date = ?",
                (nid, event_date),
            )
            if result.get("status") != "success" or not result.get("events"):
                continue
            conn.executemany(
                """
                INSERT INTO eventos (nobreak_id, event_date, data_hora, codigo, descricao, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        nid,
                        event_date,
                        ev.get("data_hora", ""),
                        ev.get("codigo", ""),
                        ev.get("descricao", ""),
                        fetched,
                    )
                    for ev in result["events"]
                ],
            )


def get_latest_leituras(limit_per_nobreak: int = 1) -> list:
    """Últimas leituras por nobreak (para consulta via API)."""
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT n.ip, n.display_name, l.collected_at, l.payload_json, l.fetch_error
            FROM nobreaks n
            JOIN leituras l ON l.nobreak_id = n.id
            WHERE l.id IN (
                SELECT l2.id FROM leituras l2
                WHERE l2.nobreak_id = n.id
                ORDER BY l2.collected_at DESC
                LIMIT ?
            )
            ORDER BY n.ip
            """,
            (limit_per_nobreak,),
        )
        rows = []
        for row in cur.fetchall():
            rows.append({
                "ip": row["ip"],
                "name": row["display_name"],
                "collected_at": row["collected_at"],
                "data": json.loads(row["payload_json"]),
                "fetch_error": row["fetch_error"],
            })
        return rows


def sync_medidores(configs: list) -> None:
    rows = [
        (
            c["ip"],
            c["display_name"],
            c.get("loja", ""),
            c["device_type"],
            c["api_path"],
            c.get("page_path", ""),
            1 if c.get("auth_required") else 0,
        )
        for c in configs
    ]
    with _connect() as conn:
        conn.executemany(
            """
            INSERT INTO medidores (ip, display_name, loja, device_type, api_path, page_path, auth_required)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ip) DO UPDATE SET
                display_name = excluded.display_name,
                loja = excluded.loja,
                device_type = excluded.device_type,
                api_path = excluded.api_path,
                page_path = excluded.page_path,
                auth_required = excluded.auth_required
            """,
            rows,
        )


def _medidor_id(conn: sqlite3.Connection, ip: str) -> Optional[int]:
    cur = conn.execute("SELECT id FROM medidores WHERE ip = ?", (ip,))
    row = cur.fetchone()
    return int(row["id"]) if row else None


def save_medicoes_batch(ip_to_data: Dict[str, dict]) -> None:
    collected = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        for ip, data in ip_to_data.items():
            payload = json.dumps(data, ensure_ascii=False)
            err = data.get("error")
            status = data.get("status", "unknown")
            mid = _medidor_id(conn, ip)
            if mid is None:
                conn.execute(
                    """
                    INSERT INTO medidores (ip, display_name, loja, device_type, api_path, page_path, auth_required)
                    VALUES (?, ?, ?, ?, ?, ?, 0)
                    """,
                    (
                        ip,
                        data.get("name", ip),
                        data.get("loja", ""),
                        data.get("device_type", "unknown"),
                        "",
                        "",
                    ),
                )
                mid = _medidor_id(conn, ip)
            conn.execute(
                """
                INSERT INTO medicoes (medidor_id, collected_at, status, payload_json, fetch_error)
                VALUES (?, ?, ?, ?, ?)
                """,
                (mid, collected, status, payload, err),
            )


def get_latest_medicoes() -> list:
    with _connect() as conn:
        cur = conn.execute(
            """
            SELECT m.ip, m.display_name, m.loja, m.device_type,
                   mc.collected_at, mc.status, mc.payload_json, mc.fetch_error
            FROM medidores m
            JOIN medicoes mc ON mc.medidor_id = m.id
            WHERE mc.id IN (
                SELECT mc2.id FROM medicoes mc2
                WHERE mc2.medidor_id = m.id
                ORDER BY mc2.collected_at DESC
                LIMIT 1
            )
            ORDER BY m.loja, m.ip
            """
        )
        rows = []
        for row in cur.fetchall():
            rows.append({
                "ip": row["ip"],
                "name": row["display_name"],
                "loja": row["loja"],
                "device_type": row["device_type"],
                "collected_at": row["collected_at"],
                "status": row["status"],
                "data": json.loads(row["payload_json"]),
                "fetch_error": row["fetch_error"],
            })
        return rows
