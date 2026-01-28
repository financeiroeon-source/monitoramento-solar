import streamlit as st
import requests
import pandas as pd
import json
import hashlib
import hmac
import base64
from datetime import datetime, timezone
from email.utils import formatdate

# --- CREDENCIAIS (FIXAS PARA TESTE) ---
# CUIDADO: Não compartilhe esse arquivo publicamente!
CREDS = {
    "huawei": {
        "user": "Eon.solar",
        "pass": "eonsolar2024",
        "url": "https://la5.fusionsolar.huawei.com/thirdData"
    },
    "solis": {
        "key_id": "1300386381676798170",
        "key_secret": "70b315e18b914435abe726846e950eab",
        "url": "https://www.soliscloud.com:13333"
    }
}

st.set_page_config(page_title="Monitoramento Eon", page_icon="☀️", layout="wide")
st.title("☀️ Portal Unificado - Eon Solar (Huawei + Solis)")

# --- FUNÇÕES HUAWEI (Mantendo o que já funcionava) ---
def get_huawei_data():
    try:
        # 1. Login
        s = requests.Session()
        url_login = f"{CREDS['huawei']['url']}/login"
        payload = {"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}
        r = s.post(url_login, json=payload, timeout=10)
        r.raise_for_status()
        token = r.headers.get("xsrf-token")
        
        if not token: return []

        # 2. Lista de Estações
        headers = {"xsrf-token": token}
        r_list = s.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers=headers, timeout=10)
        data_list = r_list.json().get("data", [])
        
        # Tratamento para lista/dict
        stations = []
        if isinstance(data_list, list): stations = data_list
        elif isinstance(data_list, dict): stations = data_list.get("list", [])
        
        if not stations: return []

        # 3. Status Real (KPI)
        codes = ",".join([str(s["stationCode"]) for s in stations])
        r_kpi = s.post(f"{CREDS['huawei']['url']}/getStationRealKpi", json={"stationCodes": codes}, headers=headers, timeout=10)
        
        kpi_raw = r_kpi.json().get("data", [])
        kpi_list = []
        if isinstance(kpi_raw, list): kpi_list = kpi_raw
        elif isinstance(kpi_raw, dict): kpi_list = kpi_raw.get("list", [])

        # 4. Processamento
        results = []
        map_status = {1: "OFFLINE", 2: "FALHA", 3: "ONLINE"} # Invertido conforme ajuste anterior

        for kpi in kpi_list:
            dados = kpi.get("dataItemMap", kpi)
            s_code = str(kpi.get("stationCode"))
            usina = next((s for s in stations if str(s["stationCode"]) == s_code), {})
            
            power = float(dados.get("day_power") or dados.get("dayPower") or 0.0)
            state = dados.get("realHealthState") or dados.get("real_health_state") or 1
            
            # Lógica de Inteligência: Se tem produção, é ONLINE
            status = "🟢 ONLINE" if power > 0.05 else map_status.get(int(state), "❓ DESCONHECIDO")
            if "OFFLINE" in status or "FALHA" in status: status = "🔴 " + status.replace("🔴 ", "")

            results.append({
                "Marca": "Huawei",
                "Cliente": usina.get("stationName", f"ID {s_code}"),
                "Status": status,
                "Produção Hoje (kWh)": power,
                "Endereço": usina.get("stationAddr", "-")
            })
        return results
    except Exception as e:
        st.error(f"Erro Huawei: {e}")
        return []

# --- FUNÇÕES SOLIS (A parte nova e chata de criptografia) ---
def get_solis_headers(body, resource):
    # Solis exige autenticação HMAC-SHA1
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    content_md5 = base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')
    content_type = "application/json"
    
    string_to_sign = f"POST\n{content_md5}\n{content_type}\n{now}\n{resource}"
    
    signature = hmac.new(
        CREDS['solis']['key_secret'].encode('utf-8'),
        string_to_sign.encode('utf-8'),
        hashlib.sha1
    ).digest()
    auth_sign = base64.b64encode(signature).decode('utf-8')
    
    return {
        "Authorization": f"API {CREDS['solis']['key_id']}:{auth_sign}",
        "Content-MD5": content_md5,
        "Content-Type": content_type,
        "Date": now
    }

def get_solis_data():
    try:
        resource = "/v1/api/userStationList"
        url = f"{CREDS['solis']['url']}{resource}"
        
        # Payload padrão para listar usinas
        body_json = json.dumps({"pageNo": 1, "pageSize": 100})
        headers = get_solis_headers(body_json, resource)
        
        r = requests.post(url, data=body_json, headers=headers, timeout=15)
        
        if r.status_code != 200:
            st.error(f"Erro Solis HTTP {r.status_code}: {r.text}")
            return []
            
        data = r.json()
        if data.get("code") != "0":
            st.error(f"Erro API Solis: {data.get('msg')}")
            return []
            
        stations = data.get("data", {}).get("page", {}).get("records", [])
        results = []
        
        for s in stations:
            # Solis Status: 1=Generating, 2=Offline, 3=Fault
            state_raw = s.get("state", 2)
            power_today = float(s.get("dayEnergy", 0))
            
            # Lógica unificada
            if state_raw == 1 or power_today > 0.05:
                status = "🟢 ONLINE"
            elif state_raw == 3:
