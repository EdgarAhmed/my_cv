#!/usr/bin/env python3
"""
Script de scraping para ebooks de MediaMarkt
Basado en el notebook: 03_scraping_mediamark_ebooks.ipynb

Para usar en GitHub Actions:
1. Guarda este archivo en scraping_web/scrip_ebooks_01.py
2. Actualiza el workflow para ejecutar este script en lugar del notebook
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

# Configuración para entorno headless (GitHub Actions)
def setup_chrome_options():
    """Configura Chrome para ejecución headless"""
    chrome_options = Options()
    
    # Opciones para entorno sin display (headless)
    chrome_options.add_argument("--headless")  # Ejecutar sin interfaz gráfica
    chrome_options.add_argument("--no-sandbox")  # Necesario para CI/CD
    chrome_options.add_argument("--disable-dev-shm-usage")  # Para limitaciones de memoria
    chrome_options.add_argument("--disable-gpu")  # Deshabilitar GPU
    chrome_options.add_argument("--window-size=1920,1080")  # Tamaño de ventana fijo
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Deshabilitar imágenes para acelerar
    prefs = {
        "profile.managed_default_content_settings.images": 2,  # No cargar imágenes
        "profile.default_content_setting_values.notifications": 2  # Deshabilitar notificaciones
    }
    chrome_options.add_experimental_option("prefs", prefs)
    
    return chrome_options

def mediamark_mob_(url):
    """Inicializa el navegador Chrome"""
    try:
        # Configurar opciones de Chrome
        chrome_options = setup_chrome_options()
        
        # Usar webdriver-manager para manejar ChromeDriver automáticamente
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        driver.get(url)
        time.sleep(3)  # Esperar inicial

        # Aceptar cookies si existe el botón
        try:
            aceptar = driver.find_element(By.ID, "pwa-consent-layer-accept-all-button")
            aceptar.click()
            print("✅ Cookies aceptadas")
            time.sleep(1)
        except:
            print("ℹ️ No se encontró botón de cookies o ya estaban aceptadas")

        return driver
        
    except Exception as e:
        print(f"❌ Error inicializando Chrome: {e}")
        # Intentar método alternativo
        try:
            driver = webdriver.Chrome(options=setup_chrome_options())
            driver.get(url)
            time.sleep(3)
            return driver
        except Exception as e2:
            print(f"❌ Error alternativo: {e2}")
            raise

def obtener_total_articulos(driver):
    """
    Obtiene el número total de artículos del span y calcula las páginas necesarias
    """
    try:
        # Esperar a que cargue el elemento
        time.sleep(2)
        
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
    """
    try:
        # PRIMERO: Buscar precio final (rebajado) - span con clase dYbTef
        try:
            precio_final = contenedor_producto.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.dYbTef.sc-8a3a8cd8-2.csCDkt')
            return precio_final.text.strip()
        except:
            pass
        
        # SEGUNDO: Buscar precio normal - span con clase OhHlB
        try:
            precio_normal = contenedor_producto.find_element(By.CSS_SELECTOR, 'span.sc-94eb08bc-0.OhHlB.sc-8a3a8cd8-2.csCDkt')
            return precio_normal.text.strip()
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
        # Esperar a que carguen los productos
        time.sleep(2)
        
        # Buscar todos los títulos de productos en la página actual
        productos_titulos = driver.find_elements(By.CSS_SELECTOR, 'p[data-test="product-title"]')
        
        if not productos_titulos:
            print("   ⚠️ No se encontraron productos en la página")
            return productos_pagina
            
        print(f"   🔍 Encontrados {len(productos_titulos)} productos en la página")
        
        # Para cada título, encontrar su contenedor y extraer información
        for i, titulo in enumerate(productos_titulos[:12]):  # Máximo 12 por página
            try:
                # Encontrar el contenedor del producto
                contenedor = titulo
                for _ in range(5):
                    try:
                        contenedor = contenedor.find_element(By.XPATH, "./..")
                        precios = contenedor.find_elements(By.XPATH, ".//*[contains(text(), '€')]")
                        if precios:
                            break
                    except:
                        continue
                
                # Extraer nombre y precio
                nombre = titulo.text.strip()
                if not nombre:  # Si el nombre está vacío, saltar
                    continue
                    
                precio = extraer_precio_producto(contenedor)
                
                productos_pagina.append({
                    'nombre': nombre,
                    'precio': precio
                })
                
            except Exception as e:
                print(f"   ⚠️ Error extrayendo producto {i+1}: {str(e)[:50]}...")
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
        print("\n🔄 Obteniendo información del catálogo...")
        total_articulos, total_paginas = obtener_total_articulos(driver)
        
        # Limitar páginas para pruebas (comentar para producción)
        # total_paginas = min(total_paginas, 5)
        
        print(f"📄 Páginas calculadas: {total_paginas}")
        
        # Diferentes criterios de ordenación para obtener productos variados
        criterios_ordenacion = [
            "currentprice+desc",    # Precio descendente
            "relevance",            # Relevancia
        ]
        
        productos_unicos = set()
        paginas_procesadas = 0
        
        for criterio in criterios_ordenacion:
            print(f"\n🎯 Usando criterio de ordenación: {criterio}")
            
            for pagina in range(1, min(total_paginas, 6) + 1):  # Máximo 5 páginas por criterio
                try:
                    print(f"📖 Página {pagina}/{min(total_paginas, 5)} - Criterio: {criterio}")
                    
                    # Construir URL
                    url_pagina = f"https://www.mediamarkt.es/es/category/ebooks-249.html?sort={criterio}&page={pagina}"
                    
                    # Navegar a la página
                    driver.get(url_pagina)
                    
                    # Esperar a que cargue la página
                    time.sleep(3)
                    
                    # Verificar que la página cargó correctamente
                    try:
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, 'p[data-test="product-title"]'))
                        )
                    except:
                        print(f"❌ La página {pagina} no cargó correctamente")
                        break
                    
                    # Extraer productos de la página actual
                    productos_pagina = extraer_productos_pagina(driver)
                    
                    # Agregar solo productos nuevos
                    productos_nuevos = 0
                    for producto in productos_pagina:
                        nombre_producto = producto['nombre']
                        if nombre_producto and nombre_producto not in productos_unicos:
                            productos_unicos.add(nombre_producto)
                            producto['numero'] = contador_global
                            contador_global += 1
                            productos_data.append(producto)
                            productos_nuevos += 1
                    
                    print(f"✅ Página {pagina}: {len(productos_pagina)} productos, Nuevos: {productos_nuevos}, Total únicos: {len(productos_data)}")
                    
                    paginas_procesadas += 1
                    
                    # Si la página tiene menos de 6 productos, es la última
                    if len(productos_pagina) < 6:
                        print("📝 Última página detectada")
                        break
                        
                    # Pequeña pausa entre páginas
                    time.sleep(2)
                    
                    # Limitar páginas procesadas para no exceder tiempo
                    if paginas_procesadas >= 8:  # Máximo 8 páginas total
                        print("⚠️  Límite de páginas alcanzado")
                        break
                        
                except Exception as e:
                    print(f"❌ Error en página {pagina}: {e}")
                    continue
            
            if paginas_procesadas >= 8:
                break
        
        print(f"\n📊 Resumen final: {len(productos_data)} productos únicos")
        
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
        print("❌ No hay datos para guardar")
        return None
    
    try:
        # Crear DataFrame
        df = pd.DataFrame(productos_data)
        
        # Añadir fecha y hora de extracción
        fecha_extraccion = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        df['fecha_extraccion'] = fecha_extraccion
        
        # Reordenar columnas
        column_order = ['fecha_extraccion', 'numero', 'nombre', 'precio']
        df = df[column_order]
        
        # Crear carpeta para resultados si no existe
        os.makedirs("scraping_results", exist_ok=True)
        
        # Nombre del archivo con timestamp
        nombre_archivo = f"scraping_results/ebooks_mediamarkt_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(nombre_archivo, index=False, encoding='utf-8')
        
        print(f"\n✅ Datos guardados en: {nombre_archivo}")
        print(f"📊 Total de productos únicos: {len(df)}")
        
        # Estadísticas
        productos_con_precio = len(df[df['precio'].str.contains('€|\\d', na=False, regex=True)])
        productos_sin_precio = len(df) - productos_con_precio
        
        print(f"💰 Productos con precio: {productos_con_precio}")
        print(f"❌ Productos sin precio: {productos_sin_precio}")
        
        # Mostrar primeras filas
        print("\n📋 Primeras 5 filas del DataFrame:")
        print(df.head())
        
        return df, nombre_archivo
        
    except Exception as e:
        print(f"❌ Error guardando DataFrame: {e}")
        return None, None

def procesar_dataframe(df):
    """
    Procesa el DataFrame: limpia precios, extrae marcas
    """
    if df is None or len(df) == 0:
        print("❌ No hay datos para procesar")
        return None
    
    try:
        print("\n" + "="*50)
        print("PROCESANDO DATAFRAME")
        print("="*50)
        
        # Limpiar la columna precio
        print("\n🧹 Limpiando precios...")
        df['precio_limpio'] = (
            df['precio']
            .astype(str)
            .str.replace(r'[^\d,]', '', regex=True)
            .str.replace(',', '.', regex=False)
        )
        
        # Convertir a numérico
        df['precio_numerico'] = pd.to_numeric(df['precio_limpio'], errors='coerce')
        
        # Extraer marcas
        print("🏷️  Extrayendo marcas...")
        
        marcas_ebooks = [
            'amazon', 'kindle', 'kobo', 'pocketbook', 'bq', 'tolino', 'onyx boox',
            'remarkable', 'sony', 'reader', 'nook', 'barnes noble', 'bookeen',
            'energy sistem', 'wolder', 'dingoo', 'artect', 'trekstor'
        ]
        
        def extraer_marca_ebook(nombre):
            if pd.isna(nombre):
                return 'Desconocido'
            
            nombre_lower = str(nombre).lower()
            
            # Casos especiales
            if 'kindle' in nombre_lower:
                return 'Amazon Kindle'
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
            if 'nook' in nombre_lower:
                return 'Barnes & Noble Nook'
            
            # Búsqueda general
            for marca in marcas_ebooks:
                if marca in nombre_lower:
                    return marca.title()
            
            return 'Otra marca'
        
        df['marca'] = df['nombre'].apply(extraer_marca_ebook)
        
        # Ordenar por precio
        df = df.sort_values(by='precio_numerico', ascending=False)
        
        print("✅ Procesamiento completado")
        print(f"\n📊 Distribución de marcas:")
        print(df['marca'].value_counts().head(10))
        
        return df
        
    except Exception as e:
        print(f"❌ Error procesando DataFrame: {e}")
        return df

def guardar_resultado_final(df):
    """
    Guarda el DataFrame procesado en un archivo final
    """
    if df is None or len(df) == 0:
        return None
    
    try:
        # Nombre del archivo final
        nombre_final = f"scraping_results/ebooks_mediamarkt_final_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        
        # Seleccionar columnas importantes
        columnas_finales = ['fecha_extraccion', 'numero', 'nombre', 'precio', 'precio_numerico', 'marca']
        columnas_disponibles = [col for col in columnas_finales if col in df.columns]
        
        df_final = df[columnas_disponibles]
        df_final.to_csv(nombre_final, index=False, encoding='utf-8')
        
        print(f"\n💾 Archivo final guardado: {nombre_final}")
        print(f"📊 Total registros: {len(df_final)}")
        print(f"💰 Precio promedio: {df_final['precio_numerico'].mean():.2f}€")
        print(f"📈 Precio máximo: {df_final['precio_numerico'].max():.2f}€")
        print(f"📉 Precio mínimo: {df_final['precio_numerico'].min():.2f}€")
        
        return nombre_final
        
    except Exception as e:
        print(f"❌ Error guardando archivo final: {e}")
        return None

def subir_a_google_drive(df_mediamark_ebooks_):
    """
    Intenta subir el DataFrame a Google Drive, pero omite si no hay autenticación disponible
    """
    # Verificar si estamos en un entorno sin GUI (como GitHub Actions)
    if os.environ.get('SKIP_GOOGLE_DRIVE') == 'true' or not os.environ.get('DISPLAY'):
        print("⚠️  Omitiendo subida a Google Drive (entorno sin GUI/CI/CD)")
        return
    
    try:
        from pydrive.auth import GoogleAuth
        from pydrive.drive import GoogleDrive
        
        print("\n" + "="*50)
        print("INTENTANDO SUBIR A GOOGLE DRIVE")
        print("="*50)
        
        # --- Autenticación ---
        gauth = GoogleAuth()
        
        # En CI/CD no hay navegador, así que omitimos
        print("ℹ️  La autenticación de Google Drive requiere navegador")
        print("ℹ️  En CI/CD, configura credenciales de servicio")
        print("ℹ️  Omitiendo subida a Google Drive por ahora")
        
        return
        
    except ImportError:
        print("⚠️  Módulo pydrive no disponible. Omitiendo Google Drive.")
    except Exception as e:
        print(f"⚠️  Error con Google Drive: {e}")
        print("ℹ️  Continuando sin subir a Google Drive")

def main():
    """
    Función principal que ejecuta todo el flujo de scraping
    """
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
        
        # Paso 2: Extraer productos
        productos_data = extraer_productos(driver)
        
        if not productos_data:
            print("❌ No se extrajeron productos. Terminando ejecución.")
            return False
        
        # Paso 3: Guardar en DataFrame
        df, archivo_csv = guardar_en_dataframe(productos_data)
        
        if df is None:
            print("❌ Error creando DataFrame. Terminando ejecución.")
            return False
        
        # Paso 4: Procesar DataFrame
        df_procesado = procesar_dataframe(df)
        
        # Paso 5: Intentar subir a Google Drive (omite automáticamente en CI/CD)
        subir_a_google_drive(df_procesado)
        
        # Paso 6: Guardar resultado final
        if df_procesado is not None:
            archivo_final = guardar_resultado_final(df_procesado)
            
            # Crear resumen
            print("\n" + "="*60)
            print("RESUMEN EJECUCIÓN")
            print("="*60)
            print(f"✅ Scraping completado exitosamente")
            print(f"📦 Productos obtenidos: {len(df_procesado)}")
            print(f"📁 Archivos generados:")
            print(f"   - {archivo_csv}")
            if archivo_final:
                print(f"   - {archivo_final}")
            
            return True
            
        else:
            print("❌ Error procesando datos")
            return False
            
    except Exception as e:
        print(f"\n❌ ERROR CRÍTICO: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cerrar navegador
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
