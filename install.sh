#!/bin/bash

# Script de instalación y configuración de IPTV Multi-Proxy
# Versión Profesional

set -e

echo "=========================================="
echo "🚀 IPTV Multi-Proxy - Instalación"
echo "=========================================="

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Función para logging
log() {
    echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')] $1${NC}"
}

warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Verificar Python
log "Verificando Python..."
if ! command -v python3 &> /dev/null; then
    error "Python 3 no está instalado. Por favor instala Python 3.8 o superior."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
log "Python version: $PYTHON_VERSION"

# Verificar pip
if ! command -v pip3 &> /dev/null; then
    error "pip3 no está instalado. Instalando..."
    sudo apt-get update
    sudo apt-get install -y python3-pip
fi

# Crear directorios necesarios
log "Creando estructura de directorios..."
mkdir -p data
mkdir -p logs
mkdir -p config
mkdir -p static/css
mkdir -p static/js
mkdir -p templates/auth
mkdir -p templates/admin
mkdir -p templates/main

# Crear entorno virtual
log "Creando entorno virtual..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    log "Entorno virtual creado"
else
    log "Entorno virtual ya existe"
fi

# Activar entorno virtual
log "Activando entorno virtual..."
source venv/bin/activate

# Actualizar pip
log "Actualizando pip..."
pip install --upgrade pip

# Instalar dependencias
log "Instalando dependencias..."
pip install -r requirements.txt

# Crear archivo de configuración
log "Creando archivo de configuración..."
cat > config/config.py << EOF
import os
from datetime import timedelta

class Config:
    """Configuración base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or '$(openssl rand -hex 32)'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///data/iptv_proxy.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de proxies
    MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
    PROXY_TIMEOUT = int(os.environ.get('PROXY_TIMEOUT', 15))
    VALIDATION_INTERVAL = int(os.environ.get('VALIDATION_INTERVAL', 300))  # 5 minutos
    
    # Rate limiting
    RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', "100/hour")
    
    # Configuración de sesiones
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    
    # Configuración de logging
    LOG_LEVEL = os.environ.get('LOG_LEVEL', 'INFO')
    LOG_FILE = os.environ.get('LOG_FILE', 'logs/iptv_proxy.log')
    
class DevelopmentConfig(Config):
    """Configuración de desarrollo"""
    DEBUG = True
    SQLALCHEMY_ECHO = False

class ProductionConfig(Config):
    """Configuración de producción"""
    DEBUG = False
    SQLALCHEMY_ECHO = False
    
    # Configuración más estricta para producción
    RATE_LIMIT_DEFAULT = "50/hour"
    PROXY_TIMEOUT = 10

class TestingConfig(Config):
    """Configuración de testing"""
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///data/test.db'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
EOF

# Crear archivo .env de ejemplo
log "Creando archivo de variables de entorno..."
cat > .env.example << EOF
# Configuración de la aplicación
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///data/iptv_proxy.db
FLASK_ENV=development

# Configuración de proxies
MAX_RETRIES=3
PROXY_TIMEOUT=15
VALIDATION_INTERVAL=300

# Rate limiting
RATE_LIMIT_DEFAULT=100/hour

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/iptv_proxy.log

# Puerto del servidor
PORT=5051
HOST=0.0.0.0
EOF

# Copiar .env si no existe
if [ ! -f ".env" ]; then
    cp .env.example .env
    log "Archivo .env creado. Puedes editarlo para personalizar la configuración."
fi

# Crear script de inicio
log "Creando script de inicio..."
cat > start.sh << EOF
#!/bin/bash

# Script de inicio de IPTV Multi-Proxy

# Activar entorno virtual
source venv/bin/activate

# Cargar variables de entorno
if [ -f .env ]; then
    export \$(cat .env | grep -v '#' | xargs)
fi

# Mostrar información
echo "=========================================="
echo "🚀 Iniciando IPTV Multi-Proxy..."
echo "=========================================="
echo "🌐 Servidor: http://\${HOST:-0.0.0.0}:\${PORT:-5051}"
echo "👤 Usuario Admin: admin / admin123"
echo "👤 Usuario Demo: demo / demo123"
echo "=========================================="

# Ejecutar aplicación
python3 iptv_proxy_complete.py
EOF

chmod +x start.sh

# Crear script de desarrollo
log "Creando script de desarrollo..."
cat > dev.sh << EOF
#!/bin/bash

# Script de desarrollo con auto-reload

source venv/bin/activate

if [ -f .env ]; then
    export \$(cat .env | grep -v '#' | xargs)
fi

export FLASK_ENV=development
export FLASK_DEBUG=1

python3 iptv_proxy_complete.py
EOF

chmod +x dev.sh

# Crear script de producción con gunicorn
log "Creando script de producción..."
cat > production.sh << EOF
#!/bin/bash

# Script de producción con Gunicorn

source venv/bin/activate

if [ -f .env ]; then
    export \$(cat .env | grep -v '#' | xargs)
fi

export FLASK_ENV=production

# Crear archivo wsgi.py si no existe
if [ ! -f wsgi.py ]; then
    cat > wsgi.py << WSGI_EOF
from iptv_proxy_complete import app

if __name__ == "__main__":
    app.run()
WSGI_EOF
fi

# Ejecutar con Gunicorn
gunicorn --bind \${HOST:-0.0.0.0}:\${PORT:-5051} \\
         --workers 4 \\
         --worker-class gthread \\
         --threads 2 \\
         --timeout 30 \\
         --keep-alive 2 \\
         --max-requests 1000 \\
         --max-requests-jitter 50 \\
         --access-logfile logs/access.log \\
         --error-logfile logs/error.log \\
         --log-level info \\
         wsgi:app
EOF

chmod +x production.sh

# Crear service file para systemd
log "Creando archivo de servicio systemd..."
cat > iptv-proxy.service << EOF
[Unit]
Description=IPTV Multi-Proxy Service
After=network.target

[Service]
Type=exec
User=\$(whoami)
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin
ExecStart=$(pwd)/production.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Crear script de instalación del servicio
cat > install-service.sh << EOF
#!/bin/bash

# Script para instalar el servicio systemd

if [ "\$EUID" -ne 0 ]; then
    echo "Por favor ejecuta como root: sudo ./install-service.sh"
    exit 1
fi

cp iptv-proxy.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable iptv-proxy
systemctl start iptv-proxy

echo "Servicio instalado y iniciado"
echo "Para ver el estado: systemctl status iptv-proxy"
echo "Para ver logs: journalctl -u iptv-proxy -f"
EOF

chmod +x install-service.sh

# Crear Dockerfile
log "Creando Dockerfile..."
cat > Dockerfile << EOF
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \\
    gcc \\
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Crear directorios necesarios
RUN mkdir -p data logs

# Exponer puerto
EXPOSE 5051

# Comando por defecto
CMD ["python3", "iptv_proxy_complete.py"]
EOF

# Crear docker-compose.yml
log "Creando docker-compose.yml..."
cat > docker-compose.yml << EOF
version: '3.8'

services:
  iptv-proxy:
    build: .
    ports:
      - "5051:5051"
    volumes:
      - ./data:/app/data
      - ./logs:/app/logs
    environment:
      - SECRET_KEY=your-secret-key-here
      - DATABASE_URL=sqlite:///data/iptv_proxy.db
      - FLASK_ENV=production
    restart: unless-stopped
    
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    restart: unless-stopped
    
volumes:
  data:
  logs:
EOF

# Crear archivo de backup
log "Creando script de backup..."
cat > backup.sh << EOF
#!/bin/bash

# Script de backup de IPTV Multi-Proxy

BACKUP_DIR="backups"
DATE=\$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="iptv_proxy_backup_\${DATE}.tar.gz"

mkdir -p \$BACKUP_DIR

echo "Creando backup..."

tar -czf \$BACKUP_DIR/\$BACKUP_FILE \\
    data/ \\
    logs/ \\
    config/ \\
    .env \\
    iptv_proxy_complete.py \\
    requirements.txt

echo "Backup creado: \$BACKUP_DIR/\$BACKUP_FILE"

# Mantener solo los últimos 7 backups
find \$BACKUP_DIR -name "iptv_proxy_backup_*.tar.gz" -mtime +7 -delete

echo "Backups antiguos eliminados"
EOF

chmod +x backup.sh

# Crear script de update
log "Creando script de actualización..."
cat > update.sh << EOF
#!/bin/bash

# Script de actualización de IPTV Multi-Proxy

echo "Actualizando IPTV Multi-Proxy..."

# Crear backup antes de actualizar
./backup.sh

# Activar entorno virtual
source venv/bin/activate

# Actualizar pip y dependencias
pip install --upgrade pip
pip install -r requirements.txt --upgrade

echo "Actualización completada"
echo "Reinicia el servicio para aplicar los cambios"
EOF

chmod +x update.sh

# Crear README con instrucciones
log "Creando documentación..."
cat > README.md << EOF
# IPTV Multi-Proxy - Versión Profesional

Sistema avanzado de gestión de proxies e IPTV con interfaz de administración completa.

## 🚀 Características

- ✅ Panel de administración web responsive
- ✅ Gestión completa de usuarios (estándar, premium, admin)
- ✅ Sistema inteligente de proxies con balanceeo de carga
- ✅ Monitoreo automático y estadísticas en tiempo real
- ✅ Soporte para múltiples fuentes M3U
- ✅ Rate limiting y seguridad avanzada
- ✅ API REST completa
- ✅ Logs profesionales y debugging
- ✅ Configuración via archivos de entorno
- ✅ Soporte para Docker y systemd

## 📋 Requisitos

- Python 3.8 o superior
- 2GB RAM mínimo
- 10GB espacio en disco
- Conexión a internet estable

## 🛠️ Instalación

1. **Instalación automática:**
   \`\`\`bash
   chmod +x install.sh
   ./install.sh
   \`\`\`

2. **Inicio del servicio:**
   \`\`\`bash
   ./start.sh
   \`\`\`

3. **Acceder a la interfaz:**
   - URL: http://localhost:5051
   - Admin: admin / admin123
   - Demo: demo / demo123

## 🔧 Configuración

Edita el archivo \`.env\` para personalizar la configuración:

\`\`\`bash
cp .env.example .env
nano .env
\`\`\`

## 🐳 Docker

\`\`\`bash
docker-compose up -d
\`\`\`

## 🔄 Servicios del Sistema

Para instalar como servicio systemd:

\`\`\`bash
sudo ./install-service.sh
\`\`\`

## 📊 Monitoreo

- Logs: \`tail -f logs/iptv_proxy.log\`
- Estado: \`systemctl status iptv-proxy\`
- Métricas: http://localhost:5051/api/status

## 🔐 Seguridad

- Cambia las contraseñas por defecto
- Configura HTTPS en producción
- Usa un SECRET_KEY fuerte
- Configura firewall apropiadamente

## 📞 Soporte

Para soporte técnico, revisa los logs y verifica la configuración.
EOF

# Establecer permisos
log "Configurando permisos..."
chmod 755 data logs config
chmod 644 requirements.txt .env.example
chmod 600 .env 2>/dev/null || true

log "=========================================="
log "✅ Instalación completada exitosamente!"
log "=========================================="
log ""
log "📋 Próximos pasos:"
log "1. Edita .env para personalizar la configuración"
log "2. Ejecuta: ./start.sh para iniciar el servidor"
log "3. Accede a: http://localhost:5051"
log "4. Usuario admin: admin / admin123"
log "5. Usuario demo: demo / demo123"
log ""
log "📚 Scripts disponibles:"
log "• ./start.sh          - Iniciar servidor"
log "• ./dev.sh            - Modo desarrollo"
log "• ./production.sh     - Modo producción"
log "• ./backup.sh         - Crear backup"
log "• ./update.sh         - Actualizar sistema"
log ""
log "🐳 Docker:"
log "• docker-compose up -d"
log ""
log "🔧 Servicio del sistema:"
log "• sudo ./install-service.sh"
log ""
warn "⚠️  IMPORTANTE: Cambia las contraseñas por defecto antes de usar en producción"
log ""
log "=========================================="
