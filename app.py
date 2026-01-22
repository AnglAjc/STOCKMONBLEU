from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import os

# ================== CONFIG ==================
app = Flask(__name__)
app.config['SECRET_KEY'] = 'clave-secreta'
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://neondb_owner:npg_WJpEv58mZdzT@ep-billowing-mountain-ahvp3wat-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PDF_FOLDER'] = 'pdfs'

db = SQLAlchemy(app)

if not os.path.exists(app.config['PDF_FOLDER']):
    os.makedirs(app.config['PDF_FOLDER'])

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
    usuario = db.Column(db.String(50), unique=True)
    password_hash = db.Column(db.String(255))
    rol = db.Column(db.String(20))

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
    en_produccion = db.Column(db.Integer, default=0)
    maquila = db.Column(db.String(20))  # A o B

class OrdenCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maquila = db.Column(db.String(20))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    pdf = db.Column(db.String(200))

class OrdenDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'))
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)

class Envio(db.Model):
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

class Pago(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer)
    monto = db.Column(db.Float)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class TallerEstado(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ultimo_pedido = db.Column(db.String(100))

# ================== HELPERS ==================
def generar_pdf_orden(orden, detalles):
    filename = f'orden_{orden.id}.pdf'
    path = os.path.join(app.config['PDF_FOLDER'], filename)

    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Orden de Compra – Maquila {orden.maquila}", styles['Title']))
    elements.append(Paragraph(f"Fecha: {orden.fecha.strftime('%Y-%m-%d')}", styles['Normal']))

    data = [['Producto', 'Talla', 'Cantidad']]
    for d in detalles:
        data.append([d.producto, d.talla, d.cantidad])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)
    return filename

@app.context_processor
def utility_processor():
    def color_stock(stock, minimo, produccion):
        if stock < minimo:
            return 'rojo'
        if produccion and produccion > 0:
            return 'amarillo'
        return 'verde'
    return dict(color_stock=color_stock)

# ================== LOGIN ==================
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = Usuario.query.filter_by(usuario=request.form['usuario']).first()
        if u and u.check_password(request.form['password']):
            session['usuario_id'] = u.id
            session['rol'] = u.rol
            return redirect(url_for('book_stock'))
        flash('Credenciales incorrectas')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ================== STOCK GENERAL (CON BUSCADOR) ==================
@app.route('/')
@login_required
def book_stock():
    q = request.args.get('q', '')
    query = BookStock.query
    if q:
        query = query.filter(
            (BookStock.producto.ilike(f'%{q}%')) |
            (BookStock.categoria.ilike(f'%{q}%'))
        )
    data = query.order_by(BookStock.producto).all()
    return render_template('stock.html', data=data, q=q)

# ================== ADMIN ==================
@app.route('/admin', methods=['GET','POST'])
@login_required
@rol_required('admin')
def admin():
    if request.method == 'POST':
        maquila = request.form['maquila']
        orden = OrdenCompra(maquila=maquila)
        db.session.add(orden)
        db.session.flush()

        detalles = []
        for key, val in request.form.items():
            if key.startswith('orden_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)
                item.en_produccion += cantidad
                d = OrdenDetalle(
                    orden_id=orden.id,
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=cantidad
                )
                db.session.add(d)
                detalles.append(d)

        orden.pdf = generar_pdf_orden(orden, detalles)
        db.session.commit()
        flash('Orden creada y PDF generado')

    productos_bajo_minimo = BookStock.query.filter(
        BookStock.stock < BookStock.minimos
    ).order_by(BookStock.producto).all()

    ordenes = OrdenCompra.query.order_by(OrdenCompra.fecha.desc()).all()

    return render_template(
        'admin.html',
        data=productos_bajo_minimo,
        ordenes=ordenes
    )

@app.route('/pdf/<nombre>')
@login_required
def ver_pdf(nombre):
    return send_file(os.path.join(app.config['PDF_FOLDER'], nombre))

# ================== MAQUILA (SOLO PANTALONES, PLAYERAS, HODDIES) ==================
@app.route('/maquila', methods=['GET','POST'])
@login_required
@rol_required('maquila')
def maquila():
    if request.method == 'POST':
        for key,val in request.form.items():
            if key.startswith('envio_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)
                item.en_produccion -= cantidad
                item.stock += cantidad
                db.session.add(Envio(
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=cantidad
                ))
        db.session.commit()
        flash('Envíos registrados')

    data = BookStock.query.filter(
        BookStock.categoria.in_(['Pantalones','Playeras','Hoddies'])
    ).order_by(BookStock.producto).all()

    return render_template('maquila.html', data=data)

# ================== TALLER (ÚLTIMO PEDIDO FUNCIONAL) ==================
@app.route('/taller', methods=['GET','POST'])
@login_required
@rol_required('taller')
def taller():
    estado = TallerEstado.query.first()

    if request.method == 'POST':
        ultimo = request.form.get('ultimo_pedido')
        if ultimo is not None:
            if not estado:
                estado = TallerEstado(ultimo_pedido=ultimo)
                db.session.add(estado)
            else:
                estado.ultimo_pedido = ultimo

        for key,val in request.form.items():
            if key.startswith('salida_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                item.stock -= int(val)
                db.session.add(Salida(
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=int(val)
                ))

        db.session.commit()
        flash('Datos actualizados')

    data = BookStock.query.order_by(BookStock.producto).all()
    return render_template('taller.html', data=data, estado=estado)

# ================== AUMENTAR MINIMOS ==================
@app.route('/aumentar-minimos')
@login_required
@rol_required('admin')
def aumentar_minimos():
    for item in BookStock.query.all():
        item.minimos += 2
    db.session.commit()
    flash('Mínimos aumentados')
    return redirect(url_for('book_stock'))

# ================== INIT ==================
@app.route('/init-db')
def init_db():
    db.create_all()
    return 'OK'

@app.route('/crear-usuarios')
def crear_usuarios():
    if Usuario.query.first():
        return 'Ya existen'
    for u,r in [('admin','admin'),('taller','taller'),('maquila','maquila')]:
        user = Usuario(usuario=u, rol=r)
        user.set_password('1234')
        db.session.add(user)
    db.session.commit()
    return 'Usuarios creados'

if __name__ == '__main__':
    app.run(debug=True)
