# Credenciais do projeto nobreak_project

Arquivo de referência com usuários, senhas e quais dispositivos exigem autenticação.

---

## Nobreaks (UPS)

| Campo | Valor |
|-------|-------|
| Usuário | `admin` |
| Senha | `272345` |

Usadas em Basic Auth quando o nobreak está marcado com `auth_required = true`.

### Quais nobreaks usam autenticação

| IP | Nome | Auth | Protocolo |
|----|------|------|-----------|
| 192.168.100.168 | Nobreak 100 | não | legacy (HTML) |
| 192.168.101.168 | Nobreak 101 | não | legacy (HTML) |
| 192.168.102.168 | Nobreak 102 | **sim** | legacy (HTML) |
| 192.168.103.168 | Nobreak 103 | não | legacy (HTML) |
| 192.168.104.168 | Nobreak 104 | não | legacy (HTML) |
| 192.168.105.168 | Nobreak 105 | não | special (JSON) |
| 192.168.106.168 | Nobreak 106 | **sim** | legacy (HTML) |
| 192.168.107.168 | Nobreak 107 | não | legacy (HTML) |
| 192.168.108.168 | Nobreak 108 | não | legacy (HTML) |
| 192.168.109.168 | Nobreak 109 | não | legacy (HTML) |
| 192.168.110.168 | Nobreak 110 | **sim** | legacy (HTML) |
| 192.168.111.168 | Nobreak 111 | não | legacy (HTML) |
| 192.168.112.168 | Nobreak 112 | não | legacy (HTML) |
| 192.168.113.168 | Nobreak 113 | **sim** | legacy (HTML) |
| 192.168.114.168 | Nobreak 114 | não | legacy (HTML) |
| 192.168.115.168 | Nobreak 115 (Especial) | não | special (JSON) |
| 192.168.116.168 | Nobreak 116 | **sim** | legacy (HTML) |

> Protocolo e auth podem ser alterados pela engrenagem ⚙ do painel (`/`).

### Endpoints por protocolo

- **legacy (HTML):** `/ups.cgi?p=otherinfo|input|output|equip`, fallback `/ddata.html`
- **special (JSON):** `/get_dashboard.cgi`, logs em `/get_eventos.cgi?date=YYYY-MM-DD`

---

## Medidores de energia

| Campo | Valor |
|-------|-------|
| Usuário | `admin` |
| Senha | `admin` |

| IP | Nome | Loja | Tipo | Auth | API |
|----|------|------|------|------|-----|
| 192.168.100.169 | Medidor Loja 100 | 100 | ie_tecnologia | **sim** | `/sistema/tecnicavalores` |
| 192.168.105.169 | Medidor Loja 105 | 105 | mienergy | não | `/Data` |
| 192.168.113.169 | Medidor Loja 113 | 113 | mienergy | **sim** | `/Data` |
| 192.168.114.169 | Medidor Loja 114 | 114 | mienergy | não | `/Data` |
| 192.168.115.169 | Medidor Loja 115 | 115 | mienergy | **sim** | `/Data` |

---

## Onde estão no código

| Uso | Arquivo | Constantes |
|-----|---------|------------|
| Nobreaks | `home.py` | `USERNAME`, `PASSWORD` |
| Medidores | `medidores.py` | `METER_USER`, `METER_PASSWORD` |
| Flags por IP | SQLite (`nobreaks.db`) | colunas `auth_required`, `protocol` |

Banco local (não versionado): `F:\nobreak_project_data\nobreaks.db` (via `NOBREAK_DB_PATH`).

---

## App web

| Item | Valor |
|------|-------|
| Host | `0.0.0.0` |
| Porta | `5500` |
| URLs | http://127.0.0.1:5500 · http://192.168.100.200:5500 |
