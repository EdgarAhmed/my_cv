
"""
Script de scraping para ebooks de MediaMarkt
Basado en el notebook: 03_scraping_mediamark_ebooks.ipynb
"""

import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from datetime import datetime
import time
import os
import math
import re
import io
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive


## Scraping Ebooks

"""En este código se usa la paginación por URL para evitar problemas de carga"""

def mediamark_mob_(url):
    
    driver = webdriver.Chrome()
    driver.get(url)
    driver.maximize_window()
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

def obtener_total_articulos(driver):
    """
    Obtiene el número total de artículos del span y calcula las páginas necesarias
    """
    try:
        # Buscar el elemento que contiene el total de artículos
        elemento_total = driver.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.AKpzk')
        texto_total = elemento_total.text
        
        # Extraer solo los números del texto (ej: "(3866 artículos)" -> 3866)
        import re
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
                    
                    # CAMBIADO por -> URL de monitores en lugar de tablets
                    url_pagina = f"https://www.mediamarkt.es/es/category/ebooks-249.html?sort={criterio}&page={pagina}"
                    
                    # Navegar a la página
                    driver.get(url_pagina)
                    
                    # Esperar a que cargue la página
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
                        
                    # Pequeña pausa entre páginas
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
    
    # Obtener el directorio de inicio del usuario para guardar el archivo
    home_dir = os.path.expanduser("~")
    
    # Crear una carpeta para los datos si no existe
    data_dir = os.path.join(home_dir, "scraping_mediamarkt")
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
    
    # CAMBIADO por -> Nombre del archivo para monitores
    nombre_archivo = f"ebooks_mediamarkt_completo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    file_path = os.path.join(data_dir, nombre_archivo)
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


def main_scraping():
    """
    Función principal para ejecutar el scraping
    """
    # CAMBIADO por -> URL principal de monitores
    url = "https://www.mediamarkt.es/es/category/ebooks-249.html?sort=currentprice+desc"
    try:
        driver = mediamark_mob_(url)
        
        # Extraer productos (ahora devuelve una lista de diccionarios)
        productos_data = extraer_productos(driver)
        
        # Guardar en DataFrame y CSV
        if productos_data:
            df, file_path = guardar_en_dataframe(productos_data)
            return df
        else:
            print("No se extrajeron productos")
            return None
            
    except Exception as e:
        print(f"Error en la ejecución: {e}")
        return None
    finally:
        # Cerrar el navegador
        if 'driver' in locals():
            driver.quit()
            print("\n🛑 Navegador cerrado")


def procesar_dataframe(df):
    """
    Procesa el DataFrame: verifica duplicados, limpia precios, extrae marcas
    """
    if df is None or len(df) == 0:
        print("No hay datos para procesar")
        return None
    
    print("\n" + "="*50)
    print("PROCESANDO DATAFRAME")
    print("="*50)
    
    # Mostrar DataFrame inicial
    print(f"\nDataFrame inicial: {len(df)} registros")
    print(df.head())
    
    # Verificar duplicados
    print("\n🔍 Verificando duplicados...")
    duplicados = df[df['nombre'].duplicated(keep=False)]['nombre'].unique()
    print(f"Nombres duplicados encontrados: {len(duplicados)}")
    
    duplicados_df = df[df['nombre'].duplicated(keep=False)]
    if len(duplicados_df) > 0:
        print(f"Registros duplicados: {len(duplicados_df)}")
        print(duplicados_df.head())
    
    # Crear el nuevo nombre dinámico
    nuevo_nombre = "df_mediamark_ebooks_"
    
    # Asignar el DataFrame actual a la nueva variable
    globals()[nuevo_nombre] = df
    
    # Eliminar el original si ya no lo necesitas
    del df
    
    print(f"\n✅ DataFrame renombrado a: {nuevo_nombre}")
    
    # Obtener el DataFrame renombrado
    df_mediamark_ebooks_ = globals()[nuevo_nombre]
    
    print(f"Dimensiones: {df_mediamark_ebooks_.shape}")
    
    # Limpiar la columna precio con regex más eficiente
    print("\n🧹 Limpiando columna de precios...")
    df_mediamark_ebooks_['precio'] = (
        df_mediamark_ebooks_['precio']
        .astype(str)
        .str.replace(r'[^\d,]', '', regex=True)  # Eliminar todo excepto números y comas
        .str.replace(',', '.', regex=False)  # Convertir comas a puntos
    )
    
    # Convertir a float
    df_mediamark_ebooks_['precio'] = pd.to_numeric(
        df_mediamark_ebooks_['precio'], 
        errors='coerce'
    )
    
    print("✅ Columna precio limpiada exitosamente")
    print(df_mediamark_ebooks_['precio'].head())
    
    # Ordenar por precio
    df_mediamark_ebooks_ = df_mediamark_ebooks_.sort_values(by='precio', ascending=False)
    print("\n📊 DataFrame ordenado por precio (descendente)")
    
    # Extraer marcas de ebooks
    print("\n🏷️  Extrayendo marcas de ebooks...")
    
    marcas_ebooks = [
        'amazon', 'kindle', 'kobo', 'pocketbook', 'bq', 'tolino', 'onyx boox',
        'remarkable', 'sony', 'reader', 'nook', 'barnes noble', 'bookeen',
        'energy sistem', 'wolder', 'dingoo', 'artect', 'trekstor', 'iriver',
        'aluratek', 'emporia', 'hanvon', 'pandigital', 'velocity micro',
        'copia', 'foxit', 'ectaco', 'entourage', 'icarus', 'geniatech',
        'pocketbook', 'inkbook', 'fidibook', 'mediapress', 'vivitar',
        'supersonic', 'visual land', 'digma', 'texet', 'prestigio', 'ritmix',
        'odeon', 'maxvi', 'teclast', 'chuwi', 'cube', 'onda', 'aigo', 'newsmy',
        'wexler', 'ebw', 'bens', 'mustek', 'philips', 'lenovo', 'asus',
        'dell', 'hp', 'acer', 'samsung', 'lg', 'microsoft', 'apple'
    ]
    
    # Función para extraer la marca del ebook del nombre
    def extraer_marca_ebook(nombre):
        if pd.isna(nombre):
            return 'Desconocido'
        
        nombre_lower = str(nombre).lower()
        
        # Casos especiales que necesitan manejo específico
        if 'kindle' in nombre_lower:
            return 'Amazon'
        if 'kobo' in nombre_lower:
            return 'Kobo'
        if 'pocketbook' in nombre_lower:
            return 'PocketBook'
        if 'tolino' in nombre_lower:
            return 'Tolino'
        if 'onyx boox' in nombre_lower:
            return 'Onyx Boox'
        if 'remarkable' in nombre_lower:
            return 'ReMarkable'
        if 'nook' in nombre_lower or 'barnes noble' in nombre_lower:
            return 'Barnes & Noble'
        if 'bookeen' in nombre_lower:
            return 'Bookeen'
        if 'energy sistem' in nombre_lower:
            return 'Energy Sistem'
        if 'inkbook' in nombre_lower:
            return 'Inkbook'
        if 'fidibook' in nombre_lower:
            return 'Fidibook'
        
        # Buscar coincidencias exactas de marcas
        for marca in marcas_ebooks:
            # Buscar la marca como palabra completa para evitar falsos positivos
            if f' {marca} ' in f' {nombre_lower} ' or nombre_lower.startswith(marca + ' '):
                # Manejar nombres que deben ser capitalizados correctamente
                if marca in ['bq', 'kobo']:
                    return marca.upper()
                elif marca == 'kindle':
                    return 'Amazon'
                elif marca == 'pocketbook':
                    return 'PocketBook'
                elif marca == 'tolino':
                    return 'Tolino'
                elif marca == 'onyx boox':
                    return 'Onyx Boox'
                elif marca == 'remarkable':
                    return 'ReMarkable'
                elif marca in ['nook', 'barnes noble']:
                    return 'Barnes & Noble'
                elif marca == 'bookeen':
                    return 'Bookeen'
                elif marca == 'energy sistem':
                    return 'Energy Sistem'
                elif marca == 'inkbook':
                    return 'Inkbook'
                elif marca == 'fidibook':
                    return 'Fidibook'
                elif marca == 'bq':
                    return 'BQ'
                else:
                    return marca.title()  # Devuelve con la primera letra mayúscula
        
        return 'Otra marca'
    
    # Aplicar la función para crear la nueva columna
    df_mediamark_ebooks_['ebook_brand'] = df_mediamark_ebooks_['nombre'].apply(extraer_marca_ebook)
    
    print("✅ Marcas extraídas exitosamente")
    print(f"\nDistribución de marcas:")
    print(df_mediamark_ebooks_['ebook_brand'].value_counts().head(10))
    
    return df_mediamark_ebooks_


def subir_a_google_drive(df_mediamark_ebooks_):
    """
    Sube el DataFrame a Google Drive, combinándolo con datos existentes si los hay
    """
    if df_mediamark_ebooks_ is None or len(df_mediamark_ebooks_) == 0:
        print("No hay datos para subir a Google Drive")
        return
    
    print("\n" + "="*50)
    print("SUBIENDO A GOOGLE DRIVE")
    print("="*50)
    
    try:
        # --- Autenticación ---
        gauth = GoogleAuth()
        gauth.LocalWebserverAuth()  # Abre navegador para autenticación
        drive = GoogleDrive(gauth)
        
        # --- ID de la carpeta ---
        folder_id = "17jYoslfZdmPgvbO2JjEWazHmS4r79Lw7" 
        
        # --- Nombre fijo del CSV ---
        nombre_csv = "ebooks_mediamarkt.csv"
        
        # Buscar si el archivo ya existe en Google Drive
        file_list = drive.ListFile({'q': f"'{folder_id}' in parents and title='{nombre_csv}' and trashed=false"}).GetList()
        
        if file_list:
            # El archivo existe - descargarlo y anexar nuevos datos
            file_drive = file_list[0]
            
            try:
                # Intentar descargar como archivo CSV normal
                existing_content = file_drive.GetContentString()
                df_existing = pd.read_csv(io.StringIO(existing_content))
                
            except Exception as e:
                print(f"⚠️  No se pudo descargar como CSV, intentando exportar desde Google Sheets...")
                
                # El archivo es probablemente un Google Sheets, necesitamos exportarlo
                try:
                    # Exportar como CSV desde Google Sheets
                    export_url = file_drive['exportLinks']['text/csv']
                    existing_content = drive.auth.service.files().export_media(fileId=file_drive['id'], mimeType='text/csv').execute()
                    df_existing = pd.read_csv(io.BytesIO(existing_content))
                    print("✅ Archivo exportado exitosamente desde Google Sheets")
                    
                except Exception as export_error:
                    print(f"❌ Error exportando desde Google Sheets: {export_error}")
                    # Si no podemos exportar, crear un DataFrame vacío
                    df_existing = pd.DataFrame()
            
            # Añadir los nuevos datos al DataFrame existente (sin eliminar duplicados)
            df_combined = pd.concat([df_existing, df_mediamark_ebooks_], ignore_index=True)
            
            # Guardar el archivo combinado localmente temporalmente
            ruta_local = os.path.join("/tmp", nombre_csv)
            df_combined.to_csv(ruta_local, index=False)
            
            # Actualizar el archivo en Google Drive
            file_drive.SetContentFile(ruta_local)
            file_drive.Upload()
            
            print(f"✅ Datos anexados al archivo existente '{nombre_csv}'")
            print(f"📊 Total de registros históricos: {len(df_combined)}")
            print(f"📈 Se añadieron {len(df_mediamark_ebooks_)} nuevos registros")
            print(f"📅 Rango de fechas: {df_combined['fecha_extraccion'].min()} a {df_combined['fecha_extraccion'].max()}")
            
        else:
            # El archivo no existe - crear uno nuevo
            ruta_local = os.path.join("/tmp", nombre_csv)
            df_mediamark_ebooks_.to_csv(ruta_local, index=False)
            
            # Subir nuevo CSV a la carpeta específica
            file_drive = drive.CreateFile({'title': nombre_csv, 'parents': [{'id': folder_id}]})
            file_drive.SetContentFile(ruta_local)
            file_drive.Upload()
            
            print(f"✅ Nuevo archivo creado en Google Drive: '{nombre_csv}'")
            print(f"📊 Registros iniciales: {len(df_mediamark_ebooks_)}")
        
        # Limpiar archivo temporal si existe
        try:
            if os.path.exists(ruta_local):
                os.remove(ruta_local)
        except:
            pass
        
        # Mostrar resumen de productos únicos por fecha
        if 'df_combined' in locals():
            productos_por_fecha = df_combined.groupby('fecha_extraccion').size()
            print(f"\n📅 Registros por fecha:")
            for fecha, cantidad in productos_por_fecha.items():
                print(f"   {fecha}: {cantidad} registros")
                
    except Exception as e:
        print(f"❌ Error al subir a Google Drive: {e}")
        print("Nota: La autenticación de Google Drive requiere navegador web.")
        print("Para entornos sin GUI (como servidores), configura las credenciales de servicio.")


def main():
    """
    Función principal que ejecuta todo el flujo
    """
    print("="*60)
    print("SCRAPING DE EBOOKS - MEDIAMARKT")
    print("="*60)
    
    # Paso 1: Ejecutar scraping
    df = main_scraping()
    
    if df is not None:
        # Paso 2: Procesar DataFrame
        df_procesado = procesar_dataframe(df)
        
        if df_procesado is not None:
            # Paso 3: Subir a Google Drive
            # Nota: Comentar esta línea si no quieres subir a Google Drive
            subir_a_google_drive(df_procesado)
            
            # Mostrar resumen final
            print("\n" + "="*60)
            print("RESUMEN FINAL")
            print("="*60)
            print(f"✅ Scraping completado exitosamente")
            print(f"📊 Total de productos únicos: {len(df_procesado)}")
            print(f"💰 Precio promedio: {df_procesado['precio'].mean():.2f}€")
            print(f"📈 Precio máximo: {df_procesado['precio'].max():.2f}€")
            print(f"📉 Precio mínimo: {df_procesado['precio'].min():.2f}€")
            
            # Guardar archivo local final
            nombre_final = f"ebooks_mediamarkt_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            df_procesado.to_csv(nombre_final, index=False, encoding='utf-8')
            print(f"💾 Archivo final guardado como: {nombre_final}")
    
    print("\n" + "="*60)
    print("PROCESO COMPLETADO")
    print("="*60)


if __name__ == "__main__":
    main()