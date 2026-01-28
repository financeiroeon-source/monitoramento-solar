import streamlit as st
import requests
import pandas as pd
import json
import hashlib
import hmac
import base64
from datetime import datetime, timezone

# --- CREDENCIAIS ---
# ATENÇÃO: Contém senhas reais. Não compartilhe este arquivo.
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
st.title("☀️ Portal Unificado - Eon Solar")

# --- FUNÇÃO HUAWEI ---
def get_huawei_data():
    try:
        # 1. Login
        s = requests.Session()
        url_login = f"{CREDS['huawei']['url']}/login"
        payload = {"userName": CREDS['huawei']['user'], "systemCode": CREDS['huawei']['pass']}
        r = s.post(url_login, json=payload, timeout=15)
        
        token = ""
        if r.status_code == 200 and r.json().get("success"):
            token = r.headers.get("xsrf-token")
        
        if not token: 
            return []

        # 2. Lista de Estações
        headers = {"xsrf-token": token}
        r_list = s.post(f"{CREDS['huawei']['url']}/getStationList", json={"pageNo": 1, "pageSize": 100}, headers=headers, timeout=15)
        
        stations = []
        raw_data = r_list.json().get("data")
        if isinstance(raw_data, list): stations = raw_data
        elif isinstance(raw_data, dict): stations = raw_data.get("list", [])
        
        if not stations: return []

        # 3. Status Real (KPI)
        codes = ",".join([str(s["stationCode"]) for s in stations])
        r_kpi = s.post(f"{CREDS['huawei']['url']}/getStationRealKpi", json={"stationCodes": codes}, headers=headers, timeout=15)
        
        kpi_list = []
        kpi_raw = r_kpi.json().get("data")
        if isinstance(kpi_raw, list): kpi_list = kpi_raw
        elif isinstance(kpi_raw, dict): kpi_list = kpi_raw.get("list", [])

        # 4. Processamento
        results = []
        # Mapa Huawei Invertido: 1=Offline/Falha, 3=Online
        map_status = {1: "⚫ OFFLINE", 2: "🔴 FALHA", 3: "🟢 ONLINE"}

        for kpi in kpi_list:
            dados = kpi.get("dataItemMap", kpi)
            s_code = str(kpi.get("stationCode"))
            usina = next((s for s in stations if str(s["stationCode"]) == s_code), {})
            
            power = float(dados.get("day_power") or dados.get("dayPower") or 0.0)
            state = dados.get("realHealthState") or dados.get("real_health_state") or 1
            
            # Regra de Ouro: Se tem produção, é ONLINE
            if power > 0.05:
                status = "🟢 ONLINE"
            else:
                status = map_status.get(int(state), "❓ DESCONHECIDO")

            results.append({
                "Marca": "Huawei",
                "Cliente": usina.get("stationName", f"ID {s_code}"),
                "Status": status,
                "Produção (kWh)": power,
                "Endereço": usina.get("stationAddr", "-")
            })
        return results
    except Exception as e:
        st.error(f"Erro Huawei: {e}")
        return []

# --- FUNÇÃO SOLIS ---
def get_solis_data():
    try:
        # Autenticação HMAC-SHA1
        resource = "/v1/api/userStationList"
        body = json.dumps({"pageNo": 1, "pageSize": 100})
        
        now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        content_md5 = base64.b64encode(hashlib.md5(body.encode('utf-8')).digest()).decode('utf-8')
        
        sign_str = f"POST\n{content_md5}\napplication/json\n{now}\n{resource}"
        signature = hmac.new(
            CREDS['solis']['key_secret'].encode('utf-8'),
            sign_str.encode('utf-8'),
