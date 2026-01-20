from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
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
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class BookStock(db.Model):
    __tablename__ = 'book_stock'
    id = db.Column(db.Integer, primary_key=True)
    categoria = db.Column(db.String(50))
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    stock = db.Column(db.Integer)
    minimos = db.Column(db.Integer)
    orden_compra = db.Column(db.Integer)   # 👈 CAMBIO CLAVE



class Entrada(db.Model):
    __tablename__ = 'entradas'
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)

class Salida(db.Model):
    __tablename__ = 'salidas'
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)

class OrdenCompra(db.Model):
    __tablename__ = 'orden_compra'
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    nueva_orden_compra = db.Column(db.Integer)False)

# ================== HELPERS ==================
def color_stock(stock, minimo, orden):
    if minimo is None:
        return 'verde'
    if stock < minimo:
        return 'rojo'
    if orden is not None and stock < orden:
        return 'amarillo'
    return 'verde'




# ================== LOGIN ==================
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form['usuario']
        password = request.form['password']

        user = Usuario.query.filter_by(usuario=usuario).first()
        if user and user.check_password(password):
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
    return render_template('stock.html', data=data, color_stock=color_stock)

# ================== EDITAR STOCK ==================
@app.route('/book_stock/editar/<int:id>', methods=['POST'])
@login_required
@rol_required('admin')
def editar_book_stock(id):
    item = BookStock.query.get_or_404(id)

    try:
        item.stock = int(request.form['stock'])
        item.minimos = int(request.form['minimos'])
        item.orden_compra = int(request.form['orden_compra'])

        db.session.commit()
        flash('Registro actualizado', 'success')

    except Exception as e:
        db.session.rollback()
        flash(f'Error al guardar: {e}', 'danger')

    return redirect(url_for('book_stock'))


# ================== TALLER ==================
@app.route('/taller', methods=['GET', 'POST'])
@login_required
@rol_required('taller')
def taller():
    if request.method == 'POST':
        item = BookStock.query.get(request.form['id'])
        cantidad = int(request.form['cantidad'])

        item.stock -= cantidad
        db.session.add(Salida(
            producto=item.producto,
            talla=item.talla,
            cantidad=cantidad
        ))
        db.session.commit()

    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('taller.html', data=data)

# ================== MAQUILA ==================
@app.route('/maquila', methods=['GET', 'POST'])
@login_required
@rol_required('maquila')
def maquila():
    if request.method == 'POST':
        item = BookStock.query.get(request.form['id'])
        cantidad = int(request.form['cantidad'])

        item.stock += cantidad
        db.session.add(Entrada(
            producto=item.producto,
            talla=item.talla,
            cantidad=cantidad
        ))
        db.session.commit()

    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('maquila.html', data=data)

# ================== ADMIN ==================
@app.route('/admin', methods=['GET', 'POST'])
@login_required
@rol_required('admin')
def admin():
    if request.method == 'POST':
        oc = OrdenCompra.query.get(request.form['id'])
        oc.nueva_orden_compra = int(request.form['nueva'])
        db.session.commit()

    data = OrdenCompra.query.all()
    return render_template('admin.html', data=data)

# ================== SYNC MANUAL ==================
import subprocess

@app.route('/sync')
@login_required
@rol_required('admin')
def sync_manual():
    try:
        subprocess.run(
            ['python3', 'sync.py'],
            check=True
        )
        flash('Sincronización completada correctamente', 'success')
    except Exception as e:
        flash(f'Error en sync: {e}', 'danger')

    return redirect(url_for('admin'))


# ================== AUMENTAR MINIMOS ==================
@app.route('/aumentar-minimos')
@login_required
@rol_required('admin')
def aumentar_minimos():
    for item in BookStock.query.all():
        item.minimos += 2
    db.session.commit()
    flash('Mínimos aumentados', 'success')
    return redirect(url_for('book_stock'))

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
