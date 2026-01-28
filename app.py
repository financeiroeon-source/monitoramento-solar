import streamlit as st
import requests
import pandas as pd

# --- CONFIGURAÇÕES ---
BASE_URL = "https://la5.fusionsolar.huawei.com/thirdData"

st.set_page_config(page_title="Monitoramento Huawei", page_icon="☀️", layout="wide")

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
        if r.json().get("success", False): return r.headers.get("xsrf-token")
    except Exception as e:
        st.error(f"Erro Login: {e}")
    return None

def get_data(url, token, payload):
    try:
        r = requests.post(url, json=payload, headers={"xsrf-token": token}, timeout=15)
        return r.json()
    except:
        return {}

# --- LÓGICA ---
if btn_carregar:
    if not api_user or not api_pass:
        st.warning("Preencha usuário e senha.")
    else:
        with st.spinner("Conectando..."):
            token = login_huawei(api_user, api_pass)
            if token:
                # 1. Pegar Lista
                raw_stations = get_data(f"{BASE_URL}/getStationList", token, {"pageNo": 1, "pageSize": 100})
                stations = raw_stations.get("data", {}).get("list", []) if raw_stations.get("data") else []

                if stations:
                    codes = ",".join([str(s["stationCode"]) for s in stations])
                    
                    # 2. Pegar Status (KPI)
                    raw_kpi = get_data(f"{BASE_URL}/getStationRealKpi", token, {"stationCodes": codes})
                    kpi_list = raw_kpi.get("data", {}).get("list", []) if raw_kpi.get("data") else []

                    # --- ÁREA DE DEBUG (NOVO) ---
                    with st.expander("🛠️ CLIQUE AQUI SE TODOS ESTIVEREM OFFLINE (Ver Dados Brutos)"):
                        st.write("Estrutura do primeiro cliente recebida da Huawei:")
                        if kpi_list:
                            st.json(kpi_list[0])
                        else:
                            st.write("Nenhum dado de KPI recebido.")

                    lista_final = []
                    # Mapeamento Status: 1=Conectado, 2=Falha, 3=Offline
                    map_status = {1: "🟢 ONLINE", 2: "🔴 FALHA", 3: "⚫ OFFLINE"}

                    for item in kpi_list:
                        # Tenta achar os dados na raiz ou dentro de 'dataItemMap'
                        dados = item.get("dataItemMap", item)
                        
                        s_code = item.get("stationCode")
                        usina = next((s for s in stations if str(s["stationCode"]) == str(s_code)), {})
                        
                        # Tenta ler o status com diferentes nomes de chave possíveis
                        state = dados.get("realHealthState") or dados.get("real_health_state") or 3
                        power = dados.get("day_power") or dados.get("dayPower") or 0
                        
                        lista_final.append({
                            "Cliente": usina.get("stationName", f"ID {s_code}"),
                            "Status": map_status.get(state, "DESCONHECIDO"),
                            "Potência (kW)": power,
                            "Endereço": usina.get("stationAddr", "-")
                        })

                    df = pd.DataFrame(lista_final)
                    
                    # Filtros
                    df_offline = df[df["Status"].str.contains("OFFLINE|FALHA")]
                    df_online = df[df["Status"].str.contains("ONLINE")]

                    # Métricas
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Total", len(df))
                    c2.metric("Com Problema", len(df_offline))
                    c3.metric("Operando", len(df_online))

                    st.divider()
                    if not df_offline.empty:
                        st.error("⚠️ Clientes com Alerta")
                        st.dataframe(df_offline, use_container_width=True, hide_index=True)
                    else:
                        st.success("Tudo certo! Ninguém offline.")
                        
                    st.subheader("Clientes Normais")
                    st.dataframe(df_online, use_container_width=True, hide_index=True)

                else:
                    st.warning("Lista de usinas veio vazia.")
