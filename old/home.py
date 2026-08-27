from flask import Flask, jsonify, render_template, request
import requests
from requests.auth import HTTPBasicAuth
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup

app = Flask(__name__)

# List of IP addresses for UPS devices
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
]

# IPs requiring authentication
AUTH_REQUIRED_IPS = [
    "192.168.102.168", "192.168.106.168", "192.168.110.168", "192.168.113.168" 
]

# Authentication credentials
USERNAME = 'admin'
PASSWORD = '272345'

def fetch_data(ip):
    """
    Fetches and combines data from UPS endpoints for a given IP.
    """
    try:
        # Fetch and parse data from relevant endpoints
        other_info = fetch_and_parse(f"http://{ip}/ups.cgi?p=otherinfo", extract_other_info, ip)
        input_info = fetch_and_parse(f"http://{ip}/ups.cgi?p=input", extract_input_data, ip)
        output_info = fetch_and_parse(f"http://{ip}/ups.cgi?p=output", extract_output_data, ip)

        # Combine fetched data into a single dictionary
        combined_data = {
            "otherInfo": other_info,
            "inputInfo": input_info,
            "outputInfo": output_info
        }
        return ip, combined_data
    except requests.exceptions.RequestException as e:
        # Handle any request exceptions gracefully
        return ip, get_error_data(e)

def fetch_and_parse(url, parse_func, ip):
    """
    Fetches data from a given URL and parses it using the provided parsing function.
    """
    # Check if authentication is required for the IP
    if ip in AUTH_REQUIRED_IPS:
        response = requests.get(url, auth=HTTPBasicAuth(USERNAME, PASSWORD))
    else:
        response = requests.get(url)

    # Raise an error if the request was not successful
    response.raise_for_status()
    response.encoding = 'utf-8'
    
    # Parse the response text using the provided function
    return parse_func(response.text)

def extract_other_info(html):
    """
    Parses the HTML to extract other general information.
    """
    soup = BeautifulSoup(html, 'html.parser')
    info = {}
    # Implement your specific parsing logic here for 'otherInfo'
    return info

def extract_input_data(html):
    """
    Parses the HTML to extract input data.
    """
    soup = BeautifulSoup(html, 'html.parser')
    try:
        input_voltage = soup.find(string="Tensão").findNext('td').text.strip()
        input_frequency = soup.find(string="Frequência").findNext('td').text.strip()
        input_phase = "Fase A"
    except AttributeError:
        input_voltage = input_frequency = input_phase = "N/A"
    return {
        "inputVoltage": input_voltage,
        "inputFrequency": input_frequency,
        "inputPhase": input_phase
    }

def extract_output_data(html):
    """
    Parses the HTML to extract output information.
    """
    soup = BeautifulSoup(html, 'html.parser')
    output_info = {}
    try:
        output_section = soup.find('div', id='ddata')
        if output_section:
            rows = output_section.find_all('tr')
            for row in rows:
                cols = row.find_all('td')
                if len(cols) == 2:
                    label = cols[0].text.strip()
                    value = cols[1].text.strip()
                    # Map labels to keys in the output dictionary
                    if "Tensão" in label:
                        output_info['Tensão'] = value
                    elif "Frequência" in label:
                        output_info['Frequência'] = value
                    elif "Corrente" in label:
                        output_info['Corrente'] = value
                    elif "Potência ativa" in label:
                        output_info['Potência ativa'] = value
                    elif "Potência aparente" in label:
                        output_info['Potência aparente'] = value
                    elif "Carga" in label:
                        output_info['Carga'] = value
                    elif "FP da Carga" in label:
                        output_info['FP da Carga'] = value
    except AttributeError:
        # Handle parsing issues by returning empty data
        pass
    return output_info

def get_error_data(error):
    """
    Returns a dictionary with error information and default values for missing data.
    """
    return {
        "otherInfo": {
            "frequencyIn": "N/A",
            "frequencyOut": "N/A",
            "inputVoltage": "N/A",
            "outputVoltage": "N/A",
            "outputPower": "N/A",
            "temperature": "N/A",
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

@app.route('/')
def home():
    """
    Renders the home page.
    """
    return render_template('index.html')

@app.route('/details/<ip>')
def details(ip):
    """
    Renders the details page for a specific IP address.
    """
    _, data = fetch_data(ip)
    return render_template('details.html', ip=ip, data=data)

@app.route('/dashboard-data')
def get_dashboard_data():
    """
    Fetches data for all IPS and returns it as JSON.
    """
    with ThreadPoolExecutor(max_workers=len(IPS)) as executor:
        results = list(executor.map(fetch_data, IPS))
    return jsonify(dict(results))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
