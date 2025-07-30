import requests

def obtener_trm_oficial(fecha):
    fecha_str = fecha.strftime("%Y-%m-%d")
    url = f"https://www.datos.gov.co/resource/mcec-87by.json?$where=vigenciadesde='{fecha_str}T00:00:00.000'"
    respuesta = requests.get(url)
    if respuesta.status_code != 200:
        return None
    datos = respuesta.json()
    if datos:
        valor = datos[0]['valor']
        valor = valor.replace(",", "")
        return round(float(valor), 2)
    else:
        return None