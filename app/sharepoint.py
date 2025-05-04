from dotenv import load_dotenv
import os
import requests
import pandas as pd
from msal import ConfidentialClientApplication
import json

# Configuración
TENANT_ID = os.getenv("TENANT_ID")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

SITE_NAME = os.getenv("SITE_NAME")
DRIVE_ID = os.getenv("DRIVE_ID")
FOLDER_PATH = os.getenv("FOLDER_PATH") 
OUTPUT_FILE = "listado_archivos_graph.xlsx"

# 1. Obtener token de acceso
def get_access_token():
    authority = f"https://login.microsoftonline.com/{TENANT_ID}"
    app = ConfidentialClientApplication(
        CLIENT_ID,
        authority=authority,
        client_credential=CLIENT_SECRET
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    return result.get("access_token")

# 2. Obtener ID de la carpeta
def get_folder_id(access_token, drive_id, folder_path):
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/root:/{folder_path}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("id")
    else:
        raise Exception(f"Error al obtener folder ID: {response.text}")

# 3. Listar archivos en la carpeta
def list_files_in_folder(access_token, drive_id, folder_id):
    url = f"https://graph.microsoft.com/v1.0/drives/{drive_id}/items/{folder_id}/children"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get("value", [])
    else:
        raise Exception(f"Error al listar archivos: {response.text}")

# Ejecución principal
try:
    # Autenticación
    access_token = get_access_token()
    if not access_token:
        raise Exception("No se pudo obtener el token de acceso")
    else:
        print("Token de acceso obtenido correctamente" + access_token)

    # Obtener ID de la carpeta
    folder_id = get_folder_id(access_token, DRIVE_ID, FOLDER_PATH)
    
    # Listar archivos
    files = list_files_in_folder(access_token, DRIVE_ID, folder_id)
    
    # Procesar resultados
    file_data = []
    for file in files:
        if "file" in file:  # Solo archivos, no carpetas
            file_data.append({
                "Nombre": file.get("name"),
                "Ruta": file.get("webUrl"),
                "Tamaño (KB)": round(file.get("size", 0) / 1024, 2),
                "Modificado": file.get("lastModifiedDateTime"),
                "Creado": file.get("createdDateTime"),
                "Tipo": file.get("file", {}).get("mimeType")
            })

    # Exportar a Excel
    if file_data:
        df = pd.DataFrame(file_data)
        df.to_excel(OUTPUT_FILE, index=False)
        print(f"Archivos listados correctamente en {OUTPUT_FILE}")
        print(f"Total de archivos: {len(file_data)}")
    else:
        print("No se encontraron archivos en la carpeta especificada")

except Exception as e:
    print(f"Error: {str(e)}")