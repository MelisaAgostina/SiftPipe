import streamlit as st
import subprocess
import sys
import pandas as pd
import json
import os

st.set_page_config(page_title="SiftPipe", layout="wide")

st.title("Pipeline Híbrido: Análisis de Seguridad")

mode = st.radio("Modo de ejecución:", ["fresh", "restore"], index=0)

if st.button("Run Analysis"):
    with st.spinner("Ejecutando pipeline..."):
        try:
            # Ejecución del main.py
            subprocess.run([sys.executable, "main.py", "--mode", mode], check=True)
            st.success("¡Pipeline finalizado!")
            
            # Cargar resultados (asumiendo que los bloques guardan en results/correlation_results.json)
            res_path = "../results/correlation_results.json"
            if os.path.exists(res_path):
                with open(res_path, 'r') as f:
                    data = json.load(f)
                
                # Conversión a DataFrame de Pandas
                df = pd.DataFrame(data)
                
                st.subheader("Resultados de Correlación")
                st.dataframe(df.style.applymap(lambda x: 'background-color: #d4edda' if x == 'CONFIRMADA' else '', subset=['result']))
                
        except subprocess.CalledProcessError:
            st.error("Error en la ejecución del pipeline.")