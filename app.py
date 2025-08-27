from flask import Flask, render_template, redirect, url_for, session, request, flash, jsonify
from functools import wraps
import os
from datetime import datetime
from models import db, Mesa, Usuario, TurnoHistorial, TurnoGeneral
from flask_migrate import Migrate

app = Flask(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    #DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
    DATABASE_URL = DATABASE_URL.replace("postgres://","postgressql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///turnero.db'

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change')
app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'

db.init_app(app)
migrate = Migrate(app, db)

ultimo_turno_avanzado = None

def obtener_proximo_turno():
    ultimo_turno = TurnoGeneral.query.order_by(TurnoGeneral.numero_turno.desc()).first()
    if ultimo_turno:
        return ultimo_turno.numero_turno + 1
    return 1

def obtener_proximo_numero_mesa():
    ultima_mesa = Mesa.query.filter_by(eliminada=False).order_by(Mesa.numero.desc()).first()
    if ultima_mesa:
        return ultima_mesa.numero + 1
    
    mesas = Mesa.query.filter_by(eliminada=False).order_by(Mesa.numero).all()
    numeros_existentes = [mesa.numero for mesa in mesas]
    
    for i in range(1, 1000): 
        if i not in numeros_existentes:
            return i
    
    return 1

def reordenar_mesas():
    """Reordenar las mesas para que tengan números consecutivos (solo las no eliminadas)"""
    try:
        mesas = Mesa.query.filter_by(eliminada=False).order_by(Mesa.numero).all()
        
        for index, mesa in enumerate(mesas, start=1):
            mesa.numero = index
        
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        print(f"Error reordenando mesas: {e}")
        return False

def docente_ya_asignado(docente_id):
    """Verificar si un docente ya está asignado a otra mesa activa"""
    if not docente_id:
        return False
    
    mesa_asignada = Mesa.query.filter_by(
        docente_id=docente_id, 
        activa=True, 
        eliminada=False
    ).first()
    
    return mesa_asignada is not None

@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session:
            flash('Debes iniciar sesión para acceder a esta página', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session or session['usuario'].get('rol') != 'admin':
            flash('No tienes permisos para acceder a esta página', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def docente_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'usuario' not in session or session['usuario'].get('rol') != 'docente':
            flash('No tienes permisos para acceder a esta página', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def inicializar_base_datos():
    with app.app_context():
        db.create_all()
        
        if not Usuario.query.first():
            admin = Usuario(
                nombre="Administrador Principal",
                email="admin@turnero.com",
                password="admin123",
                rol="admin"
            )
            db.session.add(admin)
            
            docente = Usuario(
                nombre="Docente Ejemplo",
                email="docente@turnero.com",
                password="docente123",
                rol="docente"
            )
            db.session.add(docente)
            
            mesa1 = Mesa(numero=1, turno_actual=0, activa=True, eliminada=False)
            mesa2 = Mesa(numero=2, turno_actual=0, activa=True, eliminada=False)
            mesa3 = Mesa(numero=3, turno_actual=0, activa=False, eliminada=False)
            
            db.session.add_all([mesa1, mesa2, mesa3])
            db.session.commit()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        usuario = Usuario.query.filter_by(email=email, password=password, activo=True).first()
        
        if usuario:
            session['usuario'] = {
                'id': usuario.id,
                'nombre': usuario.nombre,
                'email': usuario.email,
                'rol': usuario.rol
            }
            session.modified = True
            
            flash(f'¡Bienvenido {usuario.nombre}!', 'success')
            
            if usuario.rol == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif usuario.rol == 'docente':
                return redirect(url_for('docente_dashboard'))
        else:
            flash('Credenciales incorrectas. Intenta nuevamente.', 'danger')
    
    return render_template('auth/login.html')

@app.route('/logout')
def logout():
    session.pop('usuario', None)
    flash('Sesión cerrada correctamente', 'info')
    return redirect(url_for('index'))

@app.route('/admin/dashboard')
@login_required
@admin_required
def admin_dashboard():
    usuarios = Usuario.query.filter_by(activo=True).all()
    mesas = Mesa.query.filter_by(eliminada=False).all()  
    
    # Obtener información completa de los docentes para cada mesa
    mesas_con_docente = []
    for mesa in mesas:
        mesa_dict = mesa.to_dict()
        if mesa.docente_id:
            docente = Usuario.query.get(mesa.docente_id)
            mesa_dict['docente_nombre'] = docente.nombre if docente else 'Sin asignar'
        else:
            mesa_dict['docente_nombre'] = 'Sin asignar'
        mesas_con_docente.append(mesa_dict)
    
    mesas_activas = Mesa.query.filter_by(activa=True, eliminada=False).all() 
    ultimo_turno = TurnoGeneral.query.order_by(TurnoGeneral.numero_turno.desc()).first()
    
    proximo_turno = obtener_proximo_turno()
    
    total_turnos = TurnoGeneral.query.count()
    
    ultimos_turnos = TurnoGeneral.query.order_by(
        TurnoGeneral.numero_turno.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html', 
                         usuarios=[u.to_dict() for u in usuarios],
                         mesas=mesas_con_docente,
                         mesas_activas=mesas_activas,
                         ultimo_turno=ultimo_turno,
                         proximo_turno=proximo_turno,
                         total_turnos=total_turnos,
                         ultimos_turnos=ultimos_turnos)

@app.route('/admin/mesas')
@login_required
@admin_required
def admin_mesas():
    mesas = Mesa.query.filter_by(eliminada=False).all()  
    docentes = Usuario.query.filter_by(rol='docente', activo=True).all()
    
    for docente in docentes:
        docente_dict = docente.to_dict()
        docente_dict['asignado'] = docente_ya_asignado(docente.id)
    
    return render_template('admin/mesas.html', 
                         mesas=[m.to_dict() for m in mesas],
                         docentes=[d.to_dict() for d in docentes])

@app.route('/admin/usuarios')
@login_required
@admin_required
def admin_usuarios():
    usuarios = Usuario.query.filter_by(activo=True).all()
    mesas = Mesa.query.filter_by(eliminada=False).all() 
    return render_template('admin/usuarios.html', 
                         usuarios=[u.to_dict() for u in usuarios],
                         mesas=[m.to_dict() for m in mesas])

@app.route('/docente/dashboard')
@login_required
@docente_required
def docente_dashboard():
    if 'usuario' not in session:
        return redirect(url_for('login'))
    
    usuario_actual = session['usuario']
    
    usuario = Usuario.query.get(usuario_actual['id'])
    
    if not usuario:
        flash('Usuario no encontrado', 'danger')
        return redirect(url_for('logout'))
    
    mesa = None
    mesa_asignada = Mesa.query.filter_by(docente_id=usuario.id, eliminada=False).first()
    if mesa_asignada:
        mesa = mesa_asignada
    
    ultimos_turnos = []
    if mesa:
        ultimos_turnos = TurnoGeneral.query.filter_by(mesa_id=mesa.id)\
            .order_by(TurnoGeneral.numero_turno.desc())\
            .limit(5)\
            .all()
    
    return render_template('docente/dashboard.html', 
                         mesa=mesa.to_dict() if mesa else None,
                         usuario=usuario.to_dict(),
                         ultimos_turnos=ultimos_turnos)

@app.route('/public/turnos')
def public_turnos():
    mesas = Mesa.query.filter_by(activa=True, eliminada=False).all() 
    ultimo_turno = TurnoGeneral.query.order_by(TurnoGeneral.numero_turno.desc()).first()
    
    return render_template('public/turnos.html',
                         mesas=[m.to_dict() for m in mesas],
                         ultimo_turno=ultimo_turno)

@app.route('/api/estado_sistema')
def api_estado_sistema():
    try:
        mesas = Mesa.query.filter_by(eliminada=False).all()
        mesas_data = []
        
        for mesa in mesas:
            docente_nombre = 'Sin asignar'
            if hasattr(mesa, 'docente') and mesa.docente:
                docente_nombre = mesa.docente.nombre
            
            mesas_data.append({
                'id': mesa.id,
                'numero': mesa.numero,
                'activa': mesa.activa,
                'turno_actual': mesa.turno_actual,
                'docente': docente_nombre
            })
        
        proximo_turno = obtener_proximo_turno()
    
        ultimos_turnos = TurnoGeneral.query.order_by(
            TurnoGeneral.numero_turno.desc()
        ).limit(10).all()
        
        ultimos_turnos_data = []
        for turno in ultimos_turnos:
            mesa_numero = turno.mesa.numero if turno.mesa else 'N/A'
            ultimos_turnos_data.append({
                'numero': turno.numero_turno,
                'mesa': mesa_numero,
                'docente': turno.docente,
                'timestamp': turno.timestamp.strftime("%H:%M:%S"),
                'estado': turno.estado
            })
        
        return jsonify({
            'success': True,
            'proximo_turno': proximo_turno,
            'mesas': mesas_data,
            'ultimos_turnos': ultimos_turnos_data,
            'total_turnos': TurnoGeneral.query.count(),
            'timestamp': datetime.now().strftime("%H:%M:%S")
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error al obtener estado: {str(e)}'
        })

@app.route('/api/ultimo_turno')
def api_ultimo_turno():
    ultimo_turno = TurnoGeneral.query.order_by(TurnoGeneral.numero_turno.desc()).first()
    
    if not ultimo_turno:
        return jsonify({
            'success': True, 
            'ultimo_turno': {
                'turno': 0,
                'mesa_numero': 0,
                'docente': 'Sistema',
                'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'mensaje': 'Esperando primer turno...'
            }
        })
    
    mesa_numero = ultimo_turno.mesa.numero if ultimo_turno.mesa else 0
    
    return jsonify({
        'success': True, 
        'ultimo_turno': {
            'turno': ultimo_turno.numero_turno,
            'mesa_numero': mesa_numero,
            'docente': ultimo_turno.docente,
            'timestamp': ultimo_turno.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            'mensaje': f'Turno {ultimo_turno.numero_turno} - Mesa {mesa_numero}'
        }
    })

@app.route('/api/siguiente_turno/<int:mesa_id>', methods=['POST'])
@login_required
def siguiente_turno(mesa_id):
    global ultimo_turno_avanzado
    
    mesa = Mesa.query.get(mesa_id)
    if not mesa or not mesa.activa or mesa.eliminada: 
        return jsonify({'success': False, 'error': 'Mesa no encontrada, inactiva o eliminada'})
    
    docente_nombre = 'Sin asignar'
    if hasattr(mesa, 'docente') and mesa.docente:
        docente_nombre = mesa.docente.nombre
    
    numero_turno = obtener_proximo_turno()

    nuevo_turno = TurnoGeneral(
        numero_turno=numero_turno,
        estado='atendiendo',
        mesa_id=mesa_id,
        docente=docente_nombre
    )
    db.session.add(nuevo_turno)
    
    mesa.turno_actual = numero_turno
    
    historial = TurnoHistorial(
        mesa_id=mesa_id,
        turno=numero_turno,
        docente=docente_nombre,
        accion='avance'
    )
    db.session.add(historial)
    
    ultimo_turno_avanzado = {
        'turno': numero_turno,
        'mesa_numero': mesa.numero,
        'mesa_id': mesa_id,
        'docente': docente_nombre,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'mensaje': f'Turno {numero_turno} - Mesa {mesa.numero}'
    }
    
    db.session.commit()
    
    return jsonify({
        'success': True, 
        'nuevo_turno': numero_turno,
        'mensaje': f'Turno {numero_turno} asignado a Mesa {mesa.numero}'
    })

@app.route('/api/asignar_docente_mesa', methods=['POST'])
@login_required
@admin_required
def asignar_docente_mesa():
    data = request.get_json()
    mesa_id = data.get('mesa_id')
    docente_id = data.get('docente_id')
    
    mesa = Mesa.query.get(mesa_id)
    docente = Usuario.query.get(docente_id)
    
    if not mesa or mesa.eliminada or not docente or docente.rol != 'docente':  
        return jsonify({'success': False, 'error': 'No se pudo realizar la asignación'})
    
    if docente_ya_asignado(docente_id):
        mesa_existente = Mesa.query.filter_by(
            docente_id=docente_id, 
            activa=True, 
            eliminada=False
        ).first()
        return jsonify({
            'success': False, 
            'error': f'El docente {docente.nombre} ya está asignado a la Mesa {mesa_existente.numero}'
        })

    mesa.docente_id = docente_id
    db.session.commit()
    
    return jsonify({'success': True, 'docente': docente.nombre})

@app.route('/api/activar_mesa/<int:mesa_id>', methods=['POST'])
@login_required
@admin_required
def activar_mesa(mesa_id):
    mesa = Mesa.query.get(mesa_id)
    if not mesa or mesa.eliminada:  
        return jsonify({'success': False, 'error': 'Mesa no encontrada o eliminada'})
    
    mesa.activa = not mesa.activa
    db.session.commit()
    
    return jsonify({'success': True, 'activa': mesa.activa})

@app.route('/api/reiniciar_turnos/<int:mesa_id>', methods=['POST'])
@login_required
@admin_required
def reiniciar_turnos(mesa_id):
    mesa = Mesa.query.get(mesa_id)
    if not mesa or mesa.eliminada:  
        return jsonify({'success': False, 'error': 'Mesa no encontrada or eliminada'})

    docente_nombre = 'Sin asignar'
    if hasattr(mesa, 'docente') and mesa.docente:
        docente_nombre = mesa.docente.nombre
    
    historial = TurnoHistorial(
        mesa_id=mesa_id,
        turno=mesa.turno_actual,
        docente=docente_nombre,
        accion='reinicio'
    )
    db.session.add(historial)
    
    mesa.turno_actual = 0
    db.session.commit()
    
    return jsonify({'success': True, 'nuevo_turno': mesa.turno_actual})

@app.route('/api/crear_mesa', methods=['POST'])
@login_required
@admin_required
def api_crear_mesa():
    try:
        numero = obtener_proximo_numero_mesa()
        
        mesa_eliminada = Mesa.query.filter_by(numero=numero, eliminada=True).first()
        
        if mesa_eliminada:
            mesa_eliminada.eliminada = False
            mesa_eliminada.activa = True
            mesa_eliminada.turno_actual = 0
            mesa_eliminada.docente_id = None
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'mesa': mesa_eliminada.to_dict(),
                'recuperada': True,
                'message': f'Mesa {numero} recuperada correctamente'
            })
        else:
            mesa_existente = Mesa.query.filter_by(numero=numero, eliminada=False).first()
            if mesa_existente:
                return jsonify({
                    'success': False, 
                    'error': f'Ya existe una mesa con el número {numero}'
                })
            
            nueva_mesa = Mesa(numero=numero, activa=True, turno_actual=0, eliminada=False)
            db.session.add(nueva_mesa)
            db.session.commit()
            
            return jsonify({
                'success': True,
                'mesa': nueva_mesa.to_dict(),
                'recuperada': False,
                'message': f'Mesa {numero} creada correctamente'
            })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/activar_mesa_api/<int:mesa_id>', methods=['POST'])
@login_required
@admin_required
def api_activar_mesa(mesa_id):
    try:
        mesa = Mesa.query.get_or_404(mesa_id)
        if mesa.eliminada: 
            return jsonify({'success': False, 'error': 'No se puede activar una mesa eliminada'})
            
        mesa.activa = not mesa.activa
        db.session.commit()
        
        return jsonify({
            'success': True,
            'activa': mesa.activa,
            'message': f'Mesa {"activada" if mesa.activa else "desactivada"} correctamente'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/asignar_docente_api', methods=['POST'])
@login_required
@admin_required
def api_asignar_docente():
    try:
        data = request.get_json()
        mesa_id = data.get('mesa_id')
        docente_id = data.get('docente_id')
        
        mesa = Mesa.query.get_or_404(mesa_id)
        
        if mesa.eliminada: 
            return jsonify({'success': False, 'error': 'No se puede asignar docente a una mesa eliminada'})
        
        if docente_id:
            if docente_ya_asignado(docente_id):
                docente_existente = Usuario.query.get(docente_id)
                mesa_existente = Mesa.query.filter_by(
                    docente_id=docente_id, 
                    activa=True, 
                    eliminada=False
                ).first()
                
                return jsonify({
                    'success': False, 
                    'error': f'El docente {docente_existente.nombre} ya está asignado a la Mesa {mesa_existente.numero}'
                })
            
            docente = Usuario.query.get(docente_id)
            if not docente or docente.rol != 'docente':
                return jsonify({'success': False, 'error': 'Docente no válido'})
            
            mesa.docente_id = docente_id
            docente_name = docente.nombre
        else:
            mesa.docente_id = None
            docente_name = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'docente': docente_name,
            'message': 'Docente asignado correctamente' if docente_id else 'Docente removido correctamente'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/eliminar_mesa/<int:mesa_id>', methods=['DELETE'])
@login_required
@admin_required
def api_eliminar_mesa(mesa_id):
    try:
        mesa = Mesa.query.get_or_404(mesa_id)
        
        mesa.eliminada = True
        mesa.activa = False
        
        mesa.docente_id = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Mesa marcada como eliminada',
            'mesa_numero': mesa.numero  
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/recuperar_mesa/<int:mesa_id>', methods=['POST'])
@login_required
@admin_required
def api_recuperar_mesa(mesa_id):
    try:
        mesa = Mesa.query.get_or_404(mesa_id)
        
        if not mesa.eliminada:
            return jsonify({'success': False, 'error': 'La mesa no está eliminada'})
        
        mesa.eliminada = False
        mesa.activa = True
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Mesa {mesa.numero} recuperada correctamente',
            'mesa': mesa.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/mesas_eliminadas')
@login_required
@admin_required
def api_mesas_eliminadas():
    try:
        mesas_eliminadas = Mesa.query.filter_by(eliminada=True).order_by(Mesa.numero).all()
        
        return jsonify({
            'success': True,
            'mesas': [m.to_dict() for m in mesas_eliminadas]
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/reiniciar_turnos_mesa/<int:mesa_id>', methods=['POST'])
@login_required
@admin_required
def api_reiniciar_turnos(mesa_id):
    try:
        mesa = Mesa.query.get_or_404(mesa_id)
        
        if mesa.eliminada: 
            return jsonify({'success': False, 'error': 'No se puede reiniciar turnos de una mesa eliminada'})
        
        docente_nombre = 'Sin asignar'
        if hasattr(mesa, 'docente') and mesa.docente:
            docente_nombre = mesa.docente.nombre
        
        historial = TurnoHistorial(
            mesa_id=mesa_id,
            turno=mesa.turno_actual,
            docente=docente_nombre,
            accion='reinicio'
        )
        db.session.add(historial)
        
        mesa.turno_actual = 0
        db.session.commit()
        
        return jsonify({
            'success': True,
            'nuevo_turno': mesa.turno_actual,
            'message': 'Turno reiniciado correctamente'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/crear_usuario', methods=['POST'])
@login_required
@admin_required
def crear_usuario():
    try:
        data = request.get_json()
        nombre = data.get('nombre')
        email = data.get('email')
        password = data.get('password')
        rol = data.get('rol')
        
        if not all([nombre, email, password, rol]):
            return jsonify({'success': False, 'error': 'Todos los campos son requeridos'})
        
        if Usuario.query.filter_by(email=email).first():
            return jsonify({'success': False, 'error': 'Ya existe un usuario con este email'})
        
        if rol not in ['admin', 'docente']:
            return jsonify({'success': False, 'error': 'Rol no válido'})
        
        nuevo_usuario = Usuario(
            nombre=nombre,
            email=email,
            password=password,
            rol=rol,
            activo=True
        )
        
        db.session.add(nuevo_usuario)
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Usuario {nombre} creado exitosamente',
            'usuario': nuevo_usuario.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al crear usuario: {str(e)}'})

@app.route('/api/editar_usuario/<int:usuario_id>', methods=['POST'])
@login_required
@admin_required
def editar_usuario(usuario_id):
    try:
        data = request.get_json()
        nombre = data.get('nombre')
        email = data.get('email')
        password = data.get('password')
        rol = data.get('rol')
        activo = data.get('activo')
        
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'})
        
        if email and email != usuario.email:
            if Usuario.query.filter(Usuario.email == email, Usuario.id != usuario_id).first():
                return jsonify({'success': False, 'error': 'Ya existe un usuario con este email'})
            usuario.email = email
        
        if nombre:
            usuario.nombre = nombre
        
        if rol and rol in ['admin', 'docente']:
            usuario.rol = rol
        
        if activo is not None:
            usuario.activo = activo
        
        if password:
            usuario.password = password
        
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Usuario {usuario.nombre} actualizado exitosamente',
            'usuario': usuario.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al editar usuario: {str(e)}'})

@app.route('/api/eliminar_usuario/<int:usuario_id>', methods=['DELETE'])
@login_required
@admin_required
def eliminar_usuario(usuario_id):
    try:
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'})
        
        if 'usuario' in session and session['usuario']['id'] == usuario_id:
            return jsonify({'success': False, 'error': 'No puedes eliminar tu propia cuenta'})
        
        if usuario.rol == 'docente':
            mesas_asignadas = Mesa.query.filter_by(docente_id=usuario_id).all()
            for mesa in mesas_asignadas:
                mesa.docente_id = None
        
        usuario.activo = False
        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': f'Usuario {usuario.nombre} eliminado exitosamente'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al eliminar usuario: {str(e)}'})

@app.route('/api/obtener_usuario/<int:usuario_id>')
@login_required
@admin_required
def obtener_usuario(usuario_id):
    try:
        usuario = Usuario.query.get(usuario_id)
        if not usuario:
            return jsonify({'success': False, 'error': 'Usuario no encontrado'})
        
        mesa_asignada = None
        if usuario.rol == 'docente':
            mesa = Mesa.query.filter_by(docente_id=usuario_id).first()
            if mesa:
                mesa_asignada = mesa.to_dict()
        
        usuario_data = usuario.to_dict()
        usuario_data['mesa_asignada'] = mesa_asignada
        
        return jsonify({
            'success': True, 
            'usuario': usuario_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': f'Error al obtener usuario: {str(e)}'})

@app.route('/api/reiniciar_sistema', methods=['POST'])
@login_required
@admin_required
def reiniciar_sistema():
    try:
        # Eliminar todas las mesas permanentemente
        mesas = Mesa.query.all()
        for mesa in mesas:
            # Eliminar registros relacionados
            TurnoHistorial.query.filter_by(mesa_id=mesa.id).delete()
            TurnoGeneral.query.filter_by(mesa_id=mesa.id).delete()
            # Eliminar la mesa
            db.session.delete(mesa)
        
        # Eliminar todos los turnos generales
        TurnoGeneral.query.delete()
        
        # Reiniciar el contador de turnos
        global ultimo_turno_avanzado
        ultimo_turno_avanzado = None
        
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Sistema reiniciado correctamente. Todas las mesas han sido eliminadas permanentemente.'
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Error al reiniciar: {str(e)}'})

@app.errorhandler(404)
def pagina_no_encontrada(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def error_servidor(error):
    return render_template('errors/500.html'), 500

@app.before_request
def create_tables():
    inicializar_base_datos()

if __name__ == '__main__':
    host = os.getenv('FLASK_HOST', '0.0.0.0')
    port = int(os.getenv('FLASK_PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'True').lower() == 'true'
    
    app.run(host=host, port=port, debug=debug)