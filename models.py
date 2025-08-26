from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class TurnoGeneral(db.Model):
    __tablename__ = 'turno_general'
    id = db.Column(db.Integer, primary_key=True)
    numero_turno = db.Column(db.Integer, nullable=False, unique=True)
    estado = db.Column(db.String(20), default='pendiente')  # pendiente, atendiendo, completado
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesa.id'))
    docente = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación
    mesa = db.relationship('Mesa', backref=db.backref('turnos_atendidos', lazy=True))

class Mesa(db.Model):
    __tablename__ = 'mesa'
    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.Integer, unique=True, nullable=False)
    activa = db.Column(db.Boolean, default=True)
    turno_actual = db.Column(db.Integer, default=0)  # Solo para referencia local
    eliminada = db.Column(db.Boolean, default=False)  # NUEVO CAMPO AÑADIDO
    
    # Relación con Usuario
    docente_id = db.Column(db.Integer, db.ForeignKey('usuario.id'))
    docente = db.relationship('Usuario', backref=db.backref('mesa_asignada', uselist=False), foreign_keys=[docente_id])
    
    def to_dict(self):
        return {
            'id': self.id,
            'numero': self.numero,
            'turno_actual': self.turno_actual,
            'activa': self.activa,
            'docente_id': self.docente_id,
            'docente': self.docente.nombre if self.docente else None,
            'eliminada': self.eliminada  # INCLUIR EN EL DICT
        }

class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    rol = db.Column(db.String(20), nullable=False)  # admin, docente
    activo = db.Column(db.Boolean, default=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'nombre': self.nombre,
            'email': self.email,
            'rol': self.rol,
            'activo': self.activo,
            'mesa_id': self.mesa_asignada.id if self.mesa_asignada else None,
            'mesa': self.mesa_asignada.numero if self.mesa_asignada else None
        }

class TurnoHistorial(db.Model):
    __tablename__ = 'turno_historial'
    id = db.Column(db.Integer, primary_key=True)
    mesa_id = db.Column(db.Integer, db.ForeignKey('mesa.id'))
    turno = db.Column(db.Integer, nullable=False)
    docente = db.Column(db.String(100))
    accion = db.Column(db.String(50))  # avance, reinicio, etc.
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relación
    mesa = db.relationship('Mesa', backref=db.backref('historial', lazy=True))