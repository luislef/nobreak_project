"""
Coleta de medições dos medidores de energia (IE Tecnologia e MiEnergy).
"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import requests
from requests.auth import HTTPBasicAuth

METER_USER = "admin"
METER_PASSWORD = "admin"

MEDIDORES_CONFIG: List[Dict[str, Any]] = [
    {
        "ip": "192.168.100.169",
        "display_name": "Medidor Loja 100",
        "loja": "100",
        "device_type": "ie_tecnologia",
        "api_path": "/sistema/tecnicavalores",
        "page_path": "/tec.html",
        "auth_required": True,
    },
    {
        "ip": "192.168.105.169",
        "display_name": "Medidor Loja 105",
        "loja": "105",
        "device_type": "mienergy",
        "api_path": "/Data",
        "page_path": "/medicoes",
        "auth_required": False,
    },
    {
        "ip": "192.168.113.169",
        "display_name": "Medidor Loja 113",
        "loja": "113",
        "device_type": "mienergy",
        "api_path": "/Data",
        "page_path": "/medicoes",
        "auth_required": True,
    },
    {
        "ip": "192.168.114.169",
        "display_name": "Medidor Loja 114",
        "loja": "114",
        "device_type": "mienergy",
        "api_path": "/Data",
        "page_path": "/medicoes",
        "auth_required": False,
    },
    {
        "ip": "192.168.115.169",
        "display_name": "Medidor Loja 115",
        "loja": "115",
        "device_type": "mienergy",
        "api_path": "/Data",
        "page_path": "/medicoes",
        "auth_required": True,
    },
]


def _config_by_ip(ip: str) -> Optional[Dict[str, Any]]:
    for cfg in MEDIDORES_CONFIG:
        if cfg["ip"] == ip:
            return cfg
    return None


def parse_ie_tecnologia(text: str) -> Dict[str, str]:
    leituras: Dict[str, str] = {}
    for line in text.strip().splitlines():
        parts = line.split("|")
        if len(parts) >= 2:
            leituras[parts[0].strip()] = parts[1].strip()
    return leituras


def _http_get(url: str, auth_required: bool, timeout: int = 8) -> requests.Response:
    kwargs: Dict[str, Any] = {"timeout": timeout}
    if auth_required:
        kwargs["auth"] = HTTPBasicAuth(METER_USER, METER_PASSWORD)
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response


def fetch_medidor(cfg: Dict[str, Any]) -> Dict[str, Any]:
    ip = cfg["ip"]
    base = {
        "ip": ip,
        "name": cfg["display_name"],
        "loja": cfg["loja"],
        "device_type": cfg["device_type"],
        "page_url": f"http://{ip}{cfg['page_path']}",
        "status": "online",
        "leituras": {},
        "summary": {},
    }
    url = f"http://{ip}{cfg['api_path']}"

    try:
        response = _http_get(url, cfg["auth_required"])
        if cfg["device_type"] == "ie_tecnologia":
            leituras = parse_ie_tecnologia(response.text)
        else:
            leituras = response.json()

        base["leituras"] = leituras
        base["summary"] = build_summary(cfg["device_type"], leituras)
        return base

    except requests.exceptions.Timeout:
        base["status"] = "timeout"
        base["error"] = "Timeout ao conectar"
    except requests.exceptions.ConnectionError:
        base["status"] = "offline"
        base["error"] = "Medidor offline ou inacessível"
    except requests.exceptions.HTTPError as exc:
        base["status"] = "error"
        base["error"] = f"HTTP {exc.response.status_code if exc.response else 'erro'}"
    except (json.JSONDecodeError, ValueError) as exc:
        base["status"] = "error"
        base["error"] = f"Resposta inválida: {exc}"
    except requests.exceptions.RequestException as exc:
        base["status"] = "error"
        base["error"] = str(exc)

    base["summary"] = build_summary(cfg["device_type"], {})
    return base


def build_summary(device_type: str, leituras: Dict[str, str]) -> Dict[str, str]:
    if device_type == "ie_tecnologia":
        return {
            "tensao_a": leituras.get("x_uarms", "N/A"),
            "potencia_total": leituras.get("x_pt", "N/A"),
            "energia_consumo": leituras.get("x_ept_c", "N/A"),
            "frequencia": leituras.get("x_freq", "N/A"),
            "temperatura": leituras.get("x_TPSD", "N/A"),
        }
    return {
        "tensao_a": leituras.get("v_a", "N/A"),
        "tensao_b": leituras.get("v_b", "N/A"),
        "tensao_c": leituras.get("v_c", "N/A"),
        "potencia_total": leituras.get("p_total", "N/A"),
        "energia_consumo": leituras.get("energia_ativa_total", "N/A"),
        "frequencia": leituras.get("frequencia", "N/A"),
    }


def fetch_all_medidores() -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(MEDIDORES_CONFIG)) as executor:
        futures = {executor.submit(fetch_medidor, cfg): cfg["ip"] for cfg in MEDIDORES_CONFIG}
        for future in as_completed(futures):
            data = future.result()
            results[data["ip"]] = data
    return results


def fetch_medidor_by_ip(ip: str) -> Dict[str, Any]:
    cfg = _config_by_ip(ip)
    if not cfg:
        return {"ip": ip, "status": "error", "error": "Medidor não configurado", "leituras": {}}
    return fetch_medidor(cfg)
