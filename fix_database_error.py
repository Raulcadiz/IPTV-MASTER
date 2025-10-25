#!/usr/bin/env python3
"""
Script para corregir el error de SQLite database 
- Crear directorios necesarios
- Verificar permisos
- Configurar rutas absolutas
"""

import os
import sqlite3
import stat
from pathlib import Path

def fix_database_error():
    """Corrige el error de 'unable to open database file'"""
    
    # 1. Obtener directorio actual del proyecto
    project_dir = os.getcwd()
    print(f"📁 Directorio del proyecto: {project_dir}")
    
    # 2. Crear ruta absoluta para la base de datos
    data_dir = os.path.join(project_dir, 'data')
    db_path = os.path.join(data_dir, 'iptv_proxy.db')
    
    print(f"📁 Directorio de datos: {data_dir}")
    print(f"💾 Ruta de BD: {db_path}")
    
    # 3. Crear directorio con permisos correctos
    try:
        Path(data_dir).mkdir(parents=True, exist_ok=True)
        
        # Verificar y corregir permisos
        os.chmod(data_dir, stat.S_IRWXU | stat.S_IRWXG | stat.S_IROTH)
        print(f"✅ Directorio '{data_dir}' creado con permisos correctos")
        
    except PermissionError as e:
        print(f"❌ Error de permisos: {e}")
        print("💡 Ejecuta: sudo chown -R $USER:$USER .")
        return False
    
    # 4. Probar creación de base de datos
    try:
        # Crear conexión temporal para verificar
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()
        print(f"✅ Base de datos SQLite creada exitosamente en: {db_path}")
        
        # Eliminar tabla de prueba
        conn = sqlite3.connect(db_path)
        conn.execute("DROP TABLE IF EXISTS test_table")
        conn.commit()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error al crear la base de datos: {e}")
        return False
    
    # 5. Crear archivo de configuración corregido
    config_content = f'''
# Configuración corregida para evitar errores de SQLite
import os

class Config:
    """Configuración CORREGIDA - Rutas absolutas y manejo de errores"""
    
    # Directorio base del proyecto
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    
    # Ruta absoluta para la base de datos
    DATA_DIR = os.path.join(BASE_DIR, 'data')
    DATABASE_PATH = os.path.join(DATA_DIR, 'iptv_proxy.db')
    
    # URI corregida con ruta absoluta
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{DATABASE_PATH}'
    
    # Resto de configuración...
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tu-clave-super-secreta-cambiala-en-produccion'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
    PROXY_TIMEOUT = int(os.environ.get('PROXY_TIMEOUT', 15))
    VALIDATION_INTERVAL = int(os.environ.get('VALIDATION_INTERVAL', 300))
    RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', "100/hour")
    
    @staticmethod
    def init_directories():
        """Crear directorios necesarios con manejo de errores"""
        directories = [
            Config.DATA_DIR,
            os.path.join(Config.BASE_DIR, 'logs')
        ]
        
        for directory in directories:
            try:
                os.makedirs(directory, exist_ok=True)
                print(f"✅ Directorio creado: {directory}")
            except PermissionError:
                print(f"❌ Sin permisos para crear: {directory}")
                raise
            except Exception as e:
                print(f"❌ Error creando {directory}: {e}")
                raise

# Usar esta configuración en tu app
print(f"📍 Ruta de BD corregida: {Config.DATABASE_PATH}")
'''
    
    with open(os.path.join(project_dir, 'config_fixed.py'), 'w') as f:
        f.write(config_content.strip())
    
    print("📝 Archivo 'config_fixed.py' creado con configuración corregida")
    
    return True

def fix_iptv_proxy_file():
    """Corrige las líneas problemáticas en iptv_proxy_complete.py"""
    
    fixes = [
        {
            'line': 42,
            'old': "SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///data/iptv_proxy.db'",
            'new': "SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or f'sqlite:///{os.path.abspath(\"data/iptv_proxy.db\")}'"
        },
        {
            'line': 50,
            'old': "os.makedirs('data', exist_ok=True)",
            'new': """# Crear directorios con verificación de permisos
try:
    os.makedirs('data', exist_ok=True)
    os.makedirs('logs', exist_ok=True)
    # Verificar permisos de escritura
    test_file = 'data/.test_write'
    with open(test_file, 'w') as f:
        f.write('test')
    os.remove(test_file)
    print("✅ Directorios creados con permisos correctos")
except PermissionError:
    print("❌ Error: Sin permisos de escritura")
    print("💡 Ejecuta: sudo chown -R $USER:$USER .")
    sys.exit(1)
except Exception as e:
    print(f"❌ Error creando directorios: {e}")
    sys.exit(1)"""
        }
    ]
    
    print("\n🔧 Aplica estos cambios en tu archivo iptv_proxy_complete.py:")
    for fix in fixes:
        print(f"\n📍 Línea {fix['line']}:")
        print(f"❌ Cambiar: {fix['old']}")
        print(f"✅ Por: {fix['new']}")

if __name__ == '__main__':
    print("🔧 Solucionando error de SQLite database...")
    print("=" * 60)
    
    if fix_database_error():
        print("\n🎉 ¡Problema resuelto!")
        print("\n📋 PRÓXIMOS PASOS:")
        print("1. Ejecuta este script desde el directorio de tu proyecto")
        print("2. Aplica los cambios mostrados a continuación")
        print("3. Reinicia tu aplicación")
        
        fix_iptv_proxy_file()
        
    else:
        print("\n❌ No se pudo resolver automáticamente")
        print("💡 Revisa los permisos de directorio")
