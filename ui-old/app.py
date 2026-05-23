import streamlit as st

# Configuración de página para diseño oscuro
st.set_page_config(layout="wide", page_title="SecPipeline")

# CSS para estilo oscuro personalizado
st.markdown("""
    <style>
    .stApp { background-color: #1a1a1a; color: white; }
    .block-container { padding-top: 2rem; }
    div[data-testid="stSidebar"] { background-color: #262626; }
    .status-ok { color: #2ecc71; }
    </style>
""", unsafe_allow_html=True)

# Sidebar: Pre-requisitos
with st.sidebar:
    st.header("PRE-REQUISITOS")
    pre_reqs = ["Docker corriendo", "Repo clonado", "Seed data lista", "API LLM configurada", "Playwright listo"]
    for req in pre_reqs:
        st.write(f"✅ {req}")
    
    st.divider()
    st.header("FASES DEL ANÁLISIS")
    fases = ["Análisis estático (IA)", "Discovery dinámico", "Generación de payloads", 
             "Revisión humana", "Ejecución de ataques", "Interpretación (IA)", "Correlación"]
    for fase in fases:
        st.checkbox(fase, disabled=True)
        
    st.button("Ejecutar análisis")

# Cuerpo Principal
st.title("SecPipeline")
st.subheader("Mattermost v9.x · Docker · PostgreSQL")

# Tabs superiores (ignorando "Experimento")
tab1, tab2, tab3 = st.tabs(["Pipeline híbrido", "Correlación", "Logs en vivo"])

with tab1:
    st.info("Lo que ves acá es el pipeline corriendo sobre Mattermost en vivo.")
    
    # Simulación de Bloques B3 a B9
    st.subheader("B3 — ANÁLISIS ESTÁTICO")
    st.warning("SQL Injection — auth.go:42")
    st.warning("XSS reflejado — search_handler.ts:87")
    
    st.subheader("B4 — DISCOVERY DINÁMICO")
    st.code("login_form — endpoint: /api/v4/users/login")
    st.code("search_bar — endpoint: /api/v4/posts/search")
    
    st.subheader("B5 — GENERACIÓN DE PAYLOADS")
    st.text("Payloads generados: 14")

with tab2:
    st.subheader("Resultados de Correlación")
    st.success("Resultado: VULNERABILIDAD CONFIRMADA — SQL Injection")
    st.metric("Confirmadas", "9/9", delta="0 falsos positivos")

with tab3:
    st.text("Logs del sistema...")