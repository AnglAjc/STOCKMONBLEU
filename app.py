from flask import Flask, render_template, request, redirect, url_for, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import case
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
os.makedirs(app.config['PDF_FOLDER'], exist_ok=True)

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
    precio = db.Column(db.Float, default=0)
    maquila = db.Column(db.String(1))  # A o B

# ================== ORDEN DE TALLAS ==================
orden_tallas = case(
    (BookStock.talla == 'XS', 0),
    (BookStock.talla == 'S', 1),
    (BookStock.talla == 'M', 2),
    (BookStock.talla == 'L', 3),
    (BookStock.talla == 'XL', 4),
    (BookStock.talla == 'XXL', 5),
    else_=99
)


class OrdenCompra(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    maquila = db.Column(db.String(10))
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    total = db.Column(db.Float, default=0)
    abonado = db.Column(db.Float, default=0)
    saldo = db.Column(db.Float, default=0)
    pdf = db.Column(db.String(200))

class OrdenDetalle(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    orden_id = db.Column(db.Integer, db.ForeignKey('orden_compra.id'))
    producto = db.Column(db.String(100))
    talla = db.Column(db.String(10))
    cantidad = db.Column(db.Integer)
    precio_unitario = db.Column(db.Float)
    subtotal = db.Column(db.Float)

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
def maquila_por_categoria(cat):
    if cat in ['Hoddies', 'Playeras', 'Pantalones']:
        return 'A'
    return 'B'

def generar_pdf_orden(orden, detalles):
    filename = f'orden_{orden.id}.pdf'
    path = os.path.join(app.config['PDF_FOLDER'], filename)

    doc = SimpleDocTemplate(path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(f"Orden de Compra – Maquila {orden.maquila}", styles['Title']))
    elements.append(Paragraph(f"Fecha: {orden.fecha.strftime('%Y-%m-%d')}", styles['Normal']))

    data = [['Producto', 'Talla', 'Cantidad', 'Precio', 'Subtotal']]
    for d in detalles:
        data.append([
            d.producto,
            d.talla,
            d.cantidad,
            f"${d.precio_unitario:.2f}",
            f"${d.subtotal:.2f}"
        ])

    data.append(['', '', '', 'TOTAL', f"${orden.total:.2f}"])
    data.append(['', '', '', 'ABONADO', f"${orden.abonado:.2f}"])
    data.append(['', '', '', 'SALDO',
                 'PAGADO' if orden.saldo <= 0 else f"${orden.saldo:.2f}"])

    table = Table(data)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.orange),
        ('GRID', (0,0), (-1,-1), 1, colors.black)
    ]))

    elements.append(table)
    doc.build(elements)
    return filename

# ================== CONTEXT ==================
@app.context_processor
def utility_processor():
    def color_stock(stock, minimos, en_produccion):
        if stock < 0:
            return 'table-info'                 # 🔵 negativo
        if stock < minimos:
            return 'table-danger'               # 🔴 debajo del mínimo
        if stock < minimos * 2:
            return 'table-warning'              # 🟡 entre mínimo y doble
        return 'table-success'                  # 🟢 arriba del doble
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

# ================== STOCK ==================
@app.route('/')
@login_required
def book_stock():
    data = BookStock.query.order_by(BookStock.producto, orden_tallas).all()
    return render_template('stock.html', data=data)
    


# ================== ADMIN ==================
@app.route('/admin', methods=['GET','POST'])
@login_required
@rol_required('admin')
def admin():
    maquila_filtro = request.args.get('maquila')
    q = request.args.get('q', '').strip()   # ← YA ESTABA, SE RESPETA



    # ---- NUEVO PRODUCTO ----
    if request.method == 'POST' and request.form.get('nuevo_producto'):
        producto = request.form.get('producto')
        categoria = request.form.get('categoria')
        talla = request.form.get('talla')
        stock = int(request.form.get('stock', 0))
        minimos = int(request.form.get('minimos', 0))
        precio = float(request.form.get('precio', 0))

        nuevo = BookStock(
            producto=producto,
            categoria=categoria,
            talla=talla,
            stock=stock,
            minimos=minimos,
            precio=precio,
            en_produccion=0,
            maquila=maquila_por_categoria(categoria)
        )

        db.session.add(nuevo)
        db.session.commit()

        flash('Producto agregado correctamente', 'success')
        return redirect(url_for('admin'))

    # ---- ABONOS ----
    if request.method == 'POST' and request.form.get('abono_orden'):
        orden = OrdenCompra.query.get(int(request.form['abono_orden']))
        monto = float(request.form.get('nuevo_abono', 0))
        if orden and monto > 0:
            orden.abonado += monto
            orden.saldo = max(0, orden.total - orden.abonado)
            db.session.add(Pago(orden_id=orden.id, monto=monto))
            db.session.commit()
        return redirect(url_for('admin'))

    # ---- CREAR ORDEN ----
    if request.method == 'POST' and not request.form.get('abono_orden'):
        orden = OrdenCompra()
        db.session.add(orden)
        db.session.flush()

        total = 0
        maquila = None
        detalles = []

        for key, val in request.form.items():
            if key.startswith('orden_') and val and int(val) > 0:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)

                item.en_produccion += cantidad
                item.maquila = maquila_por_categoria(item.categoria)
                maquila = item.maquila

                subtotal = cantidad * item.precio
                total += subtotal

                detalles.append(OrdenDetalle(
                    orden_id=orden.id,
                    producto=item.producto,
                    talla=item.talla,
                    cantidad=cantidad,
                    precio_unitario=item.precio,
                    subtotal=subtotal
                ))

        orden.maquila = maquila
        orden.total = total
        orden.abonado = 0
        orden.saldo = total

        for d in detalles:
            db.session.add(d)

        orden.pdf = generar_pdf_orden(orden, detalles)
        db.session.commit()

    query = BookStock.query


    if maquila_filtro:
        query = query.filter(BookStock.maquila == maquila_filtro)

    if q:   # ← BUSCADOR FUNCIONAL (NO SE TOCA)
        query = query.filter(
            db.or_(
                BookStock.producto.ilike(f'%{q}%'),
                BookStock.categoria.ilike(f'%{q}%')
            )
        )

    return render_template(
        'admin.html',
        data=query.order_by(BookStock.producto, orden_tallas).all(),
        ordenes=OrdenCompra.query.order_by(OrdenCompra.fecha.desc()).all(),
        q=q
    )


@app.route('/pdf/<nombre>')
@login_required
def ver_pdf(nombre):
    return send_file(os.path.join(app.config['PDF_FOLDER'], nombre))



# ================== MAQUILA ==================
@app.route('/maquila', methods=['GET','POST'])
@login_required
@rol_required('maquila')
def maquila():
    if request.method == 'POST':
        for key, val in request.form.items():
            if key.startswith('envio_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)

                item.en_produccion -= cantidad
                item.stock += cantidad

                db.session.add(
                    Envio(
                        producto=item.producto,
                        talla=item.talla,
                        cantidad=cantidad
                    )
                )
        db.session.commit()

    # 🚫 EXCLUIR ACCESORIOS
    data = (
        BookStock.query
        .filter(BookStock.maquila == 'A')
        .filter(BookStock.categoria != 'accesorios')
        .order_by(BookStock.producto, orden_tallas)
        .all()
    )

    ordenes = (
        OrdenCompra.query
        .filter_by(maquila='A')
        .order_by(OrdenCompra.fecha.desc())
        .all()
    )

    return render_template('maquila.html', data=data, ordenes=ordenes)


# ================== TALLER ==================
@app.route('/taller', methods=['GET','POST'])
@login_required
@rol_required('taller')
def taller():
    estado = TallerEstado.query.first()

    # 🔹 FILTRO MAQUILA (A por defecto)
    maquila_filtro = request.args.get('maquila', 'A')

    if request.method == 'POST':

        # ---------- ÚLTIMO PEDIDO ----------
        ultimo = request.form.get('ultimo_pedido', '').strip()
        if ultimo:
            if not estado:
                estado = TallerEstado(ultimo_pedido=ultimo)
                db.session.add(estado)
            else:
                estado.ultimo_pedido = ultimo

        # ---------- SALIDAS ----------
        for key, val in request.form.items():
            if key.startswith('salida_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)

                item.stock -= cantidad

                db.session.add(
                    Salida(
                        producto=item.producto,
                        talla=item.talla,
                        cantidad=cantidad
                    )
                )

        # ---------- ENTRADAS (NUEVO) ----------
        for key, val in request.form.items():
            if key.startswith('entrada_') and val:
                item = BookStock.query.get(int(key.split('_')[1]))
                cantidad = int(val)

                item.stock += cantidad

        db.session.commit()

    # 🔹 STOCK FILTRADO POR MAQUILA
    data = (
        BookStock.query
        .filter(BookStock.maquila == maquila_filtro)
        .order_by(BookStock.producto, orden_tallas)
        .all()
    )

    return render_template(
        'taller.html',
        data=data,
        estado=estado,
        ultimo_pedido=estado.ultimo_pedido if estado else None,
        maquila_filtro=maquila_filtro
    )

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
