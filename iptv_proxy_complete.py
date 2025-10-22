#!/usr/bin/env python3
"""
IPTV Multi-Proxy Service - Versión Profesional Integrada
Sistema completo de gestión de proxies e IPTV con interfaz de administración
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, jsonify, request, redirect, url_for, session, flash, Response, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import threading
import time
import json
import requests
from typing import List, Dict, Optional, Tuple
import re
from urllib.parse import urlparse

# Configuración de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/iptv_proxy.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Crear directorio de logs si no existe
os.makedirs('logs', exist_ok=True)

class Config:
    """Configuración centralizada de la aplicación"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'tu-clave-super-secreta-cambiala-en-produccion'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///data/iptv_proxy.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    MAX_RETRIES = int(os.environ.get('MAX_RETRIES', 3))
    PROXY_TIMEOUT = int(os.environ.get('PROXY_TIMEOUT', 15))
    VALIDATION_INTERVAL = int(os.environ.get('VALIDATION_INTERVAL', 300))  # 5 minutos
    RATE_LIMIT_DEFAULT = os.environ.get('RATE_LIMIT_DEFAULT', "100/hour")

# Crear directorio de datos si no existe
os.makedirs('data', exist_ok=True)

# Inicialización de la aplicación
app = Flask(__name__)
app.config.from_object(Config)

# Extensiones
db = SQLAlchemy(app)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=[Config.RATE_LIMIT_DEFAULT]
)

# ============================================================================
# MODELOS DE BASE DE DATOS
# ============================================================================

class User(db.Model):
    """Modelo de usuario con diferentes niveles de acceso"""
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(120), nullable=False)
    is_premium = db.Column(db.Boolean, default=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    usage_count = db.Column(db.Integer, default=0)
    bandwidth_used = db.Column(db.BigInteger, default=0)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def to_dict(self):
        return {
            'id': self.id,
            'username': self.username,
            'is_premium': self.is_premium,
            'is_admin': self.is_admin,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'usage_count': self.usage_count,
            'bandwidth_used': self.bandwidth_used
        }

class Proxy(db.Model):
    """Modelo de proxy con estadísticas y monitoreo"""
    id = db.Column(db.Integer, primary_key=True)
    host = db.Column(db.String(255), nullable=False, index=True)
    port = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(100), nullable=True)
    password = db.Column(db.String(100), nullable=True)
    proxy_type = db.Column(db.String(20), default='http')
    is_active = db.Column(db.Boolean, default=True)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    last_checked = db.Column(db.DateTime)
    response_time = db.Column(db.Float, default=0.0)
    status_message = db.Column(db.String(255), default='Sin verificar')
    priority = db.Column(db.Integer, default=5)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def success_rate(self):
        total = self.success_count + self.failure_count
        return (self.success_count / total * 100) if total > 0 else 0

    @property
    def has_auth(self):
        return bool(self.username and self.password)

    def to_dict(self):
        return {
            'id': self.id,
            'host': self.host,
            'port': self.port,
            'has_auth': self.has_auth,
            'proxy_type': self.proxy_type,
            'is_active': self.is_active,
            'success_rate': self.success_rate,
            'success_count': self.success_count,
            'failure_count': self.failure_count,
            'last_checked': self.last_checked.isoformat() if self.last_checked else None,
            'response_time': self.response_time,
            'status_message': self.status_message,
            'priority': self.priority
        }

class M3USource(db.Model):
    """Modelo para múltiples fuentes M3U"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    last_updated = db.Column(db.DateTime)
    channels_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(50), default='pending')
    error_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'is_active': self.is_active,
            'last_updated': self.last_updated.isoformat() if self.last_updated else None,
            'channels_count': self.channels_count,
            'status': self.status,
            'error_message': self.error_message
        }

class Channel(db.Model):
    """Modelo de canal con múltiples URLs de respaldo"""
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False, index=True)
    group_title = db.Column(db.String(100))
    logo = db.Column(db.String(500))
    m3u_source_id = db.Column(db.Integer, db.ForeignKey('m3u_source.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    urls = db.relationship('ChannelURL', backref='channel', lazy='dynamic', cascade='all, delete-orphan')

class ChannelURL(db.Model):
    """URLs de canal con estadísticas de uso"""
    id = db.Column(db.Integer, primary_key=True)
    channel_id = db.Column(db.Integer, db.ForeignKey('channel.id'), nullable=False)
    url = db.Column(db.String(500), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    success_count = db.Column(db.Integer, default=0)
    failure_count = db.Column(db.Integer, default=0)
    last_used = db.Column(db.DateTime)
    response_time = db.Column(db.Float, default=0.0)
    priority = db.Column(db.Integer, default=5)

    @property
    def success_rate(self):
        total = self.success_count + self.failure_count
        return (self.success_count / total * 100) if total > 0 else 100

class AccessLog(db.Model):
    """Log de accesos para estadísticas"""
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ip_address = db.Column(db.String(45), nullable=False)
    channel_name = db.Column(db.String(200))
    url_accessed = db.Column(db.String(500))
    proxy_used = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    response_time = db.Column(db.Float)
    success = db.Column(db.Boolean, default=True)

# ============================================================================
# GESTOR DE PROXIES
# ============================================================================

class ProxyManager:
    """Gestor inteligente de proxies con balanceeo de carga"""
    
    def __init__(self):
        self.validation_thread = None
        self.running = False
    
    def start_monitoring(self):
        """Inicia el monitoreo automático de proxies"""
        if self.validation_thread and self.validation_thread.is_alive():
            return
        
        self.running = True
        self.validation_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.validation_thread.start()
        logger.info("Monitor de proxies iniciado")
    
    def stop_monitoring(self):
        """Detiene el monitoreo"""
        self.running = False
        if self.validation_thread:
            self.validation_thread.join(timeout=5)
    
    def _monitor_loop(self):
        """Loop principal de monitoreo"""
        while self.running:
            try:
                with app.app_context():
                    self.validate_all_proxies()
                time.sleep(Config.VALIDATION_INTERVAL)
            except Exception as e:
                logger.error(f"Error en el monitoreo de proxies: {e}")
                time.sleep(60)
    
    def validate_all_proxies(self):
        """Valida todos los proxies activos"""
        proxies = Proxy.query.filter_by(is_active=True).all()
        logger.info(f"Validando {len(proxies)} proxies...")
        
        for proxy in proxies:
            success, response_time, message = self._test_proxy(proxy)
            
            if success:
                proxy.success_count += 1
                proxy.status_message = "✅ Funcionando"
            else:
                proxy.failure_count += 1
                proxy.status_message = f"❌ {message}"
            
            proxy.response_time = response_time
            proxy.last_checked = datetime.utcnow()
            
            if proxy.success_rate < 10 and (proxy.success_count + proxy.failure_count) > 10:
                proxy.is_active = False
                logger.warning(f"Proxy {proxy.host}:{proxy.port} desactivado por baja tasa de éxito")
        
        db.session.commit()
        logger.info("Validación de proxies completada")
    
    def _test_proxy(self, proxy: Proxy) -> Tuple[bool, float, str]:
        """Prueba un proxy individual"""
        test_url = "https://httpbin.org/ip"
        proxy_url = f"{proxy.proxy_type}://"
        
        if proxy.has_auth:
            proxy_url += f"{proxy.username}:{proxy.password}@"
        
        proxy_url += f"{proxy.host}:{proxy.port}"
        
        start_time = time.time()
        
        try:
            response = requests.get(
                test_url,
                proxies={proxy.proxy_type: proxy_url},
                timeout=Config.PROXY_TIMEOUT,
                verify=False
            )
            
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                return True, response_time, "OK"
            else:
                return False, response_time, f"HTTP {response.status_code}"
                
        except requests.exceptions.Timeout:
            return False, Config.PROXY_TIMEOUT, "Timeout"
        except requests.exceptions.ConnectionError:
            return False, time.time() - start_time, "Conexión fallida"
        except Exception as e:
            return False, time.time() - start_time, str(e)[:100]
    
    def get_best_proxy(self, user: User = None) -> Optional[Proxy]:
        """Obtiene el mejor proxy disponible"""
        query = Proxy.query.filter_by(is_active=True)
        
        if user and not user.is_premium:
            query = query.filter(Proxy.username.is_(None))
        
        proxies = query.order_by(
            Proxy.priority.desc(),
            (Proxy.success_count / (Proxy.success_count + Proxy.failure_count + 1)).desc(),
            Proxy.response_time.asc()
        ).all()
        
        return proxies[0] if proxies else None

# Instancia global del gestor de proxies
proxy_manager = ProxyManager()

# ============================================================================
# DECORADORES Y UTILIDADES
# ============================================================================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Acceso denegado. Se requieren privilegios de administrador.', 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_user() -> Optional[User]:
    """Obtiene el usuario actual de la sesión"""
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def authenticate_api_user(username: str, password: str) -> Optional[User]:
    """Autentica usuario para API"""
    user = User.query.filter_by(username=username, is_active=True).first()
    if user and user.check_password(password):
        user.last_login = datetime.utcnow()
        user.usage_count += 1
        db.session.commit()
        return user
    return None

# ============================================================================
# RUTAS PRINCIPALES
# ============================================================================

@app.route('/')
def index():
    """Página principal"""
    current_user = get_current_user()
    if current_user:
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Página de login"""
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        
        if not username or not password:
            flash('Usuario y contraseña son requeridos', 'error')
            return render_template('login.html')
        
        user = User.query.filter_by(username=username, is_active=True).first()
        
        if user and user.check_password(password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            logger.info(f"Usuario {username} inició sesión desde {request.remote_addr}")
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            return redirect(url_for('dashboard'))
        else:
            flash('Credenciales inválidas', 'error')
            logger.warning(f"Intento de login fallido para {username} desde {request.remote_addr}")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Cerrar sesión"""
    username = session.get('username', 'Usuario desconocido')
    session.clear()
    flash('Sesión cerrada exitosamente', 'success')
    logger.info(f"Usuario {username} cerró sesión")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Dashboard principal del usuario"""
    current_user = get_current_user()
    
    user_stats = {
        'usage_count': current_user.usage_count,
        'bandwidth_used': current_user.bandwidth_used,
        'is_premium': current_user.is_premium,
        'last_login': current_user.last_login
    }
    
    general_stats = {}
    if current_user.is_admin:
        general_stats = {
            'total_users': User.query.filter_by(is_active=True).count(),
            'total_proxies': Proxy.query.filter_by(is_active=True).count(),
            'total_channels': Channel.query.count(),
            'recent_accesses': AccessLog.query.filter(
                AccessLog.timestamp > datetime.utcnow() - timedelta(hours=24)
            ).count()
        }
    
    return render_template('dashboard.html', 
                         user_stats=user_stats, 
                         general_stats=general_stats)

# ============================================================================
# RUTAS DE IPTV
# ============================================================================

@app.route('/play')
@limiter.limit("30/minute")
def redirect_iptv():
    """Redirección principal de IPTV"""
    user = request.args.get('user')
    pwd = request.args.get('pwd')
    channel = request.args.get('channel')
    
    if not channel or not user or not pwd:
        logger.warning(f"Parámetros faltantes en /play desde {request.remote_addr}")
        return "Error: Canal no definido o credenciales faltantes", 400
    
    authenticated_user = authenticate_api_user(user, pwd)
    if not authenticated_user:
        logger.warning(f"Autenticación fallida para {user} desde {request.remote_addr}")
        return "Error: Credenciales inválidas", 401
    
    # Buscar canal (implementación simplificada)
    best_url = find_best_channel_url(channel, authenticated_user)
    if not best_url:
        logger.warning(f"Canal {channel} no encontrado")
        return "Error: Canal no encontrado", 404
    
    # Registrar acceso
    log_access(authenticated_user, channel, best_url)
    
    logger.info(f"Redirigiendo canal {channel} para usuario {user}")
    
    response = make_response("", 302)
    response.headers["Location"] = best_url
    return response

@app.route('/list')
@limiter.limit("10/minute")
def get_iptv():
    """Generar lista M3U personalizada"""
    user = request.args.get('user')
    pwd = request.args.get('pwd')
    
    if not user or not pwd:
        return "Error: Credenciales requeridas", 400
    
    authenticated_user = authenticate_api_user(user, pwd)
    if not authenticated_user:
        return "Error: Credenciales inválidas", 401
    
    m3u_content = generate_m3u_for_user(authenticated_user)
    
    response = Response(
        m3u_content,
        mimetype='application/octet-stream',
        headers={
            'Content-Disposition': f'attachment; filename=iptv_{user}.m3u'
        }
    )
    
    logger.info(f"Lista M3U generada para usuario {user}")
    return response

@app.route('/api/status')
def api_status():
    """Estado general del sistema"""
    active_proxies = Proxy.query.filter_by(is_active=True).count()
    total_channels = Channel.query.count()
    active_sources = M3USource.query.filter_by(is_active=True).count()
    
    return jsonify({
        'status': 'online',
        'active_proxies': active_proxies,
        'total_channels': total_channels,
        'active_sources': active_sources,
        'timestamp': datetime.utcnow().isoformat()
    })

# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def find_best_channel_url(channel_name: str, user: User) -> str:
    """Encuentra la mejor URL para un canal (implementación simplificada)"""
    # En un sistema real, esto buscaría en la base de datos
    # Por ahora devolvemos una URL de ejemplo
    return f"https://example.com/stream/{channel_name}.m3u8"

def generate_m3u_for_user(user: User) -> str:
    """Genera contenido M3U personalizado para un usuario"""
    m3u_lines = ["#EXTM3U"]
    
    # Ejemplo de canales
    sample_channels = [
        {"name": "Canal 1", "group": "Nacionales"},
        {"name": "Canal 2", "group": "Nacionales"},
        {"name": "Movie Channel", "group": "Películas"},
        {"name": "Sports HD", "group": "Deportes"}
    ]
    
    for channel in sample_channels:
        extinf = f"#EXTINF:-1 group-title=\"{channel['group']}\",{channel['name']}"
        play_url = f"http://{request.host}/play?user={user.username}&pwd=dummy&channel={channel['name']}"
        
        m3u_lines.extend([extinf, play_url])
    
    return '\n'.join(m3u_lines)

def log_access(user: User, channel_name: str, url: str, proxy: Proxy = None):
    """Registra un acceso para estadísticas"""
    try:
        access_log = AccessLog(
            user_id=user.id,
            ip_address=request.remote_addr,
            channel_name=channel_name,
            url_accessed=url,
            proxy_used=f"{proxy.host}:{proxy.port}" if proxy else "direct",
            timestamp=datetime.utcnow(),
            success=True
        )
        
        db.session.add(access_log)
        user.usage_count += 1
        db.session.commit()
        
    except Exception as e:
        logger.error(f"Error al registrar acceso: {e}")
        db.session.rollback()

# ============================================================================
# TEMPLATES EMBEBIDOS (Para simplificar el deployment)
# ============================================================================

@app.route('/login.html')
def serve_login_template():
    """Template de login embebido"""
    return '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Login - IPTV Multi-Proxy</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
</head>
<body class="bg-light">
    <div class="container">
        <div class="row justify-content-center align-items-center min-vh-100">
            <div class="col-md-6 col-lg-4">
                <div class="card shadow">
                    <div class="card-header bg-primary text-white text-center">
                        <h4><i class="bi bi-shield-lock me-2"></i>IPTV Multi-Proxy</h4>
                    </div>
                    <div class="card-body">
                        {% with messages = get_flashed_messages(with_categories=true) %}
                            {% if messages %}
                                {% for category, message in messages %}
                                    <div class="alert alert-{{ 'danger' if category == 'error' else category }}">{{ message }}</div>
                                {% endfor %}
                            {% endif %}
                        {% endwith %}
                        
                        <form method="POST">
                            <div class="mb-3">
                                <label for="username" class="form-label">Usuario</label>
                                <input type="text" class="form-control" id="username" name="username" required>
                            </div>
                            <div class="mb-3">
                                <label for="password" class="form-label">Contraseña</label>
                                <input type="password" class="form-control" id="password" name="password" required>
                            </div>
                            <button type="submit" class="btn btn-primary w-100">Iniciar Sesión</button>
                        </form>
                    </div>
                </div>
            </div>
        </div>
    </div>
</body>
</html>
    '''

# Función para renderizar templates (simplificada)
def render_template(template_name, **kwargs):
    """Renderizar templates de forma simplificada"""
    if template_name == 'login.html':
        return serve_login_template()
    elif template_name == 'dashboard.html':
        return f'''
<!DOCTYPE html>
<html>
<head>
    <title>Dashboard - IPTV Multi-Proxy</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-dark bg-dark">
        <div class="container">
            <span class="navbar-brand">IPTV Multi-Proxy - Dashboard</span>
            <a href="/logout" class="btn btn-outline-light">Cerrar Sesión</a>
        </div>
    </nav>
    
    <div class="container mt-4">
        <h1>Bienvenido, {session.get('username', 'Usuario')}</h1>
        
        <div class="row mt-4">
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Uso Total</h5>
                        <p class="card-text display-6">{kwargs.get('user_stats', {}).get('usage_count', 0)}</p>
                    </div>
                </div>
            </div>
            
            <div class="col-md-3">
                <div class="card text-center">
                    <div class="card-body">
                        <h5 class="card-title">Tipo de Cuenta</h5>
                        <p class="card-text">
                            <span class="badge bg-{'warning' if session.get('is_admin') else 'success' if kwargs.get('user_stats', {}).get('is_premium') else 'secondary'}">
                                {'Admin' if session.get('is_admin') else 'Premium' if kwargs.get('user_stats', {}).get('is_premium') else 'Estándar'}
                            </span>
                        </p>
                    </div>
                </div>
            </div>
        </div>
        
        <div class="mt-4">
            <h3>Acciones Rápidas</h3>
            <div class="btn-group" role="group">
                <button class="btn btn-primary" onclick="downloadM3U()">Descargar Lista M3U</button>
                <button class="btn btn-success" onclick="checkStatus()">Ver Estado</button>
            </div>
        </div>
    </div>
    
    <script>
        function downloadM3U() {{
            window.location.href = '/list?user={session.get('username')}&pwd=dummy';
        }}
        
        function checkStatus() {{
            fetch('/api/status')
                .then(response => response.json())
                .then(data => alert('Proxies activos: ' + data.active_proxies + '\\nCanales: ' + data.total_channels));
        }}
    </script>
</body>
</html>
        '''
    
    return f"<h1>Template {template_name} no encontrado</h1>"

# ============================================================================
# INICIALIZACIÓN Y EJECUCIÓN
# ============================================================================

def initialize_database():
    """Inicializar base de datos con datos de ejemplo"""
    with app.app_context():
        db.create_all()
        
        # Crear usuario admin por defecto
        admin = User.query.filter_by(username='admin').first()
        if not admin:
            admin = User(
                username='admin',
                is_admin=True,
                is_premium=True,
                is_active=True
            )
            admin.set_password('admin123')
            db.session.add(admin)
        
        # Crear usuario de prueba
        user = User.query.filter_by(username='demo').first()
        if not user:
            user = User(
                username='demo',
                is_premium=False,
                is_admin=False,
                is_active=True
            )
            user.set_password('demo123')
            db.session.add(user)
        
        # Agregar proxies de ejemplo
        if Proxy.query.count() == 0:
            sample_proxies = [
                Proxy(host='147.75.113.227', port=8080, proxy_type='http', priority=7),
                Proxy(host='95.216.64.229', port=3128, proxy_type='http', priority=6),
                Proxy(host='proxy.example.com', port=8080, username='user', password='pass', proxy_type='http', priority=8)
            ]
            
            for proxy in sample_proxies:
                db.session.add(proxy)
        
        # Agregar fuente M3U de ejemplo
        if M3USource.query.count() == 0:
            source = M3USource(
                name='Lista de Ejemplo',
                url='https://example.com/playlist.m3u',
                is_active=True,
                status='success',
                channels_count=4
            )
            db.session.add(source)
        
        db.session.commit()
        logger.info("Base de datos inicializada con datos de ejemplo")

if __name__ == '__main__':
    # Inicializar base de datos
    initialize_database()
    
    # Iniciar monitoreo de proxies
    proxy_manager.start_monitoring()
    
    # Mostrar información de inicio
    print("=" * 60)
    print("🚀 IPTV Multi-Proxy Service - Versión Profesional")
    print("=" * 60)
    print(f"📡 Servidor iniciado en: http://localhost:5051")
    print(f"👤 Usuario Admin: admin / admin123")
    print(f"👤 Usuario Demo: demo / demo123")
    print(f"📋 Lista M3U: http://localhost:5051/list?user=demo&pwd=demo123")
    print("=" * 60)
    
    try:
        app.run(host='0.0.0.0', port=5051, debug=False, threaded=True)
    finally:
        proxy_manager.stop_monitoring()
        logger.info("Servidor detenido")
