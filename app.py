import streamlit as st
import requests
import pandas as pd
import time

# --- CONFIGURAÇÕES ---
# Servidor da América Latina (Padrão Brasil)
BASE_URL = "https://la5.fusionsolar.huawei.com/thirdData"

st.set_page_config(page_title="Monitoramento Huawei", page_icon="☀️", layout="wide")

st.title("☀️ Portal de Monitoramento - Teste Huawei")
st.markdown("Este painel verifica quais clientes estão **OFFLINE** ou com **FALHA**.")

# --- BARRA LATERAL (LOGIN) ---
with st.sidebar:
    st.header("🔐 Acesso API")
    st.info("Use o usuário e senha criados no menu 'Northbound Management' da Huawei.")
    api_user = st.text_input("Usuário da API", value="")
    api_pass = st.text_input("Senha da API", type="password", value="")
    
    btn_carregar = st.button("🔍 Buscar Dados")

# --- FUNÇÕES DO SISTEMA ---
def login_huawei(user, password):
    """Faz login e retorna o Token de acesso"""
    url = f"{BASE_URL}/login"
    payload = {"userName": user, "systemCode": password}
    
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        
        if data.get("success", False):
            return r.headers.get("xsrf-token")
        else:
            st.error(f"Erro no login: {data.get('failCode')} - {data.get('message')}")
            return None
    except Exception as e:
        st.error(f"Erro de conexão ao tentar logar: {e}")
        return None

def get_station_list(token):
    """Pega a lista de todas as usinas"""
    url = f"{BASE_URL}/getStationList"
    headers = {"xsrf-token": token}
    # Pega as primeiras 100 usinas
    payload = {"pageNo": 1, "pageSize": 100}
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        st.error(f"Erro ao baixar lista de usinas: {e}")
        return {}

def get_real_time_kpi(token, station_codes):
    """Pega dados em tempo real (status) das usinas"""
    url = f"{BASE_URL}/getStationRealKpi"
    headers = {"xsrf-token": token}
    payload = {"stationCodes": station_codes}
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=15)
        return r.json()
    except Exception as e:
        st.error(f"Erro ao baixar dados de tempo real: {e}")
        return {}

# --- LÓGICA PRINCIPAL ---
if btn_carregar:
    if not api_user or not api_pass:
        st.warning("⚠️ Preencha usuário e senha na barra lateral antes de buscar.")
    else:
        with st.spinner("Conectando aos servidores da Huawei..."):
            # 1. TENTAR LOGIN
            token = login_huawei(api_user, api_pass)
            
            if token:
                st.toast("Login realizado! Baixando usinas...", icon="✅")
                
                # 2. PEGAR LISTA DE USINAS
                data_stations = get_station_list(token)
                
                # Verificação robusta se a lista veio
                stations = []
                raw_stations = data_stations.get("data")
                
                if isinstance(raw_stations, list):
                    stations = raw_stations
                elif isinstance(raw_stations, dict) and "list" in raw_stations:
                    stations = raw_stations["list"]
                
                if stations:
                    # Extrair códigos das estações
                    station_codes = ",".join([str(s.get("stationCode")) for s in stations])
                    
                    # 3. PEGAR STATUS EM TEMPO REAL
                    data_kpi = get_real_time_kpi(token, station_codes)
                    
                    # --- CORREÇÃO DO ERRO ANTERIOR ---
                    # O sistema agora verifica se veio como lista direta ou dicionário
                    lista_dados = []
                    raw_kpi = data_kpi.get("data")
                    
                    if isinstance(raw_kpi, list):
                        lista_dados = raw_kpi
                    elif isinstance(raw_kpi, dict) and "list" in raw_kpi:
                        lista_dados = raw_kpi["list"]
                    
                    if lista_dados:
                        lista_final = []
                        
                        # Mapeamento de Status Huawei: 1=Normal, 2=Falha, 3=Desconectado
                        map_status = {1: "Normal", 2: "FALHA", 3: "OFFLINE"}
                        
                        for kpi in lista_dados:
                            s_code = kpi.get("stationCode")
                            
                            # Tenta achar o nome da usina na lista anterior
                            usina_info = next((s for s in stations if str(s.get("stationCode")) == str(s_code)), {})
                            nome = usina_info.get("stationName", f"Usina {s_code}")
                            endereco = usina_info.get("stationAddr", "-")
                            
                            status_code = kpi.get("realHealthState", 3)
                            status_text = map_status.get(status_code, "Desconhecido")
                            
                            lista_final.append({
                                "Cliente": nome,
                                "Status": status_text,
                                "Potência (kW)": kpi.get("day_power", 0),
                                "Endereço": endereco
                            })
                        
                        # Criar Tabela (DataFrame)
                        df = pd.DataFrame(lista_final)
                        
                        # Separar problemas
                        df_problema = df[df["Status"].isin(["OFFLINE", "FALHA"])]
                        df_ok = df[df["Status"] == "Normal"]
                        
                        # --- EXIBIÇÃO ---
                        kpi1, kpi2, kpi3 = st.columns(3)
                        kpi1.metric("Total Monitorado", len(df))
                        kpi2.metric("Com Alerta", len(df_problema), delta_color="inverse")
                        kpi3.metric("Normal", len(df_ok))
                        
                        st.divider()
                        
                        st.subheader("🚨 Atenção Necessária")
                        if not df_problema.empty:
                            st.error(f"Encontramos {len(df_problema)} clientes com problemas.")
                            st.dataframe(df_problema, use_container_width=True, hide_index=True)
                        else:
                            st.success("Tudo limpo! Nenhum cliente offline ou com falha.")
                            
                        with st.expander("Ver lista de clientes operando normalmente"):
                            st.dataframe(df_ok, use_container_width=True, hide_index=True)
                            
                    else:
                        st.warning("A lista de usinas foi baixada, mas os dados de tempo real (KPI) vieram vazios.")
                        st.write("Resposta crua da Huawei (KPI):", data_kpi)
                else:
                    st.warning("Não encontramos usinas vinculadas a essa conta de instalador.")
                    st.write("Resposta crua da Huawei (StationList):", data_stations)
