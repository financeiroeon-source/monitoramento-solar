import streamlit as st
import requests
import pandas as pd
import json

# --- CONFIGURAÇÕES ---
# Mantendo la5 pois conectou com sucesso
BASE_URL = "https://la5.fusionsolar.huawei.com/thirdData"

st.set_page_config(page_title="Monitoramento Eon", page_icon="☀️", layout="wide")

st.title("☀️ Portal de Monitoramento - Eon Solar")

# --- BARRA LATERAL ---
with st.sidebar:
    st.header("🔐 Acesso API")
    api_user = st.text_input("Usuário (Northbound)", value="")
    api_pass = st.text_input("Senha", type="password", value="")
    btn_carregar = st.button("🔍 Buscar Dados")

# --- FUNÇÕES ---
def login_huawei(user, password):
    try:
        r = requests.post(f"{BASE_URL}/login", json={"userName": user, "systemCode": password}, timeout=15)
        r.raise_for_status()
        resp = r.json()
        if resp.get("success", False): 
            return r.headers.get("xsrf-token")
        else:
            st.error(f"Falha no Login: {resp.get('message', 'Erro desconhecido')}")
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
    return None

def get_data(url, token, payload):
    try:
        r = requests.post(url, json=payload, headers={"xsrf-token": token}, timeout=15)
        return r.json()
    except Exception as e:
        st.error(f"Erro ao baixar dados ({url}): {e}")
        return {}

# --- LÓGICA PRINCIPAL ---
if btn_carregar:
    if not api_user or not api_pass:
        st.warning("⚠️ Preencha usuário e senha.")
    else:
        with st.spinner("Conectando ao servidor da Huawei..."):
            token = login_huawei(api_user, api_pass)
            
            if token:
                # 1. Pegar Lista de Estações
                raw_stations = get_data(f"{BASE_URL}/getStationList", token, {"pageNo": 1, "pageSize": 100})
                
                stations = []
                if raw_stations.get("data"):
                    if isinstance(raw_stations["data"], list):
                        stations = raw_stations["data"]
                    elif isinstance(raw_stations["data"], dict):
                        stations = raw_stations["data"].get("list", [])

                if stations:
                    st.toast(f"{len(stations)} usinas encontradas!", icon="✅")
                    
                    # 2. Pegar Dados de Tempo Real (KPI)
                    codes = ",".join([str(s["stationCode"]) for s in stations])
                    raw_kpi = get_data(f"{BASE_URL}/getStationRealKpi", token, {"stationCodes": codes})
                    
                    kpi_list = []
                    data_container = raw_kpi.get("data")
                    
                    if isinstance(data_container, list):
                        kpi_list = data_container
                    elif isinstance(data_container, dict):
                        kpi_list = data_container.get("list", [])

                    # 3. Processar Dados
                    lista_final = []
                    
                    # --- MAPA CORRIGIDO (INVERTIDO) ---
                    # 1 = Offline (Desconectado)
                    # 2 = Falha
                    # 3 = Online (Conectado)
                    map_status = {
                        1: "⚫ OFFLINE", 
                        2: "🔴 FALHA", 
                        3: "🟢 ONLINE"
                    }

                    for item in kpi_list:
                        dados_reais = item.get("dataItemMap", item)
                        s_code = str(item.get("stationCode"))
                        
                        usina_match = next((s for s in stations if str(s["stationCode"]) == s_code), {})
                        nome = usina_match.get("stationName", f"ID {s_code}")
                        
                        # Leitura dos dados
                        state_code = dados_reais.get("realHealthState") or dados_reais.get("real_health_state") or 1
                        power = float(dados_reais.get("day_power") or dados_reais.get("dayPower") or 0.0)
                        
                        # --- INTELIGÊNCIA EXTRA ---
                        # Se tem produção, é ONLINE, não importa o que o status diga.
                        if power > 0.1:
                            status_text = "🟢 ONLINE"
                        else:
                            status_text = map_status.get(int(state_code), "❓ DESCONHECIDO")

                        lista_final.append({
                            "Cliente": nome,
                            "Status": status_text,
                            "Produção Dia (kWh)": power,
                            "Endereço": usina_match.get("stationAddr", "-")
                        })

                    # Criar Tabela
                    df = pd.DataFrame(lista_final)
                    
                    # Filtros de Texto
                    df_offline = df[df["Status"].str.contains("OFFLINE|FALHA|DESCONHECIDO", na=False)]
                    df_online = df[df["Status"].str.contains("ONLINE", na=False)]

                    # Exibir Métricas
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total", len(df))
                    c2.metric("Com Alerta", len(df_offline), delta_color="inverse")
                    c3.metric("Operando", len(df_online))

                    st.divider()

                    if not df_offline.empty:
                        st.error(f"🚨 Atenção: {len(df_offline)} clientes parados.")
                        st.dataframe(df_offline, use_container_width=True, hide_index=True)
                    else:
                        st.success("Tudo limpo! Todos os clientes operando.")

                    st.subheader("Clientes Operando")
                    with st.expander("Ver lista completa"):
                        st.dataframe(df_online, use_container_width=True, hide_index=True)

                else:
                    st.warning("A lista de usinas veio vazia.")
