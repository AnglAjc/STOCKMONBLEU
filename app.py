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

# ================== AUTH ==================
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ================== MODELOS ==================
class Usuario(db.Model):
    __tablename__ = 'usuario'
    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)  # taller | maquila

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
    minimos = db.Column(db.Integer, nullable=True)
    orden_compra = db.Column(db.String(50), nullable=True)


class FaltantesJueves(db.Model):
    __tablename__ = 'faltantes_jueves'
    id = db.Column(db.Integer, primary_key=True)
    producto = db.Column(db.String(100))
    ch = db.Column(db.Integer, nullable=True)
    m = db.Column(db.Integer, nullable=True)
    l = db.Column(db.Integer, nullable=True)
    xl = db.Column(db.Integer, nullable=True)

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
    flash('Sesión cerrada exitosamente', 'info')
    return redirect(url_for('login'))


# ================== BOOK STOCK ==================
@app.route('/')
@login_required
def book_stock():
    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('stock.html', data=data)

@app.route('/book_stock/editar/<int:id>', methods=['POST'])
@login_required
def editar_book_stock(id):
    item = BookStock.query.get_or_404(id)
    item.stock = request.form['stock']
    item.minimos = request.form['minimos'] or None
    item.orden_compra = request.form['orden_compra'] or None
    db.session.commit()
    return redirect(url_for('book_stock'))

# ================== FALTANTES ==================
@app.route('/faltantes')
@login_required
def faltantes():
    data = FaltantesJueves.query.order_by(FaltantesJueves.producto).all()
    return render_template('faltantes.html', data=data)

@app.route('/faltantes/editar/<int:id>', methods=['POST'])
@login_required
def editar_faltantes(id):
    f = FaltantesJueves.query.get_or_404(id)
    f.ch = request.form['ch'] or None
    f.m = request.form['m'] or None
    f.l = request.form['l'] or None
    f.xl = request.form['xl'] or None
    db.session.commit()
    return redirect(url_for('faltantes'))

# ================== INIT DB ==================
@app.route('/init-db')
def init_db():
    db.create_all()
    return 'Tablas creadas correctamente'

@app.route('/crear-usuarios')
def crear_usuarios():
    if Usuario.query.first():
        return 'Usuarios ya existen'

    taller = Usuario(usuario='taller', rol='taller')
    taller.set_password('1234')

    maquila = Usuario(usuario='maquila', rol='maquila')
    maquila.set_password('1234')

    db.session.add_all([taller, maquila])
    db.session.commit()

    return 'Usuarios creados: taller / maquila (password: 1234)'

# ================== MAIN ==================
if __name__ == '__main__':
    app.run(debug=True)
