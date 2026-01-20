from app import db, BookStock, OrdenCompra

OrdenCompra.query.delete()

for b in BookStock.query.all():
    stock_nuevo = b.stock
    urgente = abs(stock_nuevo) if stock_nuevo < 0 else 0
    faltantes = max(b.orden_compra - stock_nuevo, 0)

    db.session.add(OrdenCompra(
        producto=b.producto,
        talla=b.talla,
        nueva_orden_compra=faltantes,
    ))

db.session.commit()
