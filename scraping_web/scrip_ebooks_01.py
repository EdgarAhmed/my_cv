#!/usr/bin/env python3
"""
Script de scraping para ebooks de MediaMarkt con actualización en Google Drive
EXACTLY matches the old notebook scraping logic
"""

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time
import os
import math
import re
import sys
import io
import json

# ============================================
# CONFIGURACIÓN DE GOOGLE DRIVE
# ============================================

def configurar_google_drive():
    """
    Configura y autentica con Google Drive usando credenciales de servicio
    """
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
        
        # Verificar si hay credenciales disponibles
        credenciales_json = os.environ.get('GOOGLE_CREDENTIALS_JSON')
        
        if not credenciales_json:
            print("⚠️  No se encontraron credenciales de Google Drive en variables de entorno")
            return None
        
        # Crear credenciales desde JSON string
        creds_dict = json.loads(credenciales_json)
        scopes = ['https://www.googleapis.com/auth/drive']
        
        credentials = service_account.Credentials.from_service_account_info(
            creds_dict, scopes=scopes
        )
        
        # Crear servicio de Google Drive
        service = build('drive', 'v3', credentials=credentials)
        
        print("✅ Google Drive configurado exitosamente")
        return service
        
    except ImportError:
        print("❌ Módulos de Google API no instalados. Instala: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
        return None
    except Exception as e:
        print(f"❌ Error configurando Google Drive: {e}")
        return None

def buscar_archivo_drive(service, nombre_archivo, folder_id):
    """
    Busca un archivo en Google Drive
    """
    try:
        query = f"name = '{nombre_archivo}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            fields="files(id, name, modifiedTime)"
        ).execute()
        
        files = results.get('files', [])
        return files[0] if files else None
        
    except Exception as e:
        print(f"❌ Error buscando archivo en Drive: {e}")
        return None

def descargar_archivo_drive(service, file_id):
    """
    Descarga un archivo de Google Drive
    """
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        return fh.getvalue().decode('utf-8')
        
    except Exception as e:
        print(f"❌ Error descargando archivo de Drive: {e}")
        return None

def subir_archivo_drive(service, nombre_archivo, contenido, folder_id, file_id=None):
    """
    Sube o actualiza un archivo en Google Drive
    """
    try:
        from googleapiclient.http import MediaIoBaseUpload
        
        file_metadata = {
            'name': nombre_archivo,
            'parents': [folder_id]
        }
        
        media = MediaIoBaseUpload(
            io.BytesIO(contenido.encode('utf-8')),
            mimetype='text/csv',
            resumable=True
        )
        
        if file_id:
            # Actualizar archivo existente
            archivo = service.files().update(
                fileId=file_id,
                media_body=media
            ).execute()
            print(f"✅ Archivo actualizado en Google Drive: {archivo.get('name')}")
        else:
            # Crear nuevo archivo
            archivo = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            print(f"✅ Nuevo archivo creado en Google Drive: {nombre_archivo}")
        
        return archivo
        
    except Exception as e:
        print(f"❌ Error subiendo archivo a Drive: {e}")
        return None

def actualizar_csv_drive(df_nuevo, folder_id="17jYoslfZdmPgvbO2JjEWazHmS4r79Lw7", nombre_archivo="ebooks_mediamarkt.csv"):
    """
    Actualiza un archivo CSV en Google Drive combinando datos existentes con nuevos
    """
    print("\n" + "="*60)
    print("ACTUALIZANDO GOOGLE DRIVE")
    print("="*60)
    
    # Configurar Google Drive
    service = configurar_google_drive()
    if not service:
        print("⚠️  Omitiendo actualización en Google Drive")
        return False
    
    try:
        # Buscar archivo existente
        archivo_existente = buscar_archivo_drive(service, nombre_archivo, folder_id)
        
        if archivo_existente:
            print(f"📁 Archivo encontrado en Drive: {archivo_existente['name']}")
            print(f"📅 Última modificación: {archivo_existente.get('modifiedTime', 'Desconocida')}")
            
            # Descargar archivo existente
            contenido_existente = descargar_archivo_drive(service, archivo_existente['id'])
            
            if contenido_existente:
                # Leer CSV existente
                df_existente = pd.read_csv(io.StringIO(contenido_existente))
                print(f"📊 Registros existentes en Drive: {len(df_existente)}")
                
                # Preparar nuevo DataFrame para combinación
                # Asegurar que las columnas coincidan
                columnas_comunes = list(set(df_existente.columns) & set(df_nuevo.columns))
                
                if columnas_comunes:
                    # Seleccionar solo columnas comunes
                    df_nuevo_compatible = df_nuevo[columnas_comunes]
                    df_existente_compatible = df_existente[columnas_comunes]
                    
                    # Combinar dataframes
                    df_combinado = pd.concat([df_existente_compatible, df_nuevo_compatible], ignore_index=True)
                    
                    # Eliminar duplicados (si los hay)
                    df_combinado = df_combinado.drop_duplicates(subset=['nombre', 'precio', 'fecha_extraccion'], keep='last')
                    
                    print(f"📈 Registros después de combinar: {len(df_combinado)}")
                    print(f"➕ Nuevos registros añadidos: {len(df_nuevo)}")
                else:
                    print("⚠️  No hay columnas comunes entre los DataFrames")
                    df_combinado = df_nuevo
            else:
                print("⚠️  No se pudo descargar el archivo existente, creando uno nuevo")
                df_combinado = df_nuevo
        else:
            print("📝 No se encontró archivo existente, creando uno nuevo")
            df_combinado = df_nuevo
        
        # Convertir DataFrame combinado a CSV
        csv_contenido = df_combinado.to_csv(index=False, encoding='utf-8')
        
        # Subir/actualizar archivo en Drive
        file_id = archivo_existente['id'] if archivo_existente else None
        archivo = subir_archivo_drive(service, nombre_archivo, csv_contenido, folder_id, file_id)
        
        if archivo:
            print(f"✅ Google Drive actualizado exitosamente")
            print(f"📊 Total de registros en archivo combinado: {len(df_combinado)}")
            return True
        else:
            print("❌ Error actualizando Google Drive")
            return False
            
    except Exception as e:
        print(f"❌ Error en el proceso de Google Drive: {e}")
        import traceback
        traceback.print_exc()
        return False

# ============================================
# FUNCIONES DE SCRAPING (EXACTLY like old notebook)
# ============================================

def setup_chrome_options():
    """Configura Chrome para ejecución headless (optimizado)"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    # Deshabilitar imágenes para acelerar
    prefs = {"profile.managed_default_content_settings.images": 2}
    chrome_options.add_experimental_option("prefs", prefs)
    
    return chrome_options

def mediamark_mob_(url):
    """Inicializa el navegador Chrome - EXACTLY like old notebook"""
    try:
        chrome_options = setup_chrome_options()
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get(url)
        # Removed maximize_window for headless
        time.sleep(2)

        # Aceptar cookies
        try:
            aceptar = driver.find_element(By.ID, "pwa-consent-layer-accept-all-button")
            aceptar.click()
            print("Cookies aceptadas")
        except Exception as e:
            print(f"Error aceptando cookies: {e}")

        time.sleep(3)
        
        return driver
        
    except Exception as e:
        print(f"❌ Error inicializando Chrome: {e}")
        raise

def obtener_total_articulos(driver):
    """
    Obtiene el número total de artículos del span y calcula las páginas necesarias
    EXACTLY like old notebook
    """
    try:
        # Buscar el elemento que contiene el total de artículos
        elemento_total = driver.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.AKpzk')
        texto_total = elemento_total.text
        
        # Extraer solo los números del texto (ej: "(3866 artículos)" -> 3866)
        numero_total = re.search(r'\((\d+)', texto_total)
        
        if numero_total:
            total_articulos = int(numero_total.group(1))
            print(f"📊 Total de artículos encontrados: {total_articulos}")
            
            # Calcular número de páginas necesarias (cada página muestra 12 productos)
            productos_por_pagina = 12
            total_paginas = math.ceil(total_articulos / productos_por_pagina)
            print(f"📄 Total de páginas a recorrer: {total_paginas}")
            
            return total_articulos, total_paginas
        else:
            print("❌ No se pudo extraer el número total de artículos")
            return None, 10  # Valor por defecto
    
    except Exception as e:
        print(f"❌ Error obteniendo el total de artículos: {e}")
        return None, 10  # Valor por defecto en caso de error

def extraer_precio_producto(contenedor_producto):
    """
    Función específica para extraer el precio correcto de un producto
    Prioriza el precio final sobre el precio original tachado
    EXACTLY like old notebook
    """
    try:
        # PRIMERO: Buscar precio final (rebajado) - span con clase dYbTef
        try:
            precio_final = contenedor_producto.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.dYbTef.sc-8a3a8cd8-2.csCDkt')
            return precio_final.text
        except:
            pass
        
        # SEGUNDO: Buscar precio normal - span con clase OhHlB
        try:
            precio_normal = contenedor_producto.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.OhHlB.sc-8a3a8cd8-2.csCDkt')
            return precio_normal.text
        except:
            pass
        
        # TERCERO: Buscar cualquier precio que contenga €
        try:
            elementos_precio = contenedor_producto.find_elements(By.XPATH, ".//*[contains(text(), '€')]")
            for elem in elementos_precio:
                texto = elem.text.strip()
                if '€' in texto and any(c.isdigit() for c in texto):
                    return texto
        except:
            pass
        
        return "Precio no disponible"
        
    except Exception as e:
        return f"Error: {e}"

def extraer_productos_pagina(driver):
    """
    Extrae los productos de una sola página
    EXACTLY like old notebook
    """
    productos_pagina = []
    
    try:
        # Buscar todos los títulos de productos en la página actual
        productos_titulos = driver.find_elements(By.CSS_SELECTOR, 'p[data-test="product-title"]')
        
        print(f"   🔍 Encontrados {len(productos_titulos)} productos en la página")
        
        # Para cada título, encontrar su contenedor y extraer información
        for i, titulo in enumerate(productos_titulos):
            try:
                # Encontrar el contenedor del producto
                contenedor = titulo
                for _ in range(5):
                    contenedor = contenedor.find_element(By.XPATH, "./..")
                    try:
                        precios = contenedor.find_elements(By.XPATH, ".//*[contains(text(), '€')]")
                        if precios:
                            break
                    except:
                        continue
                
                # Extraer nombre y precio
                nombre = titulo.text
                precio = extraer_precio_producto(contenedor)
                
                productos_pagina.append({
                    'nombre': nombre,
                    'precio': precio
                })
                
            except Exception as e:
                print(f"   ❌ Error extrayendo producto {i+1} de la página: {e}")
                continue
                
        return productos_pagina
        
    except Exception as e:
        print(f"❌ Error extrayendo productos de la página: {e}")
        return productos_pagina

def extraer_productos(driver):
    """
    Extrae todos los productos
    EXACTLY like old notebook - 5 sorting criteria, 30 pages each
    """
    # Lista para almacenar todos los productos
    productos_data = []
    contador_global = 1
    
    try:
        # OBTENER TOTAL DE ARTÍCULOS
        total_articulos, total_paginas = obtener_total_articulos(driver)
        
        print(f"🔄 Total de artículos: {total_articulos}")
        print(f"📄 Páginas calculadas: {total_paginas}")
        
        # Diferentes criterios de ordenación para obtener todos los productos
        criterios_ordenacion = [
            "currentprice+desc",    # Precio descendente
            "currentprice+asc",     # Precio ascendente  
            "relevance",            # Relevancia
            "name+asc",             # Nombre A-Z
            "name+desc"             # Nombre Z-A
        ]
        
        productos_unicos = set()
        
        for criterio in criterios_ordenacion:
            print(f"🎯 Usando criterio de ordenación: {criterio}")
            
            for pagina in range(1, 31):  # Máximo 30 páginas por criterio
                try:
                    print(f"📖 Página {pagina}/30 - Criterio: {criterio}")
                    
                    # URL de ebooks
                    url_pagina = f"https://www.mediamarkt.es/es/category/ebooks-249.html?sort={criterio}&page={pagina}"
                    
                    # Navegar a la página
                    driver.get(url_pagina)
                    
                    # Esperar a que cargue la página - EXACT timing
                    time.sleep(2)
                    
                    # Verificar que la página cargó correctamente
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'p[data-test="product-title"]'))
                        )
                    except:
                        print(f"❌ La página {pagina} no cargó correctamente, pasando a siguiente criterio")
                        break
                    
                    # Extraer productos de la página actual
                    productos_pagina = extraer_productos_pagina(driver)
                    
                    # Agregar solo productos nuevos
                    for producto in productos_pagina:
                        nombre_producto = producto['nombre']
                        if nombre_producto not in productos_unicos:
                            productos_unicos.add(nombre_producto)
                            producto['numero'] = contador_global
                            contador_global += 1
                            productos_data.append(producto)
                    
                    print(f"✅ Página {pagina}: {len(productos_pagina)} productos, Total únicos: {len(productos_data)}")
                    
                    # Si la página tiene menos de 12 productos, es la última
                    if len(productos_pagina) < 12:
                        print("📝 Última página detectada")
                        break
                        
                    # Pequeña pausa entre páginas - EXACT timing
                    time.sleep(1)
                    
                except Exception as e:
                    print(f"❌ Error en página {pagina}: {e}")
                    continue
        
        print(f"\n📊 Resumen final: {len(productos_data)} productos únicos de {len(criterios_ordenacion)} criterios")
        
        if total_articulos:
            porcentaje = (len(productos_data) / total_articulos) * 100
            print(f"📈 Se extrajo el {porcentaje:.1f}% del total de artículos")
        
        return productos_data
                
    except Exception as e:
        print(f"❌ Error extrayendo productos: {e}")
        return productos_data

def guardar_en_dataframe(productos_data):
    """
    Convierte la lista de productos en un DataFrame y lo guarda en CSV
    EXACTLY like old notebook
    """
    if not productos_data:
        print("No hay datos para guardar")
        return None
    
    # Crear DataFrame (ya vienen sin duplicados)
    df = pd.DataFrame(productos_data)
    
    # Añadir fecha y hora de extracción
    fecha_extraccion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df['fecha_extraccion'] = fecha_extraccion
    
    # Reordenar columnas
    column_order = ['fecha_extraccion', 'numero', 'nombre', 'precio']
    df = df[column_order]
    
    # Crear carpeta para resultados si no existe
    os.makedirs("scraping_results", exist_ok=True)
    
    # Nombre del archivo
    nombre_archivo = f"scraping_results/ebooks_mediamarkt_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = nombre_archivo
    df.to_csv(file_path, index=False, encoding='utf-8')
    
    print(f"\n✅ Datos guardados en: {file_path}")
    print(f"📊 Total de productos únicos: {len(df)}")
    
    # Mostrar resumen
    productos_con_precio = len(df[df['precio'].str.contains('€', na=False)])
    productos_sin_precio = len(df) - productos_con_precio
    
    print(f"💰 Productos con precio: {productos_con_precio}")
    print(f"❌ Productos sin precio: {productos_sin_precio}")
    
    # Mostrar primeras filas
    print("\n📋 Primeras 5 filas del DataFrame:")
    print(df.head())
    
    return df, file_path

# ============================================
# FUNCIÓN PRINCIPAL
# ============================================

def main():
    """Función principal"""
    print("="*60)
    print("SCRAPING DE EBOOKS - MEDIAMARKT")
    print("="*60)
    print(f"Fecha y hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60)
    
    driver = None
    
    try:
        # URL objetivo
        url = "https://www.mediamarkt.es/es/category/ebooks-249.html?sort=currentprice+desc"
        
        print(f"\n🌐 Accediendo a: {url}")
        
        # Paso 1: Inicializar navegador
        driver = mediamark_mob_(url)
        
        # Paso 2: Extraer productos (EXACTLY like old notebook)
        productos_data = extraer_productos(driver)
        
        if not productos_data:
            print("No se extrajeron productos")
            return False
        
        # Paso 3: Guardar en DataFrame
        df, archivo_csv = guardar_en_dataframe(productos_data)
        
        if df is None:
            print("❌ Error creando DataFrame. Terminando ejecución.")
            return False
        
        # Paso 4: Actualizar Google Drive con append
        print("\n🔄 Actualizando Google Drive...")
        drive_actualizado = actualizar_csv_drive(df)
        
        if drive_actualizado:
            print("✅ Google Drive actualizado exitosamente")
        else:
            print("⚠️  No se pudo actualizar Google Drive (puede ser falta de credenciales)")
        
        print("\n" + "="*60)
        print("RESUMEN EJECUCIÓN")
        print("="*60)
        print(f"✅ Scraping completado exitosamente")
        print(f"📦 Productos obtenidos: {len(df)}")
        print(f"📁 Archivo local generado: {archivo_csv}")
        
        return True
            
    except Exception as e:
        print(f"Error en la ejecución: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cerrar el navegador
        if driver:
            try:
                driver.quit()
                print("\n🛑 Navegador cerrado")
            except:
                pass
        
        print("\n" + "="*60)
        print("EJECUCIÓN FINALIZADA")
        print("="*60)

if __name__ == "__main__":
    # Ejecutar scraping
    success = main()
    
    # Salir con código apropiado para CI/CD
    sys.exit(0 if success else 1)
