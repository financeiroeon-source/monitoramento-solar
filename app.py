import streamlit as st
import requests
import pandas as pd
import time

# --- CONFIGURAÇÕES ---
# Se sua conta for muito antiga, pode ser 'eu5'. No Brasil geralmente é 'la5'.
BASE_URL = "https://la5.fusionsolar.huawei.com/thirdData"

st.set_page_config(page_title="Monitoramento Huawei", page_icon="☀️", layout="wide")

st.title("☀️ Portal de Monitoramento - Teste Huawei")
st.markdown("Este painel verifica quais clientes estão **OFFLINE** ou com **FALHA**.")

# --- BARRA LATERAL (LOGIN) ---
with st.sidebar:
    st.header("🔐 Acesso API")
    api_user = st.text_input("Usuário da API (Northbound)", value="")
    api_pass = st.text_input("Senha da API", type="password", value="")
    
    btn_carregar = st.button("🔍 Buscar Dados")

# --- FUNÇÕES DO SISTEMA ---
def login_huawei(user, password):
    """Faz login e retorna o Token de acesso"""
    url = f"{BASE_URL}/login"
    payload = {"userName": user, "systemCode": password}
    
    try:
        r = requests.post(url, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if data.get("success", False):
            # O Token vem no cabeçalho da resposta, não no JSON
            return r.headers.get("xsrf-token")
        else:
            st.error(f"Erro no login: {data.get('failCode')} - {data.get('message')}")
            return None
    except Exception as e:
        st.error(f"Erro de conexão: {e}")
        return None

def get_station_list(token):
    """Pega a lista de todas as usinas"""
    url = f"{BASE_URL}/getStationList"
    headers = {"xsrf-token": token}
    # Paginação simplificada (pega as primeiras 100 usinas para teste)
    payload = {"pageNo": 1, "pageSize": 100}
    
    r = requests.post(url, json=payload, headers=headers)
    return r.json()

def get_real_time_kpi(token, station_codes):
    """Pega dados em tempo real (status) das usinas"""
    url = f"{BASE_URL}/getStationRealKpi"
    headers = {"xsrf-token": token}
    payload = {"stationCodes": station_codes}
    
    r = requests.post(url, json=payload, headers=headers)
    return r.json()

# --- LÓGICA PRINCIPAL ---
if btn_carregar:
    if not api_user or not api_pass:
        st.warning("Preencha usuário e senha na barra lateral.")
    else:
        with st.spinner("Conectando aos servidores da Huawei..."):
            token = login_huawei(api_user, api_pass)
            
            if token:
                st.success("Login realizado com sucesso! Baixando lista de clientes...")
                
                # 1. Pegar Lista de Usinas
                data_stations = get_station_list(token)
                if data_stations.get("data") and data_stations["data"]["list"]:
                    stations = data_stations["data"]["list"]
                    
                    # Extrair códigos das estações para consultar status
                    station_codes = ",".join([s["stationCode"] for s in stations])
                    
                    # 2. Pegar Status em Tempo Real
                    data_kpi = get_real_time_kpi(token, station_codes)
                    
                    if data_kpi.get("data") and data_kpi["data"]["list"]:
                        lista_final = []
                        
                        # Cruzar dados (Nome da usina + Status atual)
                        # O status 1=Conectado, 2=Falha, 3=Desconectado
                        map_status = {1: "Normal", 2: "FALHA", 3: "OFFLINE"}
                        
                        for kpi in data_kpi["data"]["list"]:
                            # Achar o nome da usina pelo código
                            nome = next((s["stationName"] for s in stations if s["stationCode"] == kpi["stationCode"]), "Desconhecido")
                            
                            status_code = kpi.get("realHealthState", 3) # Assume offline se não tiver status
                            status_text = map_status.get(status_code, "Desconhecido")
                            
                            lista_final.append({
                                "Cliente": nome,
                                "Status": status_text,
                                "Potência Atual (kW)": kpi.get("day_power", 0), # day_power geralmente é produção do dia
                                "Endereço": next((s["stationAddr"] for s in stations if s["stationCode"] == kpi["stationCode"]), "-")
                            })
                        
                        # Criar DataFrame
                        df = pd.DataFrame(lista_final)
                        
                        # FILTRO: Quem está com problema?
                        df_problema = df[df["Status"].isin(["OFFLINE", "FALHA"])]
                        df_ok = df[df["Status"] == "Normal"]
                        
                        # --- EXIBIÇÃO NA TELA ---
                        col1, col2, col3 = st.columns(3)
                        col1.metric("Total Clientes", len(df))
                        col2.metric("Offline/Falha", len(df_problema))
                        col3.metric("Online", len(df_ok))
                        
                        st.subheader("🚨 Clientes com ALERTA (Offline/Falha)")
                        if not df_problema.empty:
                            st.dataframe(df_problema, use_container_width=True, hide_index=True)
                        else:
                            st.info("Nenhum cliente offline no momento! 🎉")
                            
                        st.subheader("✅ Clientes Normais")
                        with st.expander("Ver lista completa"):
                            st.dataframe(df_ok, use_container_width=True, hide_index=True)
                            
                    else:
                        st.warning("Não foi possível obter os dados de tempo real (KPI).")
                else:
                    st.warning("Nenhuma usina encontrada nesta conta.")
