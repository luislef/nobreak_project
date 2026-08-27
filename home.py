from flask import Flask, jsonify, render_template, request, Response
import requests
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from datetime import datetime
import csv
import io

from database import (
    init_db,
    get_latest_leituras,
    get_latest_medicoes,
    get_nobreak_configs,
    is_special_protocol,
    needs_auth,
    save_eventos_from_results,
    save_leitura,
    save_leituras_batch,
    save_medicoes_batch,
    sync_medidores,
    sync_nobreaks,
    update_nobreak_config,
)
from medidores import MEDIDORES_CONFIG, fetch_all_medidores, fetch_medidor_by_ip

app = Flask(__name__)

# Lista de IPs dos nobreaks
IPS = [
    "192.168.100.168",
    "192.168.101.168",
    "192.168.102.168",
    "192.168.103.168",
    "192.168.104.168",
    "192.168.105.168",
    "192.168.106.168",
    "192.168.107.168",
    "192.168.108.168",
    "192.168.109.168",
    "192.168.110.168",
    "192.168.111.168",
    "192.168.112.168",
    "192.168.113.168",
    "192.168.114.168",
    "192.168.115.168",
    "192.168.116.168",
]

# Defaults iniciais (só usados na 1ª inserção no SQLite).
# Depois disso, protocol/auth ficam editáveis pela engrenagem do painel.
DEFAULT_SPECIAL_IPS = [
    "192.168.105.168",
    "192.168.115.168",
]

# IPs que requerem autenticação (default inicial)
DEFAULT_AUTH_REQUIRED_IPS = [
    "192.168.102.168",
    "192.168.106.168",
    "192.168.110.168",
    "192.168.113.168",
    "192.168.116.168",  # temporariamente modelo antigo com auth
]

# Credenciais de autenticação
USERNAME = 'admin'
PASSWORD = '272345'

# Mapeamento de nomes de meses em português para inglês (usado nas URLs dos logs)
MONTH_MAP = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
    7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'
}

# Mapeamento de códigos de eventos para descrições (nobreaks especiais 115/116)
EVENT_CODE_DESCRIPTIONS = {
    1: "Ligado",
    2: "Desligado",
    3: "Falha na rede elétrica",
    4: "Rede elétrica restabelecida",
    5: "Operando em bateria",
    6: "Bateria fraca",
    7: "Bateria em carga",
    8: "Bateria carregada",
    9: "Sobrecarga",
    10: "Falha na entrada",
    11: "Entrada normalizada",
    12: "Teste de bateria iniciado",
    13: "Teste de bateria finalizado",
    14: "Alarme ativado",
    15: "Alarme desativado",
    32: "Aguardando energia",
    33: "Energia reestabelecida",
}

# Nomes amigáveis para os nobreaks (pode ser personalizado)
NOBREAK_NAMES = {
    "192.168.100.168": "Nobreak 100",
    "192.168.101.168": "Nobreak 101",
    "192.168.102.168": "Nobreak 102",
    "192.168.103.168": "Nobreak 103",
    "192.168.104.168": "Nobreak 104",
    "192.168.105.168": "Nobreak 105",
    "192.168.106.168": "Nobreak 106",
    "192.168.107.168": "Nobreak 107",
    "192.168.108.168": "Nobreak 108",
    "192.168.109.168": "Nobreak 109",
    "192.168.110.168": "Nobreak 110",
    "192.168.111.168": "Nobreak 111",
    "192.168.112.168": "Nobreak 112",
    "192.168.113.168": "Nobreak 113",
    "192.168.114.168": "Nobreak 114",
    "192.168.115.168": "Nobreak 115 (Especial)",
    "192.168.116.168": "Nobreak 116",
}

init_db()
sync_nobreaks(IPS, NOBREAK_NAMES, DEFAULT_AUTH_REQUIRED_IPS, DEFAULT_SPECIAL_IPS)
sync_medidores(MEDIDORES_CONFIG)


def fetch_section(ip, urls, parse_func):
    last_error = None
    for url in urls:
        try:
            return fetch_and_parse(url, parse_func, ip)
        except requests.exceptions.RequestException as exc:
            last_error = exc
            print(f"DEBUG: falha ao acessar {url} para {ip}: {exc}")
    if last_error:
        raise last_error
    return parse_func("")

def fetch_data(ip):
    """
    Busca e combina os dados dos endpoints de um UPS.
    Para os IPs especiais, utiliza uma função específica que busca o JSON.
    """
    try:
        if is_special_protocol(ip):
            # Chama a função especial para o JSON dos dispositivos especiais
            # mas retorna na estrutura padrão
            return fetch_special_data(ip)
        else:
            other_info = fetch_section(ip, [
                f"http://{ip}/ups.cgi?p=otherinfo",
                f"http://{ip}/ddata.html"
            ], extract_other_info)
            input_info = fetch_section(ip, [
                f"http://{ip}/ups.cgi?p=input",
                f"http://{ip}/ddata.html"
            ], extract_input_data)
            output_info = fetch_section(ip, [
                f"http://{ip}/ups.cgi?p=output",
                f"http://{ip}/ddata.html"
            ], extract_output_data)

            return {
                "otherInfo": other_info,
                "inputInfo": input_info,
                "outputInfo": output_info
            }
    except requests.exceptions.RequestException as e:
        print(f"Erro ao buscar dados para {ip}: {e}")
        return get_error_data(e)

def fetch_special_data(ip):
    """
    Busca e processa o JSON dos dispositivos com protocol=special.
    Usa o endpoint /get_dashboard.cgi e organiza os dados no formato padrão.
    """
    url = f"http://{ip}/get_dashboard.cgi"
    print(f"DEBUG: Tentando acessar URL: {url}")
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        print(f"DEBUG: Resposta HTTP status: {response.status_code}")
        print(f"DEBUG: Conteúdo da resposta: {response.text[:200]}...")
        
        # Assume que o dispositivo retorna JSON válido
        data = response.json()
        print(f"DEBUG: JSON parseado: {data}")
        
        # Organiza os dados no formato padrão dos outros nobreaks
        dashboard_data = data.get("Dashboard", {})
    except Exception as e:
        print(f"DEBUG: Erro ao acessar {url}: {e}")
        # Em caso de erro, retorna dados vazios
        dashboard_data = {}
    
    return {
        "otherInfo": {
            "frequencyIn": "N/A",
            "frequencyOut": "N/A",
            "inputVoltage": str(dashboard_data.get("gVolt1", "N/A")),
            "outputVoltage": str(dashboard_data.get("lVolt1", "N/A")),
            "outputPower": str(dashboard_data.get("lWatt", "N/A")),
            "temperature": "N/A",
            "percentualCarga": f"{dashboard_data.get('bWatt', 'N/A')} %",
        },
        "inputInfo": {
            "inputVoltage": str(dashboard_data.get("gVolt1", "N/A")),
            "inputFrequency": "N/A",
            "inputPhase": f"Fase A ({dashboard_data.get('nPhases', 'N/A')} fases)"
        },
        "outputInfo": {
            "Tensão": f"{dashboard_data.get('lVolt1', 'N/A')} V",
            "Frequência": "N/A",
            "Corrente": "N/A",
            "Potência ativa": f"{dashboard_data.get('lWatt', 'N/A')} W",
            "Potência aparente": "N/A",
            "Carga": "N/A",
            "FP da Carga": "N/A"
        }
    }

def fetch_and_parse(url, parse_func, ip):
    if needs_auth(ip):
        response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), timeout=8)
    else:
        response = requests.get(url, timeout=8)
    response.raise_for_status()
    response.encoding = 'utf-8'
    return parse_func(response.text)

def extract_other_info(html):
    """
    Faz o parsing do HTML para extrair informações gerais.
    Extrai dados da estrutura de tabela HTML.
    """
    soup = BeautifulSoup(html, 'html.parser')
    info = {}
    
    try:
        # Procura por todas as linhas da tabela
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                
                # Remove acentos e caracteres especiais para comparação
                label_clean = label.replace('ê', 'e').replace('ã', 'a').replace('ç', 'c').replace('á', 'a')
                
                if "Frequencia de entrada" in label_clean or "Frequência de entrada" in label:
                    info['frequencyIn'] = value
                elif "Frequencia de saida" in label_clean or "Frequência de saída" in label:
                    info['frequencyOut'] = value
                elif "Tensao de entrada" in label_clean or "Tensão de entrada" in label:
                    info['inputVoltage'] = value
                elif "Tensao de saida" in label_clean or "Tensão de saída" in label:
                    info['outputVoltage'] = value
                elif "Potencia ativa" in label_clean or "Potência ativa" in label:
                    info['outputPower'] = value
                elif "Temperatura" in label:
                    info['temperature'] = value
                # Captura do percentual de carga (várias variações possíveis)
                elif "Percentual de carga" in label or "percentual de carga" in label_clean:
                    info['percentualCarga'] = value
                elif "Carga da bateria" in label or "carga da bateria" in label_clean:
                    info['percentualCarga'] = value
                elif "Battery charge" in label_clean:
                    info['percentualCarga'] = value
                # Se for apenas "Carga" com %, pode ser o percentual
                elif label_clean == "Carga" and "%" in value:
                    info['percentualCarga'] = value
    except Exception as e:
        print(f"Erro ao extrair outras informações: {e}")
    
    # Preenche campos faltantes com "N/A"
    info.setdefault('frequencyIn', 'N/A')
    info.setdefault('frequencyOut', 'N/A')
    info.setdefault('inputVoltage', 'N/A')
    info.setdefault('outputVoltage', 'N/A')
    info.setdefault('outputPower', 'N/A')
    info.setdefault('temperature', 'N/A')
    info.setdefault('percentualCarga', '100 %')  # Default para 100% se não encontrar
    
    return info

def extract_output_data(html):
    """
    Faz o parsing do HTML para extrair os dados de saída.
    Extrai dados da estrutura de tabela HTML.
    """
    soup = BeautifulSoup(html, 'html.parser')
    output_info = {}
    
    try:
        # Procura por todas as linhas da tabela
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                
                # Remove acentos e caracteres especiais para comparação
                label_clean = label.replace('ê', 'e').replace('ã', 'a').replace('ç', 'c')
                
                if "Tensao" in label_clean or "Tensão" in label:
                    output_info['Tensão'] = value
                elif "Frequencia" in label_clean or "Frequência" in label:
                    output_info['Frequência'] = value
                elif "Corrente" in label:
                    output_info['Corrente'] = value
                elif "Potencia ativa" in label_clean or "Potência ativa" in label:
                    output_info['Potência ativa'] = value
                elif "Potencia aparente" in label_clean or "Potência aparente" in label:
                    output_info['Potência aparente'] = value
                elif "Carga" in label:
                    output_info['Carga'] = value
                elif "FP da Carga" in label:
                    output_info['FP da Carga'] = value
    except Exception as e:
        print(f"Erro ao extrair dados de saída: {e}")

    # Se nenhum dado foi extraído, preenche com "N/A"
    if not output_info:
        output_info = {
            "Tensão": "N/A",
            "Frequência": "N/A",
            "Corrente": "N/A",
            "Potência ativa": "N/A",
            "Potência aparente": "N/A",
            "Carga": "N/A",
            "FP da Carga": "N/A"
        }
    return output_info

def extract_input_data(html):
    """
    Faz o parsing do HTML para extrair os dados de entrada.
    Extrai dados da estrutura de tabela HTML.
    """
    soup = BeautifulSoup(html, 'html.parser')
    input_info = {"inputVoltage": "N/A", "inputFrequency": "N/A", "inputPhase": "Fase A"}
    
    try:
        # Procura por todas as linhas da tabela
        rows = soup.find_all('tr')
        for row in rows:
            cols = row.find_all('td')
            if len(cols) == 2:
                label = cols[0].get_text(strip=True)
                value = cols[1].get_text(strip=True)
                
                # Remove acentos e caracteres especiais para comparação
                label_clean = label.replace('ê', 'e').replace('ã', 'a').replace('ç', 'c')
                
                if "Tensao" in label_clean or "Tensão" in label:
                    input_info['inputVoltage'] = value
                elif "Frequencia" in label_clean or "Frequência" in label:
                    input_info['inputFrequency'] = value
    except Exception as e:
        print(f"Erro ao extrair dados de entrada: {e}")
    
    return input_info


def extract_ups_config(html):
    """
    Faz o parsing do HTML para extrair as configurações do UPS.
    Extrai dados dos campos de formulário.
    """
    soup = BeautifulSoup(html, 'html.parser')
    config = {}
    
    try:
        # Extrair valor do select de teste de bateria
        test_select = soup.find('select', {'name': 'test'})
        if test_select:
            selected_option = test_select.find('option', selected=True)
            if selected_option:
                config['testeBateria'] = selected_option.get_text(strip=True)
            else:
                config['testeBateria'] = 'N/A'
        
        # Extrair valores dos inputs
        inputs_map = {
            'hora': 'hora',
            'min': 'minuto',
            'seg': 'segundo',
            'day': 'dia',
            'mon': 'mes',
            'yea': 'ano',
            'vout': 'tensaoSaida',
            'freqout': 'frequenciaSaida',
            'under': 'subtensao',
            'over': 'sobretensao',
            'bday': 'bateriaDia',
            'bmon': 'bateriaMes',
            'byea': 'bateriaAno',
            'batlife': 'vidaBateria'
        }
        
        for input_name, config_key in inputs_map.items():
            input_elem = soup.find('input', {'name': input_name})
            if input_elem:
                config[config_key] = input_elem.get('value', 'N/A')
            else:
                config[config_key] = 'N/A'
        
        # Extrair valor do buzzer (radio button)
        buzzer_checked = soup.find('input', {'name': 'buzzer', 'checked': True})
        if buzzer_checked:
            buzzer_value = buzzer_checked.get('value', '')
            config['buzzer'] = 'Ativado' if buzzer_value == '2' else 'Desativado'
        else:
            config['buzzer'] = 'N/A'
            
    except Exception as e:
        print(f"Erro ao extrair configurações do UPS: {e}")
    
    # Preencher campos faltantes com "N/A"
    default_fields = ['testeBateria', 'hora', 'minuto', 'segundo', 'dia', 'mes', 'ano',
                      'tensaoSaida', 'frequenciaSaida', 'buzzer', 'subtensao', 'sobretensao',
                      'bateriaDia', 'bateriaMes', 'bateriaAno', 'vidaBateria']
    for field in default_fields:
        config.setdefault(field, 'N/A')
    
    return config


def fetch_ups_config(ip):
    """
    Busca as configurações do UPS para um IP específico.
    """
    try:
        # Protocolo special não possui essa página de configuração
        if is_special_protocol(ip):
            return {
                'testeBateria': 'N/A (dispositivo especial)',
                'hora': 'N/A', 'minuto': 'N/A', 'segundo': 'N/A',
                'dia': 'N/A', 'mes': 'N/A', 'ano': 'N/A',
                'tensaoSaida': 'N/A', 'frequenciaSaida': 'N/A',
                'buzzer': 'N/A', 'subtensao': 'N/A', 'sobretensao': 'N/A',
                'bateriaDia': 'N/A', 'bateriaMes': 'N/A', 'bateriaAno': 'N/A',
                'vidaBateria': 'N/A'
            }
        
        url = f"http://{ip}/ups.cgi?p=equip"
        if needs_auth(ip):
            response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), timeout=8)
        else:
            response = requests.get(url, timeout=8)
        response.raise_for_status()
        response.encoding = 'utf-8'
        return extract_ups_config(response.text)
    except Exception as e:
        print(f"Erro ao buscar configurações do UPS para {ip}: {e}")
        return {
            'testeBateria': 'Erro', 'hora': 'N/A', 'minuto': 'N/A', 'segundo': 'N/A',
            'dia': 'N/A', 'mes': 'N/A', 'ano': 'N/A',
            'tensaoSaida': 'N/A', 'frequenciaSaida': 'N/A',
            'buzzer': 'N/A', 'subtensao': 'N/A', 'sobretensao': 'N/A',
            'bateriaDia': 'N/A', 'bateriaMes': 'N/A', 'bateriaAno': 'N/A',
            'vidaBateria': 'N/A', 'error': str(e)
        }


def get_error_data(error):
    """
    Retorna um dicionário com informações de erro e valores padrão.
    """
    return {
        "otherInfo": {
            "frequencyIn": "N/A",
            "frequencyOut": "N/A",
            "inputVoltage": "N/A",
            "outputVoltage": "N/A",
            "outputPower": "N/A",
            "temperature": "N/A",
            "percentualCarga": "N/A",
        },
        "inputInfo": {
            "inputVoltage": "N/A",
            "inputFrequency": "N/A",
            "inputPhase": "N/A"
        },
        "outputInfo": {
            "Tensão": "N/A",
            "Frequência": "N/A",
            "Corrente": "N/A",
            "Potência ativa": "N/A",
            "Potência aparente": "N/A",
            "Carga": "N/A",
            "FP da Carga": "N/A"
        },
        "error": str(error)
    }


def fetch_event_log(ip, date_str):
    """
    Busca o log de eventos de um nobreak para uma data específica.
    
    Args:
        ip: IP do nobreak
        date_str: Data no formato 'YYYY-MM-DD'
    
    Returns:
        dict com status, eventos e informações do nobreak
    """
    try:
        # Verifica se é um nobreak especial (CGIs em JSON)
        if is_special_protocol(ip):
            return fetch_special_event_log(ip, date_str)
        
        # Parse da data
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        year = date_obj.year
        month = date_obj.month
        day = date_obj.day
        
        # Monta a URL do arquivo CSV
        # Formato: http://IP/memsd/EVENT/YYYY/Mon/EVENTYYYY-MM-DD.csv
        month_abbr = MONTH_MAP.get(month, 'Jan')
        filename = f"EVENT{year}-{month:02d}-{day:02d}.csv"
        url = f"http://{ip}/memsd/EVENT/{year}/{month_abbr}/{filename}"
        
        print(f"DEBUG: Buscando logs de {ip}: {url}")
        
        # Faz a requisição com ou sem autenticação
        if needs_auth(ip):
            response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD), timeout=10)
        else:
            response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            # Parse do CSV
            events = parse_event_csv(response.text)
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "success",
                "date": date_str,
                "events": events,
                "event_count": len(events)
            }
        elif response.status_code == 404:
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "no_data",
                "date": date_str,
                "events": [],
                "event_count": 0,
                "message": "Nenhum log encontrado para esta data"
            }
        else:
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "error",
                "date": date_str,
                "events": [],
                "event_count": 0,
                "message": f"Erro HTTP {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "timeout",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": "Timeout ao conectar"
        }
    except requests.exceptions.ConnectionError:
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "offline",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": "Nobreak offline ou inacessível"
        }
    except Exception as e:
        print(f"DEBUG: Erro ao buscar log de {ip}: {e}")
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "error",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": str(e)
        }


def fetch_special_event_log(ip, date_str):
    """
    Busca o log de eventos dos nobreaks especiais usando o endpoint /get_eventos.cgi.
    
    Args:
        ip: IP do nobreak
        date_str: Data no formato 'YYYY-MM-DD'
    
    Returns:
        dict com status, eventos e informações do nobreak
    """
    try:
        url = f"http://{ip}/get_eventos.cgi?date={date_str}"
        print(f"DEBUG: Buscando logs especiais de {ip}: {url}")
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            events = []
            
            # Parse do JSON: {"data": [{"code": 4, "date": "08:29:58"}, ...]}
            for event in data.get("data", []):
                code = event.get("code", 0)
                time_str = event.get("date", "")
                description = EVENT_CODE_DESCRIPTIONS.get(code, f"Evento desconhecido (código {code})")
                
                # Monta data/hora completa
                full_datetime = f"{date_str}T{time_str}" if time_str else date_str
                
                events.append({
                    "data_hora": full_datetime,
                    "codigo": str(code),
                    "descricao": description
                })
            
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "success" if events else "no_data",
                "date": date_str,
                "events": events,
                "event_count": len(events),
                "message": "" if events else "Nenhum evento registrado nesta data"
            }
        elif response.status_code == 404:
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "no_data",
                "date": date_str,
                "events": [],
                "event_count": 0,
                "message": "Nenhum log encontrado para esta data"
            }
        else:
            return {
                "ip": ip,
                "name": NOBREAK_NAMES.get(ip, ip),
                "status": "error",
                "date": date_str,
                "events": [],
                "event_count": 0,
                "message": f"Erro HTTP {response.status_code}"
            }
            
    except requests.exceptions.Timeout:
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "timeout",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": "Timeout ao conectar"
        }
    except requests.exceptions.ConnectionError:
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "offline",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": "Nobreak offline ou inacessível"
        }
    except Exception as e:
        print(f"DEBUG: Erro ao buscar log especial de {ip}: {e}")
        return {
            "ip": ip,
            "name": NOBREAK_NAMES.get(ip, ip),
            "status": "error",
            "date": date_str,
            "events": [],
            "event_count": 0,
            "message": str(e)
        }


def parse_event_csv(csv_text):
    """
    Faz o parse do conteúdo CSV de eventos.
    
    Args:
        csv_text: Conteúdo do arquivo CSV como string
    
    Returns:
        Lista de dicionários com os eventos
    """
    events = []
    try:
        # Usa StringIO para tratar a string como arquivo
        csv_file = io.StringIO(csv_text)
        reader = csv.reader(csv_file)
        
        # Pula o cabeçalho
        header = next(reader, None)
        
        for row in reader:
            if len(row) >= 3:
                events.append({
                    "data_hora": row[0],
                    "codigo": row[1],
                    "descricao": row[2] if len(row) > 2 else ""
                })
    except Exception as e:
        print(f"DEBUG: Erro ao fazer parse do CSV: {e}")
    
    return events


def fetch_all_event_logs(date_str, ips=None):
    """
    Busca logs de eventos de todos os nobreaks simultaneamente.
    
    Args:
        date_str: Data no formato 'YYYY-MM-DD'
        ips: Lista de IPs para buscar (opcional, usa todos se None)
    
    Returns:
        Lista de resultados de cada nobreak
    """
    if ips is None:
        # Agora inclui TODOS os IPs, pois os especiais têm tratamento próprio
        ips = IPS
    
    results = []
    with ThreadPoolExecutor(max_workers=len(ips)) as executor:
        future_to_ip = {executor.submit(fetch_event_log, ip, date_str): ip for ip in ips}
        for future in as_completed(future_to_ip):
            result = future.result()
            results.append(result)
    
    # Ordena por IP para manter consistência
    results.sort(key=lambda x: x['ip'])
    return results


def generate_consolidated_report(results, date_str):
    """
    Gera um relatório consolidado em formato CSV com todos os eventos.
    
    Args:
        results: Lista de resultados de cada nobreak
        date_str: Data do relatório
    
    Returns:
        String com o conteúdo CSV do relatório
    """
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Cabeçalho
    writer.writerow(['Nobreak', 'IP', 'Data/Hora', 'Código do Evento', 'Descrição do Evento'])
    
    # Dados de cada nobreak
    for result in results:
        if result['status'] == 'success' and result['events']:
            for event in result['events']:
                writer.writerow([
                    result['name'],
                    result['ip'],
                    event['data_hora'],
                    event['codigo'],
                    event['descricao']
                ])
    
    return output.getvalue()


@app.route('/')
def home():
    """
    Renderiza a página inicial.
    """
    return render_template('index.html')

@app.route('/details/<ip>')
def details(ip):
    """
    Renderiza a página de detalhes para um IP específico.
    """
    data = fetch_data(ip)
    config = fetch_ups_config(ip)
    try:
        save_leitura(ip, data)
    except Exception as exc:
        print(f"Aviso: falha ao gravar leitura no SQLite ({ip}): {exc}")
    return render_template('details.html', ip=ip, data=data, config=config)

@app.route('/dashboard-data')
def get_dashboard_data():
    """
    Busca os dados de todos os UPS e os retorna como JSON.
    """
    with ThreadPoolExecutor(max_workers=len(IPS)) as executor:
        results = list(executor.map(fetch_data, IPS))
    
    data = {}
    for ip, result in zip(IPS, results):
        data[ip] = result

    try:
        save_leituras_batch(data)
    except Exception as exc:
        print(f"Aviso: falha ao gravar leituras no SQLite: {exc}")

    return jsonify(data)


@app.route('/api/nobreak-config', methods=['GET'])
def api_nobreak_config_list():
    """Lista protocolo e autenticação de cada nobreak."""
    try:
        return jsonify(get_nobreak_configs())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/api/nobreak-config/<ip>', methods=['PUT', 'POST'])
def api_nobreak_config_update(ip):
    """
    Atualiza protocol ('legacy'|'special') e/ou auth_required de um nobreak.
    Body JSON: {"protocol": "legacy", "auth_required": true}
    """
    body = request.get_json(silent=True) or {}
    protocol = body.get("protocol")
    auth_required = body.get("auth_required")
    if protocol is None and auth_required is None:
        return jsonify({"error": "Informe protocol e/ou auth_required"}), 400
    try:
        updated = update_nobreak_config(ip, protocol=protocol, auth_required=auth_required)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500
    if updated is None:
        return jsonify({"error": "Nobreak não encontrado"}), 404
    return jsonify(updated)


@app.route('/api/leituras-recentes')
def api_leituras_recentes():
    """
    Retorna a última leitura gravada no SQLite por nobreak.
    """
    try:
        return jsonify(get_latest_leituras())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/medidores')
def medidores_page():
    """Dashboard dos medidores de energia das lojas."""
    return render_template('medidores.html')


@app.route('/medidores-data')
def medidores_data():
    """Coleta medições de todos os medidores e grava no SQLite."""
    data = fetch_all_medidores()
    try:
        save_medicoes_batch(data)
    except Exception as exc:
        print(f"Aviso: falha ao gravar medições no SQLite: {exc}")
    return jsonify(data)


@app.route('/medidores/<ip>')
def medidor_detail(ip):
    """Detalhes de um medidor específico."""
    data = fetch_medidor_by_ip(ip)
    try:
        save_medicoes_batch({ip: data})
    except Exception as exc:
        print(f"Aviso: falha ao gravar medição no SQLite ({ip}): {exc}")
    return render_template('medidor_detail.html', ip=ip, data=data)


@app.route('/api/medicoes-recentes')
def api_medicoes_recentes():
    """Última medição gravada no SQLite por medidor."""
    try:
        return jsonify(get_latest_medicoes())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route('/logs')
def logs_page():
    """
    Renderiza a página de logs de eventos.
    """
    today = datetime.now().strftime('%Y-%m-%d')
    return render_template('logs.html', today=today, nobreaks=NOBREAK_NAMES)


@app.route('/fetch-logs')
def fetch_logs():
    """
    Busca logs de eventos de todos os nobreaks para uma data específica.
    Query params:
        - date: Data no formato 'YYYY-MM-DD' (default: hoje)
    """
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    # Valida o formato da data
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400
    
    # Busca logs de todos os nobreaks
    results = fetch_all_event_logs(date_str)

    try:
        save_eventos_from_results(results, date_str)
    except Exception as exc:
        print(f"Aviso: falha ao gravar eventos no SQLite: {exc}")
    
    # Estatísticas
    total_events = sum(r['event_count'] for r in results)
    success_count = sum(1 for r in results if r['status'] == 'success')
    no_data_count = sum(1 for r in results if r['status'] == 'no_data')
    error_count = sum(1 for r in results if r['status'] in ['error', 'timeout', 'offline'])
    
    return jsonify({
        "date": date_str,
        "results": results,
        "summary": {
            "total_nobreaks": len(results),
            "with_data": success_count,
            "no_data": no_data_count,
            "errors": error_count,
            "total_events": total_events
        }
    })


@app.route('/download-report')
def download_report():
    """
    Gera e baixa um relatório consolidado de eventos em CSV.
    Query params:
        - date: Data no formato 'YYYY-MM-DD' (default: hoje)
    """
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))
    
    # Valida o formato da data
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Formato de data inválido. Use YYYY-MM-DD"}), 400
    
    # Busca logs de todos os nobreaks
    results = fetch_all_event_logs(date_str)
    
    # Gera o relatório CSV
    csv_content = generate_consolidated_report(results, date_str)
    
    # Retorna como download
    filename = f"relatorio_eventos_{date_str}.csv"
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename={filename}',
            'Content-Type': 'text/csv; charset=utf-8'
        }
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5500, debug=True)
