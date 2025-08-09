# -------------------------------
# 📦 GESTOR OPERACIONES CE - GOOGLE SHEETS
# -------------------------------

import streamlit as st
from streamlit.runtime.scriptrunner import RerunException, RerunData
import pandas as pd
import os
from datetime import datetime, timedelta, time
from babel.dates import format_date
from scraper import obtener_trm_oficial
import pytz
import json
import gspread
from google.oauth2 import service_account
from gspread_dataframe import get_as_dataframe, set_with_dataframe

# -------------------------------
# Configuración inicial
# -------------------------------
st.set_page_config(page_title="Gestor Operaciones CE", layout="centered")
TIMEZONE = pytz.timezone("America/Bogota")

# Archivos locales de respaldo
ARCHIVO_CSV = "operaciones.csv"
HISTORIAL_CSV = "alertas.csv"
TRM_HISTORY = "trm_history.csv"

# -------------------------------
# Autenticación
# -------------------------------
try:
    USER = st.secrets["auth"].get("usuario")
    PASS = st.secrets["auth"].get("password")
except Exception:
    USER = None
    PASS = None

def login_ui():
    st.sidebar.header("🔒 Iniciar Sesión")
    usuario = st.sidebar.text_input("Usuario")
    contrasena = st.sidebar.text_input("Contraseña", type="password")
    if st.sidebar.button("Iniciar sesión"):
        if USER is None or PASS is None:
            st.sidebar.error("Credenciales no configuradas en secrets.toml")
            return
        if usuario == USER and contrasena == PASS:
            st.session_state["logged_in"] = True
            raise RerunException(RerunData())
        else:
            st.sidebar.error("Usuario o contraseña incorrectos")

if "logged_in" not in st.session_state or not st.session_state.get("logged_in", False):
    login_ui()
    st.stop()

# -------------------------------
# Helper functions para Google Sheets
# -------------------------------
def extract_sheet_id_from_url(url):
    try:
        parts = url.split("/d/")
        if len(parts) > 1:
            return parts[1].split("/")[0]
    except Exception:
        return None
    return None

def get_sheet_info_from_secrets():
    creds_info = None
    spreadsheet_identifier = None

    try:
        if "gcp" in st.secrets and "service_account" in st.secrets["gcp"]:
            sa = st.secrets["gcp"]["service_account"]
            creds_info = sa if isinstance(sa, dict) else json.loads(sa)
            spreadsheet_identifier = st.secrets["gcp"].get("sheet_id") or st.secrets["gcp"].get("spreadsheet_url")
    except Exception:
        pass

    if creds_info is None and "gcp_service_account" in st.secrets:
        try:
            sa = st.secrets["gcp_service_account"]
            creds_info = sa if isinstance(sa, dict) else json.loads(sa)
        except Exception:
            pass

    if spreadsheet_identifier is None:
        try:
            if "sheets" in st.secrets:
                spreadsheet_identifier = st.secrets["sheets"].get("spreadsheet_url") or st.secrets["sheets"].get("sheet_id")
        except Exception:
            pass

    return creds_info, spreadsheet_identifier

def get_gs_client():
    creds_info, _ = get_sheet_info_from_secrets()
    if not creds_info:
        return None
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = service_account.Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds)
    except Exception as e:
        st.error(f"Error al autenticar con Google: {str(e)}")
        return None

def open_spreadsheet():
    gc = get_gs_client()
    if not gc:
        return None, None
    
    _, spreadsheet_identifier = get_sheet_info_from_secrets()
    if not spreadsheet_identifier:
        return None, None
    
    try:
        if spreadsheet_identifier.startswith("http"):
            sh = gc.open_by_url(spreadsheet_identifier)
            return sh, spreadsheet_identifier
        else:
            sh = gc.open_by_key(spreadsheet_identifier)
            return sh, spreadsheet_identifier
    except Exception:
        try:
            sheet_id = extract_sheet_id_from_url(spreadsheet_identifier)
            if sheet_id:
                return gc.open_by_key(sheet_id), sheet_id
        except Exception:
            pass
    return None, None

# -------------------------------
# Operaciones con Google Sheets
# -------------------------------
def ensure_worksheet(sheet, title, headers):
    try:
        ws = sheet.worksheet(title)
    except Exception:
        ws = sheet.add_worksheet(title=title, rows="1000", cols=str(len(headers)))
        ws.append_row(headers)
    return ws

def read_sheet_dataframe(sheet_title="operaciones"):
    sh, _ = open_spreadsheet()
    base_columns = ['Consecutivo','Modalidad','Tipo','Cliente','FechaLlegada']
    additional_columns = ['FechaCertificacionFletes', 'EstadoCertificacionFletes',
                         'FechaSolicitarLiberacion', 'EstadoSolicitarLiberacion']
    all_columns = base_columns + additional_columns
    
    if sh:
        try:
            ws = ensure_worksheet(sh, sheet_title, all_columns)
            df = get_as_dataframe(ws, evaluate_formulas=True, usecols=None) or pd.DataFrame(columns=all_columns)
            
            # Conversión de tipos de datos
            for col in base_columns[:4] + additional_columns[1::2]:
                if col in df.columns:
                    df[col] = df[col].astype(str)
            
            for col in ['FechaLlegada', 'FechaCertificacionFletes', 'FechaSolicitarLiberacion']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
            
            # Limpieza de datos
            df = df.dropna(how="all")
            if list(df.columns)[:len(base_columns)] != base_columns:
                df.columns = [str(c) for c in df.columns]
                if len(df.columns) >= len(all_columns):
                    df = df.iloc[:, :len(all_columns)]
                    df.columns = all_columns
                else:
                    for col in all_columns:
                        if col not in df.columns:
                            df[col] = ""
                    df = df[all_columns]
            
            df = df.dropna(subset=['Consecutivo'], how='all').fillna("")
            return df[all_columns]
        except Exception as e:
            st.error(f"Error al leer datos: {str(e)}")
    
    # Fallback a CSV local
    if os.path.exists(ARCHIVO_CSV):
        try:
            return pd.read_csv(ARCHIVO_CSV, encoding='utf-8')
        except Exception:
            pass
    return pd.DataFrame(columns=all_columns)

def save_sheet_dataframe(df, sheet_title="operaciones"):
    base_columns = ['Consecutivo','Modalidad','Tipo','Cliente','FechaLlegada']
    additional_columns = ['FechaCertificacionFletes', 'EstadoCertificacionFletes',
                         'FechaSolicitarLiberacion', 'EstadoSolicitarLiberacion']
    all_columns = base_columns + additional_columns
    
    for col in all_columns:
        if col not in df.columns:
            df[col] = ""
    
    df_to_save = df[all_columns].copy()
    sh, _ = open_spreadsheet()
    
    if sh:
        try:
            ws = ensure_worksheet(sh, sheet_title, all_columns)
            set_with_dataframe(ws, df_to_save, include_index=False, include_column_header=True, resize=True)
        except Exception as e:
            st.error(f"Error al guardar datos: {str(e)}")
    
    # Backup local
    df_to_save.to_csv(ARCHIVO_CSV, index=False, encoding='utf-8')

# -------------------------------
# Funciones principales
# -------------------------------
def read_operaciones_df():
    return read_sheet_dataframe("operaciones")

def save_operaciones_df(df):
    save_sheet_dataframe(df, "operaciones")

# -------------------------------
# Manejo de Alertas
# -------------------------------
def read_alertas_sheet():
    sh, _ = open_spreadsheet()
    expected_columns = ["FechaRegistro","Consecutivo","Cliente","Tipo","FechaSuceso","Resuelta"]
    
    if sh:
        try:
            ws = ensure_worksheet(sh, "alertas", expected_columns)
            df = get_as_dataframe(ws, evaluate_formulas=True) or pd.DataFrame(columns=expected_columns)
            df = df.dropna(how="all")
            
            for col in expected_columns:
                if col not in df.columns:
                    df[col] = ""
            
            try:
                df['FechaSuceso'] = pd.to_datetime(df['FechaSuceso']).dt.date
            except Exception:
                pass
            
            return df[expected_columns]
        except Exception:
            pass
    
    if os.path.exists(HISTORIAL_CSV):
        try:
            df = pd.read_csv(HISTORIAL_CSV, encoding='utf-8')
            df['FechaSuceso'] = pd.to_datetime(df['FechaSuceso']).dt.date
            return df
        except Exception:
            pass
    return pd.DataFrame(columns=expected_columns)

def guardar_alerta_historial(consecutivo, cliente, tipo, fecha_suceso):
    row = {
        "FechaRegistro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Consecutivo": consecutivo,
        "Cliente": cliente,
        "Tipo": tipo,
        "FechaSuceso": fecha_suceso.strftime("%Y-%m-%d") if isinstance(fecha_suceso, (datetime.date, datetime.datetime)) else str(fecha_suceso),
        "Resuelta": False
    }
    
    sh, _ = open_spreadsheet()
    if sh:
        try:
            ws = ensure_worksheet(sh, "alertas", list(row.keys()))
            ws.append_row([row[k] for k in ["FechaRegistro","Consecutivo","Cliente","Tipo","FechaSuceso","Resuelta"]])
            return
        except Exception:
            pass
    
    # Fallback local
    df_hist = read_alertas_sheet()
    df_hist = pd.concat([df_hist, pd.DataFrame([row])], ignore_index=True)
    df_hist.to_csv(HISTORIAL_CSV, index=False, encoding='utf-8')

def guardar_alerta(consecutivo, cliente, mensaje):
    guardar_alerta_historial(consecutivo, cliente, mensaje, datetime.now())

def read_alertas_historial():
    return read_alertas_sheet()

def marcar_alerta_resuelta(idx):
    df = read_alertas_historial()
    if 0 <= idx < len(df):
        df.loc[idx, 'Resuelta'] = True
        sh, _ = open_spreadsheet()
        if sh:
            try:
                ws = ensure_worksheet(sh, "alertas", df.columns.tolist())
                set_with_dataframe(ws, df, include_index=False, include_column_header=True, resize=True)
                return
            except Exception:
                pass
        df.to_csv(HISTORIAL_CSV, index=False, encoding='utf-8')

# -------------------------------
# Manejo de TRM
# -------------------------------
_trm_cache = {}

def save_trm_history(fecha, trm_val):
    row = {"fecha": fecha.strftime("%Y-%m-%d"), "trm": trm_val}
    if os.path.exists(TRM_HISTORY):
        df = pd.read_csv(TRM_HISTORY, encoding='utf-8')
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(TRM_HISTORY, index=False, encoding='utf-8')

def last_known_trm():
    if os.path.exists(TRM_HISTORY):
        df = pd.read_csv(TRM_HISTORY, encoding='utf-8')
        if not df.empty:
            return float(df.iloc[-1]['trm'])
    return None

def obtener_trm_cached(fecha):
    key = fecha.strftime("%Y-%m-%d")
    if key in _trm_cache:
        return _trm_cache[key]
    
    try:
        trm = obtener_trm_oficial(fecha)
        if trm is not None and trm > 0:
            _trm_cache[key] = trm
            save_trm_history(fecha, trm)
            return trm
    except Exception:
        pass
    
    last = last_known_trm()
    if last is not None:
        _trm_cache[key] = last
        return last
    
    return 0.0

# -------------------------------
# Funciones de utilidad
# -------------------------------
def seconds_until_next_trm(target_hour=14, target_minute=0):
    now = datetime.now(TIMEZONE)
    today_target = TIMEZONE.localize(datetime.combine(now.date(), time(hour=target_hour, minute=target_minute)))
    
    if now >= today_target:
        tomorrow = now.date() + timedelta(days=1)
        next_target = TIMEZONE.localize(datetime.combine(tomorrow, time(hour=target_hour, minute=target_minute)))
    else:
        next_target = today_target
    
    return int((next_target - now).total_seconds())

def human_readable_countdown(sec):
    if sec <= 0:
        return "0s"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    parts = []
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    parts.append(f"{s}s")
    return " ".join(parts)

def sugerir_mejor_dia(fecha_llegada, trm_hoy_manual=None, trm_manana_manual=None):
    dia_antes = fecha_llegada - timedelta(days=1)
    dia_llegada = fecha_llegada
    dia_despues = fecha_llegada + timedelta(days=1)

    trm_ayer = obtener_trm_cached(dia_antes)
    trm_hoy = obtener_trm_cached(dia_llegada)
    trm_manana = obtener_trm_cached(dia_despues)

    if trm_hoy_manual:
        trm_hoy = trm_hoy_manual
    if trm_manana_manual:
        trm_manana = trm_manana_manual

    trms = {
        dia_antes: trm_ayer,
        dia_llegada: trm_hoy,
        dia_despues: trm_manana
    }

    trms_validas = {k: v for k, v in trms.items() if v is not None and v > 0}
    if not trms_validas:
        return "Sin datos", 0.0, trms

    mejor_fecha = max(trms_validas, key=trms_validas.get)
    mejor_trm = trms_validas[mejor_fecha]
    return mejor_fecha, mejor_trm, trms

# -------------------------------
# Interfaz de usuario
# -------------------------------
hoy = datetime.now(TIMEZONE).date()
manana = hoy + timedelta(days=1)

trm_hoy = obtener_trm_cached(hoy)
trm_manana = obtener_trm_cached(manana)

# Fallback si no hay TRM disponible
if trm_hoy == 0.0:
    trm_hoy = last_known_trm() or 0.0
if trm_manana == 0.0:
    trm_manana = last_known_trm() or trm_hoy or 0.0

# Sidebar TRM
st.sidebar.title("📈 TRM Oficial (actualizable)")
st.sidebar.write(f"🔍 TRM Hoy: ${trm_hoy:,.2f}")
st.sidebar.write(f"🔍 TRM Mañana: ${trm_manana:,.2f}")

segundos_rest = seconds_until_next_trm(14, 0)
st.sidebar.write(f"⏳ Tiempo hasta próxima TRM (14:00 COL): {human_readable_countdown(segundos_rest)}")

# Inputs manuales TRM
trm_hoy_input = st.sidebar.number_input("TRM Hoy (editar)", value=float(trm_hoy), step=1.0)
trm_manana_input = st.sidebar.number_input("TRM Mañana (editar)", value=float(trm_manana), step=1.0)

# Menú principal
menu = ["Registrar Operación", "Ver Operaciones", "Alertas"]
opcion = st.sidebar.radio("Selecciona:", menu)

# -------------------------------
# Registrar Operación
# -------------------------------
if opcion == "Registrar Operación":
    st.header("Registrar Nueva Operación")
    st.write(f"📅 Hoy es: {format_date(datetime.now(TIMEZONE).date(), format='full', locale='es')}")
    df_ops = read_operaciones_df()

    consecutivo = st.text_input("Consecutivo (ej. DO AT25621)")
    modalidad = st.selectbox("Modalidad", ["Marítimo", "Aéreo", "Terrestre", "Ferroviario"])
    tipo = st.selectbox("Tipo", ["Importación", "Exportación"])
    cliente = st.text_input("Cliente")
    fecha_llegada = st.date_input("Fecha de Arribo (ETA)", datetime.now(TIMEZONE).date())

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Guardar Operación"):
            if not consecutivo:
                st.error("El campo Consecutivo es obligatorio.")
            else:
                df_ops = read_operaciones_df()
                nueva_operacion = {
                    'Consecutivo': consecutivo,
                    'Modalidad': modalidad,
                    'Tipo': tipo,
                    'Cliente': cliente,
                    'FechaLlegada': fecha_llegada.strftime("%Y-%m-%d"),
                    'FechaCertificacionFletes': "",
                    'EstadoCertificacionFletes': "",
                    'FechaSolicitarLiberacion': "",
                    'EstadoSolicitarLiberacion': ""
                }

                if consecutivo in df_ops['Consecutivo'].values:
                    df_ops.loc[df_ops['Consecutivo'] == consecutivo, list(nueva_operacion.keys())] = list(nueva_operacion.values())
                    mensaje = "✅ Operación actualizada correctamente."
                else:
                    df_ops = pd.concat([df_ops, pd.DataFrame([nueva_operacion])], ignore_index=True)
                    mensaje = "✅ Operación creada correctamente."

                save_operaciones_df(df_ops)
                st.success(mensaje)

                # Generar alertas
                guardar_alerta(consecutivo, cliente, f"Registro de operación para llegada {fecha_llegada.strftime('%Y-%m-%d')}")
                
                cert_fletes = fecha_llegada - timedelta(days=7)
                if cert_fletes <= fecha_llegada:
                    guardar_alerta(consecutivo, cliente, "Programada: Certificación de Fletes")
                
                liberacion = fecha_llegada - timedelta(days=2)
                if liberacion <= fecha_llegada:
                    guardar_alerta(consecutivo, cliente, "Programada: Solicitar Liberación")
                
                # Sugerencia TRM
                mejor_fecha, mejor_trm, _ = sugerir_mejor_dia(fecha_llegada, trm_hoy_input, trm_manana_input)
                if mejor_fecha != "Sin datos":
                    sd = format_date(mejor_fecha, format="EEEE d 'de' MMMM 'de' yyyy", locale='es')
                    st.info(f"📌 Sugerencia: mejor día para facturar -> {sd} (TRM aprox: ${mejor_trm:,.2f})")
                
                st.rerun()

    with col2:
        st.write("Ayuda rápida:")
        st.write("- Guarda operaciones y crea alertas programadas.")
        st.write("- Para modificar una operación puedes usar la pestaña 'Ver Operaciones'.")

# -------------------------------
# Ver Operaciones
# -------------------------------
elif opcion == "Ver Operaciones":
    st.header("📋 Operaciones Registradas")
    df_ops = read_operaciones_df()
    
    # Asegurar columnas necesarias
    expected_columns = ['Consecutivo', 'Modalidad', 'Tipo', 'Cliente', 'FechaLlegada',
                       'FechaCertificacionFletes', 'EstadoCertificacionFletes',
                       'FechaSolicitarLiberacion', 'EstadoSolicitarLiberacion']
    
    for col in expected_columns:
        if col not in df_ops.columns:
            df_ops[col] = ""
    
    # Convertir fechas
    df_ops['FechaLlegada_date'] = pd.to_datetime(df_ops['FechaLlegada'], errors='coerce').dt.date
    df_ops['FechaCertificacionFletes'] = pd.to_datetime(df_ops['FechaCertificacionFletes'], errors='coerce').dt.date
    df_ops['FechaSolicitarLiberacion'] = pd.to_datetime(df_ops['FechaSolicitarLiberacion'], errors='coerce').dt.date
    
    # Calcular fechas programadas
    df_ops['CertFletes_Programada'] = df_ops['FechaLlegada_date'] - pd.Timedelta(days=7)
    df_ops['Liberacion_Programada'] = df_ops['FechaLlegada_date'] - pd.Timedelta(days=2)
    
    # Filtrar operaciones recientes
    fecha_min = hoy - timedelta(days=30)
    df_visible = df_ops[df_ops['FechaLlegada_date'] >= fecha_min].copy()
    
    # Función para mostrar estado
    def formato_accion(fecha_programada, fecha_real, estado_real):
        try:
            estado = str(estado_real).strip().lower() if pd.notna(estado_real) else ""
            
            if pd.notna(fecha_real):
                fecha_str = format_date(fecha_real, format="d MMM", locale='es')
                if estado in ["lista", "completado", "hecho", "realizado"]:
                    return f"✅ Realizado ({fecha_str})"
                return f"⏳ Pendiente ({fecha_str})"
            
            if pd.notna(fecha_programada):
                fecha_str = format_date(fecha_programada, format="d MMM", locale='es')
                if fecha_programada < datetime.now().date():
                    return f"⚠️ Atrasado ({fecha_str})"
                return f"📅 Programado ({fecha_str})"
            
            return "Sin programar"
        except Exception:
            return "Sin datos"
    
    # Aplicar formato
    df_visible['Certificación Fletes'] = df_visible.apply(
        lambda row: formato_accion(
            row['CertFletes_Programada'],
            row['FechaCertificacionFletes'],
            row['EstadoCertificacionFletes']
        ), axis=1
    )
    
    df_visible['Solicitar Liberación'] = df_visible.apply(
        lambda row: formato_accion(
            row['Liberacion_Programada'],
            row['FechaSolicitarLiberacion'],
            row['EstadoSolicitarLiberacion']
        ), axis=1
    )
    
    # Columnas adicionales
    df_visible['Arribo (ETA)'] = df_visible['FechaLlegada_date'].apply(
        lambda d: format_date(d, format="EEE d MMM yyyy", locale='es') if pd.notna(d) else "Sin fecha"
    )
    
    hoy_dt = pd.to_datetime(hoy)
    df_visible['Días ETA'] = df_visible['FechaLlegada_date'].apply(
        lambda d: (pd.to_datetime(d) - hoy_dt).days if pd.notna(d) else "Sin fecha"
    )
    
    # Columnas para mostrar
    columnas_mostrar = ['Consecutivo', 'Modalidad', 'Tipo', 'Cliente', 'Arribo (ETA)',
                       'Días ETA', 'Certificación Fletes', 'Solicitar Liberación']
    
    # Editor de datos
    st.subheader("Editar operaciones")
    df_edit = st.data_editor(
        df_visible[columnas_mostrar],
        num_rows="dynamic",
        disabled=['Certificación Fletes', 'Solicitar Liberación', 'Arribo (ETA)', 'Días ETA'],
        column_config={
            "Certificación Fletes": st.column_config.TextColumn(
                "Cert. Fletes",
                help="7 días antes del ETA"
            ),
            "Solicitar Liberación": st.column_config.TextColumn(
                "Sol. Liberación",
                help="2 días antes del ETA"
            ),
            "Días ETA": st.column_config.NumberColumn(
                "Días para ETA",
                format="%d",
                help="Días restantes para el arribo"
            )
        }
    )
    
    # Botones de acción
    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 Guardar cambios"):
            df_current = read_operaciones_df()
            for _, row in df_edit.iterrows():
                cons = row['Consecutivo']
                if cons in df_current['Consecutivo'].values:
                    df_current.loc[df_current['Consecutivo'] == cons, ['Modalidad', 'Tipo', 'Cliente']] = [
                        row['Modalidad'], row['Tipo'], row['Cliente']
                    ]
            save_operaciones_df(df_current)
            st.success("✅ Cambios guardados.")
            st.rerun()

    with col2:
        eliminar = st.multiselect(
            "Seleccionar para eliminar",
            options=df_visible['Consecutivo'].unique()
        )
        if st.button("🗑️ Eliminar seleccionadas") and eliminar:
            df_current = read_operaciones_df()
            df_current = df_current[~df_current['Consecutivo'].isin(eliminar)]
            save_operaciones_df(df_current)
            st.success(f"✅ {len(eliminar)} operación(es) eliminada(s).")
            st.rerun()

    # Vista resumida
    st.subheader("Resumen de Operaciones")
    st.dataframe(
        df_visible[columnas_mostrar],
        hide_index=True,
        use_container_width=True
    )

# -------------------------------
# Alertas
# -------------------------------
elif opcion == "Alertas":
    st.header("🔔 Alertas y Tareas")
    df_ops = read_operaciones_df()
    hoy = datetime.now(TIMEZONE).date()

    alertas = []
    for _, fila in df_ops.iterrows():
        try:
            llegada = pd.to_datetime(fila['FechaLlegada']).date()
            if pd.isna(llegada):
                continue
                
            cert_fletes = llegada - timedelta(days=7)
            liberacion = llegada - timedelta(days=2)
            mejor_fecha, _, _ = sugerir_mejor_dia(llegada, trm_hoy_input, trm_manana_input)

            if llegada == hoy:
                alertas.append({'Tipo':'🚢 Llegada de Carga','Consecutivo':fila['Consecutivo'],'Cliente':fila['Cliente'],'Fecha':llegada,'ETA':llegada})
            if cert_fletes == hoy:
                alertas.append({'Tipo':'📄 Certificación de Fletes','Consecutivo':fila['Consecutivo'],'Cliente':fila['Cliente'],'Fecha':cert_fletes,'ETA':llegada})
            if liberacion == hoy:
                alertas.append({'Tipo':'📦 Solicitar Liberación','Consecutivo':fila['Consecutivo'],'Cliente':fila['Cliente'],'Fecha':liberacion,'ETA':llegada})
            if mejor_fecha != "Sin datos" and mejor_fecha == hoy:
                alertas.append({'Tipo':'💰 Fecha Facturación','Consecutivo':fila['Consecutivo'],'Cliente':fila['Cliente'],'Fecha':mejor_fecha,'ETA':llegada})
        except Exception:
            continue

    df_hist = read_alertas_historial()

    filtro = st.selectbox("Filtrar alertas por:", ["Hoy","Esta semana","Próximo mes","Todas"])
    def in_range(fecha, opcion):
        if opcion == "Hoy":
            return fecha == hoy
        if opcion == "Esta semana":
            inicio = hoy - timedelta(days=hoy.weekday())
            fin = inicio + timedelta(days=6)
            return inicio <= fecha <= fin
        if opcion == "Próximo mes":
            fin = hoy + timedelta(days=30)
            return hoy <= fecha <= fin
        return True

    alertas_filtradas = [a for a in alertas if in_range(a['Fecha'], filtro)]
    st.subheader("Alertas generadas desde operaciones")
    if alertas_filtradas:
        for a in sorted(alertas_filtradas, key=lambda x: x['Fecha']):
            fecha_str = format_date(a['Fecha'], format="full", locale='es')
            eta_str = format_date(a['ETA'], format="EEEE, d 'de' MMMM 'de' yyyy", locale='es')
            st.markdown(f"""
            <div style="border:2px solid #007BFF; border-radius:10px; padding:10px; margin-bottom:8px;">
                <strong>{a['Tipo']}</strong><br>
                Consecutivo: {a['Consecutivo']}<br>
                Cliente: {a['Cliente']}<br>
                Fecha del suceso: {fecha_str}<br>
                Fecha de Arribo (ETA): {eta_str}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("No hay alertas generadas por operaciones en este periodo.")

    st.subheader("Historial de alertas (registro)")
    df_hist = read_alertas_historial()
    if not df_hist.empty:
        df_hist['FechaSuceso_date'] = pd.to_datetime(df_hist['FechaSuceso']).dt.date
        df_hist_vis = df_hist[df_hist['FechaSuceso_date'].apply(lambda d: in_range(d, filtro))]
        st.dataframe(df_hist_vis[['FechaRegistro','Consecutivo','Cliente','Tipo','FechaSuceso','Resuelta']])

        idx_to_mark = st.number_input("Índice de alerta para marcar resuelta", min_value=0, max_value=len(df_hist_vis)-1 if len(df_hist_vis)>0 else 0, step=1)
        if st.button("Marcar alerta como resuelta"):
            real_idx = df_hist_vis.index[idx_to_mark]
            marcar_alerta_resuelta(real_idx)
            st.success("✅ Alerta marcada como resuelta.")
            st.rerun()
    else:
        st.info("No hay historial de alertas.")