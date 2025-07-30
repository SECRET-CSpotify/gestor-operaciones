# -------------------------------
# 📦 GESTOR OPERACIONES CE - FINAL
# -------------------------------

import streamlit as st
import pandas as pd
import locale

try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except locale.Error:
    locale.setlocale(locale.LC_TIME, 'C')  # fallback genérico

from datetime import datetime, timedelta
from scraper import obtener_trm_oficial

# Configuración global para caracteres especiales
st.set_page_config(page_title="Gestor Operaciones CE", layout="centered")

ARCHIVO = 'operaciones.csv'
HISTORIAL = 'alertas.csv'

# -------------------------------
# 📌 MENÚ PRINCIPAL (RADIO)
# -------------------------------
menu = ["Registrar Operación", "Ver Operaciones", "Alertas"]
opcion = st.sidebar.radio("📌 MENÚ PRINCIPAL", menu)

# -------------------------------
# 📈 TRM OFICIAL Y ENTRADAS MANUALES
# -------------------------------
hoy = datetime.today().date()
manana = hoy + timedelta(days=1)

trm_oficial_hoy = obtener_trm_oficial(hoy) or 0.0
trm_oficial_manana = obtener_trm_oficial(manana) or 0.0

st.sidebar.title("📈 TRM Oficial")
trm_hoy_input = st.sidebar.number_input("TRM Hoy", value=trm_oficial_hoy, step=1.0)
trm_manana_input = st.sidebar.number_input("TRM Mañana", value=trm_oficial_manana, step=1.0)

diff = trm_manana_input - trm_hoy_input
if diff > 0:
    tendencia = "📈 Sube"
elif diff < 0:
    tendencia = "📉 Baja"
else:
    tendencia = "➡️ Igual"

st.sidebar.write(f"🔍 TRM Hoy: ${trm_hoy_input:,.2f}")
st.sidebar.write(f"🔍 TRM Mañana: ${trm_manana_input:,.2f} ({tendencia})")

# -------------------------------
# 📌 SECCIÓN SEGUIR AL CREADOR
# -------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("## 🎵 Sígue al Creador SECRET C")
st.sidebar.markdown(
    """
    <a href="https://open.spotify.com/intl-es/artist/2BrdB1i0wFfQFppxPvYFTy" target="_blank">
        <img src="https://upload.wikimedia.org/wikipedia/commons/1/19/Spotify_logo_without_text.svg" width="30"/>
    </a>
    &nbsp;&nbsp;
    <a href="https://www.instagram.com/imsecretc/" target="_blank">
        <img src="https://upload.wikimedia.org/wikipedia/commons/e/e7/Instagram_logo_2016.svg" width="30"/>
    </a>
    """,
    unsafe_allow_html=True
)

# -------------------------------
# 📌 FUNCIONES DE LÓGICA
# -------------------------------

def sugerir_mejor_dia(fecha_llegada, trm_hoy_manual=None, trm_manana_manual=None):
    dia_antes = fecha_llegada - timedelta(days=1)
    dia_llegada = fecha_llegada
    dia_despues = fecha_llegada + timedelta(days=1)

    trm_ayer = obtener_trm_oficial(dia_antes)
    trm_hoy = obtener_trm_oficial(dia_llegada)
    trm_manana = obtener_trm_oficial(dia_despues)

    if trm_hoy_manual:
        trm_hoy = trm_hoy_manual
    if trm_manana_manual:
        trm_manana = trm_manana_manual

    trms = {
        dia_antes: trm_ayer,
        dia_llegada: trm_hoy,
        dia_despues: trm_manana
    }

    trms_validas = {k: v for k, v in trms.items() if v is not None}
    if not trms_validas:
        return "Sin datos", 0.0, trms

    mejor_fecha = max(trms_validas, key=trms_validas.get)
    mejor_trm = trms_validas[mejor_fecha]
    return mejor_fecha, mejor_trm, trms

def guardar_alerta(consecutivo, cliente, alerta):
    try:
        df = pd.read_csv(HISTORIAL, encoding='utf-8')
    except FileNotFoundError:
        df = pd.DataFrame(columns=['Fecha', 'Consecutivo', 'Cliente', 'Alerta'])
    nueva = pd.DataFrame([{
        'Fecha': datetime.today().strftime("%Y-%m-%d"),
        'Consecutivo': consecutivo,
        'Cliente': cliente,
        'Alerta': alerta
    }])
    df = pd.concat([df, nueva], ignore_index=True)
    df.to_csv(HISTORIAL, index=False, encoding='utf-8')

# -------------------------------
# 📝 REGISTRAR OPERACIÓN
# -------------------------------
if opcion == 'Registrar Operación':
    hoy_fecha = datetime.today()
    alerta_html = """ ... """
    st.markdown(alerta_html, unsafe_allow_html=True)
    st.write("📅 HOY Es " + datetime.today().strftime('%A, %d de %B de %Y'))
    st.header("Registrar Nueva Operación")

    consecutivo = st.text_input("Consecutivo")
    modalidad = st.selectbox("Modalidad", ["Marítimo", "Aéreo", "Terrestre", "Ferroviario"])
    tipo = st.selectbox("Tipo", ["Importación", "Exportación"])
    cliente = st.text_input("Cliente")
    fecha_llegada = st.date_input("Fecha de Llegada", datetime.today())

if st.button("Guardar Operación"):
    try:
        df = pd.read_csv(ARCHIVO, encoding='utf-8')
    except FileNotFoundError:
        df = pd.DataFrame(columns=['Consecutivo', 'Modalidad', 'Tipo', 'Cliente', 'FechaLlegada'])

    nueva_operacion = pd.DataFrame([{
        'Consecutivo': consecutivo,
        'Modalidad': modalidad,
        'Tipo': tipo,
        'Cliente': cliente,
        'FechaLlegada': fecha_llegada.strftime('%Y-%m-%d')
    }])

    df = pd.concat([df, nueva_operacion], ignore_index=True)
    df.to_csv(ARCHIVO, index=False, encoding='utf-8')

    st.success(f"✅ Operación guardada correctamente: {consecutivo}")

    mejor_fecha, mejor_trm, _ = sugerir_mejor_dia(fecha_llegada, trm_hoy_input, trm_manana_input)
    if mejor_fecha != "Sin datos":
        mejor_dia_str = mejor_fecha.strftime("%A %d de %B de %Y")
    else:
        mejor_dia_str = "Sin datos"

    st.success(f"📌 Mejor día para facturar: {mejor_dia_str} (TRM aprox: ${mejor_trm:,.2f})")


# -------------------------------
# 📋 VER OPERACIONES
# -------------------------------
elif opcion == 'Ver Operaciones':
    st.header("📋 Operaciones Registradas")
    try:
        df = pd.read_csv(ARCHIVO, encoding='utf-8')
        hoy = datetime.today().date()
        datos = []

        for _, fila in df.iterrows():
            llegada = pd.to_datetime(fila['FechaLlegada']).date()
            cert_fletes = llegada - timedelta(days=7)
            dias_restantes = (llegada - hoy).days
            mejor_fecha, mejor_trm, _ = sugerir_mejor_dia(llegada, trm_hoy_input, trm_manana_input)
            mejor_dia_str = mejor_fecha.strftime("%A %d de %B de %Y") if mejor_fecha != "Sin datos" else "-"
            datos.append({
                'Consecutivo': fila['Consecutivo'],
                'Cliente': fila['Cliente'],
                'Tipo': fila['Tipo'],
                'Modalidad': fila['Modalidad'],
                'Fecha de Llegada': llegada.strftime("%A %d-%m-%Y"),
                'Certificación de Fletes': cert_fletes.strftime("%d-%m-%Y"),
                'Días para Arribo': dias_restantes,
                '📌 Mejor día para Facturar': f"{mejor_dia_str} (TRM aprox: ${mejor_trm:,.2f})"
            })

        if datos:
            st.dataframe(pd.DataFrame(datos))

            st.subheader("🗑️ Eliminar Operación")
            eliminar = st.multiselect(
                "Selecciona el/los consecutivo(s) a eliminar:",
                df['Consecutivo'].tolist()
            )

            if st.button("Eliminar Seleccionadas"):
                df = df[~df['Consecutivo'].isin(eliminar)]
                df.to_csv(ARCHIVO, index=False, encoding='utf-8')
                st.success("✅ Operación(es) eliminada(s) correctamente.")
                st.rerun()



        else:
            st.info("No hay operaciones registradas aún.")

    except FileNotFoundError:
        st.warning("No hay operaciones registradas aún.")

# -------------------------------
# 🔔 ALERTAS
# -------------------------------
elif opcion == 'Alertas':
    st.header("🔔 Alertas")
    try:
        df = pd.read_csv(ARCHIVO, encoding='utf-8')
        hoy = datetime.today().date()
        alertas = []

        for _, fila in df.iterrows():
            llegada = pd.to_datetime(fila['FechaLlegada']).date()
            cert_fletes = llegada - timedelta(days=7)
            mejor_fecha, _, _ = sugerir_mejor_dia(llegada, trm_hoy_input, trm_manana_input)

            # 🚢 Llegada de carga HOY
            if llegada == hoy:
                alertas.append({
                    'Tipo': '🚢 Llegada de Carga',
                    'Consecutivo': fila['Consecutivo'],
                    'Cliente': fila['Cliente'],
                    'Fecha': llegada
                })

            # 📄 Certificación de Fletes HOY
            if cert_fletes == hoy:
                alertas.append({
                    'Tipo': '📄 Certificación de Fletes',
                    'Consecutivo': fila['Consecutivo'],
                    'Cliente': fila['Cliente'],
                    'Fecha': cert_fletes,
                    'Fecha de Arribo': llegada
                })

            # 💰 Facturación sugerida HOY
            if mejor_fecha != "Sin datos" and mejor_fecha == hoy:
                alertas.append({
                    'Tipo': '💰 Fecha Facturación',
                    'Consecutivo': fila['Consecutivo'],
                    'Cliente': fila['Cliente'],
                    'Fecha': mejor_fecha,
                    'Fecha de Arribo': llegada
                })

        if alertas:
            alertas_ordenadas = sorted(alertas, key=lambda x: x['Fecha'])
            for alerta in alertas_ordenadas:
                alerta_html = f"""
<div style="border: 2px solid #007BFF; border-radius: 10px; padding: 10px; margin-bottom: 10px;">
    <strong>{alerta['Tipo']}</strong><br>
    Consecutivo: {alerta['Consecutivo']}<br>
    Cliente: {alerta['Cliente']}<br>
    Fecha: {alerta['Fecha'].strftime('%A, %d de %B de %Y')}<br>
    Fecha de Arribo: {alerta['Fecha de Arribo'].strftime('%A, %d de %B de %Y')}
</div>
"""
                st.markdown(alerta_html, unsafe_allow_html=True)
        else:
            st.success("✅ Sin alertas próximas.")
    except FileNotFoundError:
        st.warning("No hay operaciones para verificar alertas.")
