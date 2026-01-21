from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
import os

# ================== CONFIG ==================
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'clave-secreta')

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_WJpEv58mZdzT@ep-billowing-mountain-ahvp3wat-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ================== DECORADORES ==================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def rol_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if session.get('rol') not in roles:
                flash('Acceso no autorizado', 'danger')
                return redirect(url_for('book_stock'))
            return f(*args, **kwargs)
        return wrapped
    return decorator

# ================== MODELOS ==================
class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BookStock(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(50))
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    stock = db.Column(db.Integer, default=0)
    minimos = db.Column(db.Integer, default=0)
    orden_compra = db.Column(db.Integer, default=0)

class Entrada(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class Salida(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

# ================== LOGIN ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(usuario=request.form['usuario']).first()
        if user and user.check_password(request.form['password']):
            session['usuario_id'] = user.id
            session['usuario'] = user.usuario
            session['rol'] = user.rol
            return redirect(url_for('book_stock'))

        flash('Credenciales incorrectas', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================== STOCK GENERAL ==================
@app.route('/')
@login_required
def book_stock():
    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('stock.html', data=data)

# ================== ADMIN ==================
@app.route('/admin', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def admin():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('orden_'):
                item_id = int(key.split('_')[1])
                item = BookStock.query.get(item_id)
                if item:
                    item.orden_compra = int(value or 0)
        db.session.commit()
        flash('Órdenes actualizadas', 'success')

    productos_bajo_minimo = BookStock.query.filter(
        BookStock.stock < BookStock.minimos
    ).order_by(BookStock.producto).all()

    entradas = Entrada.query.order_by(Entrada.fecha.desc()).limit(20).all()

    return render_template(
        'admin.html',
        data=productos_bajo_minimo,
        entradas=entradas
    )

# ================== TALLER ==================
@app.route('/taller', methods=['GET', 'POST'])
@login_required
@rol_required('taller')
def taller():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('salida_') and value:
                item_id = int(key.split('_')[1])
                cantidad = int(value)

                item = BookStock.query.get(item_id)
                if not item:
                    continue

                if cantidad > item.stock:
                    flash(f'Stock insuficiente para {item.producto} {item.talla}', 'danger')
                    continue

                item.stock -= cantidad
                db.session.add(Salida(
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=cantidad
                ))

        db.session.commit()
        flash('Salidas registradas', 'success')

    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('taller.html', data=data)

# ================== MAQUILA ==================
@app.route('/maquila', methods=['GET', 'POST'])
@login_required
@rol_required('maquila')
def maquila():
    if request.method == 'POST':
        for key, value in request.form.items():
            if key.startswith('entrada_') and value:
                item_id = int(key.split('_')[1])
                cantidad = int(value)

                item = BookStock.query.get(item_id)
                if not item:
                    continue

                if cantidad > item.orden_compra:
                    flash(f'Cantidad supera orden de compra en {item.producto}', 'danger')
                    continue

                item.stock += cantidad
                item.orden_compra -= cantidad

                db.session.add(Entrada(
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=cantidad
                ))

        db.session.commit()
        flash('Entradas registradas', 'success')

    data = BookStock.query.filter(
        BookStock.orden_compra > 0
    ).order_by(BookStock.producto).all()

    return render_template('maquila.html', data=data)

# ================== INIT ==================
@app.route('/init-db')
def init_db():
    db.create_all()
    return 'Tablas creadas'

@app.route('/crear-usuarios')
def crear_usuarios():
    if Usuario.query.first():
        return 'Usuarios ya existen'

    for u, r in [('taller','taller'), ('maquila','maquila'), ('admin','admin')]:
        user = Usuario(usuario=u, rol=r)
        user.set_password('1234')
        db.session.add(user)

    db.session.commit()
    return 'Usuarios creados'

if __name__ == '__main__':
    app.run(debug=True)
