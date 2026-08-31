from flask import Flask, render_template, request, redirect, url_for, session
from database import obtener_conexion
from functools import wraps
import bcrypt
import os


app = Flask(__name__)

app.secret_key = os.getenv(
    "SECRET_KEY",
    "clave_prueba"
)


# =====================================================
# PROTECCIÓN DE ADMINISTRADOR
# =====================================================

def administrador_requerido(func):

    @wraps(func)
    def decorador(*args, **kwargs):

        if "id_usuario" not in session:
            return redirect(url_for("login"))

        if session.get("rol") != "admin":
            return "Acceso denegado. Solo administradores."

        return func(*args, **kwargs)

    return decorador


# =====================================================
# INICIO
# =====================================================

@app.route("/")
def inicio():

    return render_template("index.html")


# =====================================================
# PRODUCTOS
# =====================================================

@app.route("/productos")
def productos():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT
                p.id_producto,
                p.nombre,
                p.descripcion,
                p.precio,
                COALESCE(i.stock_actual, 0) AS stock,
                c.nombre AS categoria
            FROM productos p
            INNER JOIN categorias c
                ON p.id_categoria = c.id_categoria
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            ORDER BY p.id_producto
        """)

        productos = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "productos.html",
        productos=productos
    )


# =====================================================
# REGISTRO
# =====================================================

@app.route("/registro", methods=["GET", "POST"])
def registro():

    if request.method == "POST":

        # Compatible con formularios que tengan "nombre"
        # o con formularios que ya tengan los dos campos.
        nombre_panaderia = request.form.get(
            "nombre_panaderia",
            "Panadería"
        ).strip()

        nombre_encargado = request.form.get(
            "nombre_encargado",
            request.form.get("nombre", "")
        ).strip()

        correo = request.form.get("correo", "").strip()
        password = request.form.get("password", "")

        if not nombre_encargado:
            return "El nombre del encargado es obligatorio."

        if not correo:
            return "El correo es obligatorio."

        if not password:
            return "La contraseña es obligatoria."

        password_hash = bcrypt.hashpw(
            password.encode("utf-8"),
            bcrypt.gensalt()
        ).decode("utf-8")

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        try:

            cursor.execute("""
                INSERT INTO usuarios
                (
                    nombre_panaderia,
                    nombre_encargado,
                    correo,
                    password_hash,
                    rol
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                nombre_panaderia,
                nombre_encargado,
                correo,
                password_hash,
                "cliente"
            ))

            conexion.commit()

        except Exception as error:

            conexion.rollback()

            print(
                "ERROR AL REGISTRAR USUARIO:",
                error
            )

            return "No se pudo registrar el usuario."

        finally:

            cursor.close()
            conexion.close()

        return redirect(url_for("login"))

    return render_template("registro.html")


# =====================================================
# LOGIN
# =====================================================

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        correo = request.form.get("correo", "").strip()
        password = request.form.get("password", "")

        conexion = obtener_conexion()
        cursor = conexion.cursor()

        try:

            cursor.execute("""
                SELECT
                    id_usuario,
                    nombre_panaderia,
                    nombre_encargado,
                    correo,
                    password_hash,
                    rol
                FROM usuarios
                WHERE correo = %s
            """, (correo,))

            usuario = cursor.fetchone()

        finally:

            cursor.close()
            conexion.close()

        if usuario:

            try:

                password_correcta = bcrypt.checkpw(
                    password.encode("utf-8"),
                    usuario[4].encode("utf-8")
                )

            except ValueError:

                return (
                    "La contraseña almacenada "
                    "no tiene un hash válido."
                )

            if password_correcta:

                session["id_usuario"] = usuario[0]
                session["nombre"] = usuario[2]
                session["nombre_panaderia"] = usuario[1]
                session["correo"] = usuario[3]
                session["rol"] = usuario[5]

                return redirect(
                    url_for("inicio")
                )

        return "Correo o contraseña incorrectos."

    return render_template("login.html")


# =====================================================
# CERRAR SESIÓN
# =====================================================

@app.route("/logout")
def logout():

    session.clear()

    return redirect(
        url_for("inicio")
    )


# =====================================================
# ADMIN
# =====================================================

@app.route("/admin")
@administrador_requerido
def admin():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =========================================
        # PRODUCTOS
        # =========================================

        cursor.execute("""
            SELECT
                p.id_producto,
                p.nombre,
                p.descripcion,
                p.precio,
                p.id_categoria,
                c.nombre AS categoria,
                COALESCE(i.stock_actual, 0) AS stock
            FROM productos p
            INNER JOIN categorias c
                ON p.id_categoria = c.id_categoria
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            ORDER BY p.id_producto
        """)

        productos = cursor.fetchall()


        # =========================================
        # CATEGORÍAS
        # =========================================

        cursor.execute("""
            SELECT
                id_categoria,
                nombre,
                descripcion
            FROM categorias
            ORDER BY id_categoria
        """)

        categorias = cursor.fetchall()


        # =========================================
        # PEDIDOS
        # =========================================

        cursor.execute("""
            SELECT
                p.id_pedido,
                u.nombre_encargado,
                u.correo,
                p.fecha_pedido,
                p.total,
                p.estado
            FROM pedidos p
            INNER JOIN usuarios u
                ON p.id_usuario = u.id_usuario
            ORDER BY p.fecha_pedido DESC
        """)

        pedidos = cursor.fetchall()


        # =========================================
        # CAJA — RESUMEN
        # =========================================

        cursor.execute("""
            SELECT
                COALESCE(SUM(monto), 0),
                COUNT(*)
            FROM pagos
            WHERE estado = 'aprobado'
        """)

        resumen = cursor.fetchone()

        total_ventas = resumen[0]
        cantidad_ventas = resumen[1]


        # =========================================
        # CAJA — VENTAS
        # =========================================

        cursor.execute("""
            SELECT
                pa.id_pago,
                pa.id_pedido,
                u.nombre_encargado,
                pa.monto,
                pa.metodo_pago,
                pa.estado,
                pa.fecha_pago
            FROM pagos pa
            INNER JOIN usuarios u
                ON pa.id_usuario = u.id_usuario
            ORDER BY pa.fecha_pago DESC
        """)

        ventas = cursor.fetchall()


    finally:

        cursor.close()
        conexion.close()


    # =========================================
    # MOSTRAR ADMIN
    # =========================================

    return render_template(
        "admin.html",
        productos=productos,
        categorias=categorias,
        pedidos=pedidos,
        total_ventas=total_ventas,
        cantidad_ventas=cantidad_ventas,
        ventas=ventas
    )

# =====================================================
# ADMIN - ACTUALIZAR INVENTARIO
# =====================================================

@app.route(
"/admin/inventario/actualizar/<int:id_producto>",
methods=["POST"]
)
@administrador_requerido
def inventario_actualizar(id_producto):

    stock = request.form.get("stock")

    try:

        stock = int(stock)

        if stock < 0:
            return "El stock no puede ser negativo."

    except (TypeError, ValueError):

        return "El stock debe ser un número válido."

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT id_inventario
            FROM inventario
            WHERE id_producto = %s
        """, (id_producto,))

        inventario = cursor.fetchone()

        if inventario:

            cursor.execute("""
                UPDATE inventario
                SET stock_actual = %s
                WHERE id_producto = %s
            """, (
                stock,
                id_producto
            ))

        else:

            cursor.execute("""
                INSERT INTO inventario
                (
                    id_producto,
                    stock_actual,
                    stock_minimo
                )
                VALUES (%s, %s, %s)
            """, (
                id_producto,
                stock,
                5
            ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL ACTUALIZAR INVENTARIO:",
            error
        )

        return "No se pudo actualizar el inventario."

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin") + "#inventario"
    )


# =====================================================
# ADMIN - ACTUALIZAR ESTADO DEL ENVÍO
# =====================================================

@app.route(
    "/admin/envios/actualizar/<int:id_pedido>",
    methods=["POST"]
)
@administrador_requerido
def envio_actualizar(id_pedido):

    estado = request.form.get("estado")


    estados_validos = [
        "pendiente",
        "preparando",
        "enviado",
        "entregado",
        "cancelado"
    ]


    if estado not in estados_validos:

        return "Estado de envío no válido."


    conexion = obtener_conexion()
    cursor = conexion.cursor()


    try:

        cursor.execute("""
            UPDATE envios
            SET estado = %s
            WHERE id_pedido = %s
        """, (
            estado,
            id_pedido
        ))


        if cursor.rowcount == 0:

            return "No existe un envío para este pedido."


        conexion.commit()


    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL ACTUALIZAR ENVÍO:",
            error
        )

        return "No se pudo actualizar el envío."


    finally:

        cursor.close()
        conexion.close()


    return redirect(
        url_for("admin") + "#envios"
    )


# =====================================================
# ADMIN - PRODUCTOS
# =====================================================

@app.route("/admin/productos")
@administrador_requerido
def productos_admin():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT
                p.id_producto,
                p.nombre,
                p.descripcion,
                p.precio,
                p.id_categoria,
                c.nombre AS categoria,
                COALESCE(i.stock_actual, 0) AS stock
            FROM productos p
            INNER JOIN categorias c
                ON p.id_categoria = c.id_categoria
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            ORDER BY p.id_producto
        """)

        productos = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "productos_admin.html",
        productos=productos
    )


# =====================================================
# ADMIN - EDITAR PRODUCTO
# =====================================================

@app.route(
    "/admin/productos/editar/<int:id_producto>",
    methods=["GET", "POST"]
)
@administrador_requerido
def producto_editar(id_producto):

    if request.method == "GET":

        return redirect(
            url_for("admin")
        )

    nombre = request.form.get("nombre", "").strip()
    descripcion = request.form.get("descripcion", "").strip()
    precio = request.form.get("precio")
    id_categoria = request.form.get("id_categoria")
    stock = request.form.get("stock", 0)

    try:

        precio = float(precio)
        id_categoria = int(id_categoria)
        stock = int(stock)

        if precio < 0:
            return "El precio no puede ser negativo."

        if stock < 0:
            return "El stock no puede ser negativo."

    except (TypeError, ValueError):

        return "Los datos enviados no son válidos."

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =========================================
        # ACTUALIZAR PRODUCTO
        # =========================================

        cursor.execute("""
            UPDATE productos
            SET
                nombre = %s,
                descripcion = %s,
                precio = %s,
                id_categoria = %s
            WHERE id_producto = %s
        """, (
            nombre,
            descripcion,
            precio,
            id_categoria,
            id_producto
        ))

        # =========================================
        # ACTUALIZAR INVENTARIO
        # =========================================

        cursor.execute("""
            SELECT id_inventario
            FROM inventario
            WHERE id_producto = %s
        """, (id_producto,))

        inventario = cursor.fetchone()

        if inventario:

            cursor.execute("""
                UPDATE inventario
                SET stock_actual = %s
                WHERE id_producto = %s
            """, (
                stock,
                id_producto
            ))

        else:

            cursor.execute("""
                INSERT INTO inventario
                (
                    id_producto,
                    stock_actual,
                    stock_minimo
                )
                VALUES (%s, %s, %s)
            """, (
                id_producto,
                stock,
                5
            ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL EDITAR PRODUCTO:",
            error
        )

        return "No se pudo editar el producto."

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin")
    )


# =====================================================
# ADMIN - ELIMINAR PRODUCTO
# =====================================================

@app.route(
    "/admin/productos/eliminar/<int:id_producto>",
    methods=["POST"]
)
@administrador_requerido
def producto_eliminar(id_producto):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =========================================
        # COMPROBAR SI TIENE PEDIDOS
        # =========================================

        cursor.execute("""
            SELECT COUNT(*)
            FROM detalles_pedido
            WHERE id_producto = %s
        """, (id_producto,))

        cantidad_pedidos = cursor.fetchone()[0]

        if cantidad_pedidos > 0:

            return (
                "No se puede eliminar el producto "
                "porque pertenece a pedidos existentes. "
                "Esto protege el historial de ventas."
            )

        # =========================================
        # ELIMINAR DEL CARRITO
        # =========================================

        cursor.execute("""
            DELETE FROM carrito_items
            WHERE id_producto = %s
        """, (id_producto,))

        # =========================================
        # ELIMINAR INVENTARIO
        # =========================================

        cursor.execute("""
            DELETE FROM inventario
            WHERE id_producto = %s
        """, (id_producto,))

        # =========================================
        # ELIMINAR PRODUCTO
        # =========================================

        cursor.execute("""
            DELETE FROM productos
            WHERE id_producto = %s
        """, (id_producto,))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL ELIMINAR PRODUCTO:",
            error
        )

        return (
            "No se pudo eliminar el producto."
        )

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin")
    )


# =====================================================
# ADMIN - NUEVO PRODUCTO
# =====================================================

@app.route(
    "/admin/productos/nuevo",
    methods=["GET", "POST"]
)
@administrador_requerido
def producto_nuevo():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    if request.method == "POST":

        nombre = request.form.get("nombre", "").strip()
        descripcion = request.form.get("descripcion", "").strip()
        precio = request.form.get("precio")
        id_categoria = request.form.get("id_categoria")
        stock = request.form.get("stock", 0)

        try:

            precio = float(precio)
            id_categoria = int(id_categoria)
            stock = int(stock)

            if precio < 0:
                return "El precio no puede ser negativo."

            if stock < 0:
                return "El stock no puede ser negativo."

            # =========================================
            # CREAR PRODUCTO
            # =========================================

            cursor.execute("""
                INSERT INTO productos
                (
                    id_categoria,
                    nombre,
                    descripcion,
                    precio
                )
                VALUES (%s, %s, %s, %s)
            """, (
                id_categoria,
                nombre,
                descripcion,
                precio
            ))

            id_producto = cursor.lastrowid

            # =========================================
            # CREAR INVENTARIO
            # =========================================

            cursor.execute("""
                INSERT INTO inventario
                (
                    id_producto,
                    stock_actual,
                    stock_minimo
                )
                VALUES (%s, %s, %s)
            """, (
                id_producto,
                stock,
                5
            ))

            conexion.commit()

        except Exception as error:

            conexion.rollback()

            print(
                "ERROR AL CREAR PRODUCTO:",
                error
            )

            return "No se pudo crear el producto."

        finally:

            cursor.close()
            conexion.close()

        return redirect(
            url_for("productos_admin")
        )

    # =========================================
    # CATEGORÍAS
    # =========================================

    try:

        cursor.execute("""
            SELECT
                id_categoria,
                nombre
            FROM categorias
            ORDER BY nombre
        """)

        categorias = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "producto_nuevo.html",
        categorias=categorias
    )


# =====================================================
# PEDIDOS DEL ADMIN
# =====================================================

@app.route("/admin/pedidos")
@administrador_requerido
def pedidos_admin():

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT
                p.id_pedido,
                u.nombre_encargado,
                u.correo,
                p.fecha_pedido,
                p.total,
                p.estado,
                dp.id_producto,
                pr.nombre,
                dp.cantidad,
                dp.precio_unitario
            FROM pedidos p
            INNER JOIN usuarios u
                ON p.id_usuario = u.id_usuario
            INNER JOIN detalles_pedido dp
                ON p.id_pedido = dp.id_pedido
            INNER JOIN productos pr
                ON dp.id_producto = pr.id_producto
            ORDER BY p.id_pedido DESC
        """)

        pedidos = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "pedidos_admin.html",
        pedidos=pedidos
    )


# =====================================================
# ADMIN - CATEGORÍA CREAR
# =====================================================

@app.route(
    "/admin/categorias/crear",
    methods=["POST"]
)
@administrador_requerido
def categoria_crear():

    nombre = request.form.get(
        "nombre",
        ""
    ).strip()

    descripcion = request.form.get(
        "descripcion",
        ""
    ).strip()

    if not nombre:

        return "El nombre de la categoría es obligatorio."

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            INSERT INTO categorias
            (
                nombre,
                descripcion
            )
            VALUES (%s, %s)
        """, (
            nombre,
            descripcion
        ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL CREAR CATEGORIA:",
            error
        )

        return "No se pudo crear la categoría."

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin")
    )


# =====================================================
# ADMIN - CATEGORÍA EDITAR
# =====================================================

@app.route(
    "/admin/categorias/editar/<int:id_categoria>",
    methods=["POST"]
)
@administrador_requerido
def categoria_editar(id_categoria):

    nombre = request.form.get(
        "nombre",
        ""
    ).strip()

    descripcion = request.form.get(
        "descripcion",
        ""
    ).strip()

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            UPDATE categorias
            SET
                nombre = %s,
                descripcion = %s
            WHERE id_categoria = %s
        """, (
            nombre,
            descripcion,
            id_categoria
        ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL EDITAR CATEGORIA:",
            error
        )

        return "No se pudo editar la categoría."

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin")
    )


# =====================================================
# ADMIN - CATEGORÍA ELIMINAR
# =====================================================

@app.route(
    "/admin/categorias/eliminar/<int:id_categoria>",
    methods=["POST"]
)
@administrador_requerido
def categoria_eliminar(id_categoria):

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # Comprobar si tiene productos

        cursor.execute("""
            SELECT COUNT(*)
            FROM productos
            WHERE id_categoria = %s
        """, (id_categoria,))

        cantidad_productos = cursor.fetchone()[0]

        if cantidad_productos > 0:

            return (
                "No se puede eliminar la categoría "
                "porque tiene productos asociados."
            )

        cursor.execute("""
            DELETE FROM categorias
            WHERE id_categoria = %s
        """, (id_categoria,))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL ELIMINAR CATEGORIA:",
            error
        )

        return "No se pudo eliminar la categoría."
    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("admin")
    )



# =====================================================
# CARRITO
# =====================================================

@app.route("/carrito")
def carrito():

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =========================================
        # BUSCAR CARRITO
        # =========================================

        cursor.execute("""
            SELECT id_carrito
            FROM carritos
            WHERE id_usuario = %s
        """, (
            session["id_usuario"],
        ))

        carrito = cursor.fetchone()

        # =========================================
        # CREAR CARRITO SI NO EXISTE
        # =========================================

        if not carrito:

            cursor.execute("""
                INSERT INTO carritos
                (
                    id_usuario
                )
                VALUES (%s)
            """, (
                session["id_usuario"],
            ))

            id_carrito = cursor.lastrowid

            conexion.commit()

        else:

            id_carrito = carrito[0]

        # =========================================
        # PRODUCTOS
        # =========================================

        cursor.execute("""
            SELECT
                ci.id_item,
                ci.id_producto,
                p.nombre,
                p.precio,
                ci.cantidad,
                p.precio * ci.cantidad AS subtotal,
                COALESCE(i.stock_actual, 0) AS stock
            FROM carrito_items ci
            INNER JOIN productos p
                ON ci.id_producto = p.id_producto
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            WHERE ci.id_carrito = %s
        """, (
            id_carrito,
        ))

        items = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "carrito.html",
        items=items
    )


# =====================================================
# AGREGAR AL CARRITO
# =====================================================

@app.route(
    "/carrito/agregar/<int:id_producto>",
    methods=["POST"]
)
def agregar_carrito(id_producto):

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =========================================
        # COMPROBAR STOCK
        # =========================================

        cursor.execute("""
            SELECT
                p.id_producto,
                COALESCE(i.stock_actual, 0)
            FROM productos p
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            WHERE p.id_producto = %s
        """, (
            id_producto,
        ))

        producto = cursor.fetchone()

        if not producto:

            return "El producto no existe."

        stock = producto[1]

        if stock <= 0:

            return "El producto está agotado."

        # =========================================
        # BUSCAR CARRITO
        # =========================================

        cursor.execute("""
            SELECT id_carrito
            FROM carritos
            WHERE id_usuario = %s
        """, (
            session["id_usuario"],
        ))

        carrito = cursor.fetchone()

        # =========================================
        # CREAR CARRITO
        # =========================================

        if not carrito:

            cursor.execute("""
                INSERT INTO carritos
                (
                    id_usuario
                )
                VALUES (%s)
            """, (
                session["id_usuario"],
            ))

            id_carrito = cursor.lastrowid

        else:

            id_carrito = carrito[0]

        # =========================================
        # BUSCAR PRODUCTO EN CARRITO
        # =========================================

        cursor.execute("""
            SELECT
                id_item,
                cantidad
            FROM carrito_items
            WHERE id_carrito = %s
            AND id_producto = %s
        """, (
            id_carrito,
            id_producto
        ))

        item = cursor.fetchone()

        # =========================================
        # SI EXISTE
        # =========================================

        if item:

            nueva_cantidad = item[1] + 1

            if nueva_cantidad > stock:

                return (
                    "No puedes agregar más unidades "
                    "de las disponibles."
                )

            cursor.execute("""
                UPDATE carrito_items
                SET cantidad = cantidad + 1
                WHERE id_item = %s
            """, (
                item[0],
            ))

        # =========================================
        # SI NO EXISTE
        # =========================================

        else:

            cursor.execute("""
                INSERT INTO carrito_items
                (
                    id_carrito,
                    id_producto,
                    cantidad
                )
                VALUES (%s, %s, %s)
            """, (
                id_carrito,
                id_producto,
                1
            ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL AGREGAR AL CARRITO:",
            error
        )

        return (
            "No se pudo agregar el producto "
            "al carrito."
        )

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("carrito")
    )


# =====================================================
# ELIMINAR DEL CARRITO
# =====================================================

@app.route(
    "/carrito/eliminar/<int:id_item>",
    methods=["POST"]
)
def eliminar_carrito(id_item):

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            DELETE FROM carrito_items
            WHERE id_item = %s
            AND id_carrito IN (
                SELECT id_carrito
                FROM carritos
                WHERE id_usuario = %s
            )
        """, (
            id_item,
            session["id_usuario"]
        ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL ELIMINAR DEL CARRITO:",
            error
        )

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("carrito")
    )


# =====================================================
# VACIAR CARRITO
# =====================================================

@app.route(
    "/carrito/vaciar",
    methods=["POST"]
)
def vaciar_carrito():

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            DELETE FROM carrito_items
            WHERE id_carrito IN (
                SELECT id_carrito
                FROM carritos
                WHERE id_usuario = %s
            )
        """, (
            session["id_usuario"],
        ))

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR AL VACIAR CARRITO:",
            error
        )

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("carrito")
    )


# =====================================================
# PÁGINA DE PAGO
# =====================================================

@app.route("/pago")
def pago():

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT
                ci.id_producto,
                p.nombre,
                p.precio,
                ci.cantidad,
                p.precio * ci.cantidad AS subtotal,
                COALESCE(i.stock_actual, 0) AS stock
            FROM carrito_items ci
            INNER JOIN carritos c
                ON ci.id_carrito = c.id_carrito
            INNER JOIN productos p
                ON ci.id_producto = p.id_producto
            LEFT JOIN inventario i
                ON p.id_producto = i.id_producto
            WHERE c.id_usuario = %s
        """, (
            session["id_usuario"],
        ))

        items = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    if not items:

        return redirect(
            url_for("carrito")
        )

    total = sum(
        item[4]
        for item in items
    )

    return render_template(
        "pago.html",
        items=items,
        total=total
    )

# =====================================================
# PROCESAR PAGO
# =====================================================

@app.route(
    "/pago/procesar",
    methods=["POST"]
)
def procesar_pago():

    if "id_usuario" not in session:

        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        # =============================================
        # BUSCAR CARRITO
        # =============================================

        cursor.execute("""
            SELECT id_carrito
            FROM carritos
            WHERE id_usuario = %s
        """, (
            session["id_usuario"],
        ))

        carrito = cursor.fetchone()

        if not carrito:

            return "No existe un carrito."

        id_carrito = carrito[0]

        # =============================================
        # OBTENER PRODUCTOS DEL CARRITO
        # =============================================

        cursor.execute("""
            SELECT
                ci.id_producto,
                ci.cantidad,
                p.precio,
                COALESCE(i.stock_actual, 0) AS stock
            FROM carrito_items ci

            INNER JOIN productos p
                ON ci.id_producto = p.id_producto

            LEFT JOIN inventario i
                ON ci.id_producto = i.id_producto

            WHERE ci.id_carrito = %s
        """, (
            id_carrito,
        ))

        items = cursor.fetchall()

        if not items:

            return "El carrito está vacío."

        # =============================================
        # COMPROBAR STOCK Y CALCULAR TOTAL
        # =============================================

        total = 0

        for item in items:

            cantidad = item[1]
            precio = item[2]
            stock = item[3]

            if stock < cantidad:

                return (
                    "No hay suficiente stock "
                    "para uno de los productos."
                )

            total += precio * cantidad

        # =============================================
        # CREAR PEDIDO
        # =============================================

        cursor.execute("""
            INSERT INTO pedidos
            (
                id_usuario,
                total,
                estado
            )
            VALUES (%s, %s, %s)
        """, (
            session["id_usuario"],
            total,
            "pagado"
        ))

        id_pedido = cursor.lastrowid

        # =============================================
        # OBTENER DIRECCIÓN DEL USUARIO
        # =============================================

        cursor.execute("""
            SELECT direccion
            FROM usuarios
            WHERE id_usuario = %s
        """, (
            session["id_usuario"],
        ))

        usuario = cursor.fetchone()

        direccion = ""

        if usuario and usuario[0]:
            direccion = usuario[0]

        # =============================================
        # OBTENER CIUDAD
        # =============================================

        ciudad = request.form.get(
            "ciudad",
            "Bogotá"
        ).strip()

        if not ciudad:
            ciudad = "Bogotá"

        # =============================================
        # CREAR ENVÍO
        # =============================================

        print("========== CREANDO ENVÍO ==========")
        print("ID PEDIDO:", id_pedido)
        print("DIRECCIÓN:", direccion)
        print("CIUDAD:", ciudad)

        cursor.execute("""
            INSERT INTO envios
            (
                id_pedido,
                direccion_envio,
                ciudad,
                estado
            )
            VALUES (%s, %s, %s, %s)
        """, (
            id_pedido,
            direccion,
            ciudad,
            "pendiente"
        ))

        # =============================================
        # CREAR DETALLES Y DESCONTAR INVENTARIO
        # =============================================

        for item in items:

            id_producto = item[0]
            cantidad = item[1]
            precio = item[2]

            # -----------------------------------------
            # CREAR DETALLE DEL PEDIDO
            # -----------------------------------------

            cursor.execute("""
                INSERT INTO detalles_pedido
                (
                    id_pedido,
                    id_producto,
                    cantidad,
                    precio_unitario
                )
                VALUES (%s, %s, %s, %s)
            """, (
                id_pedido,
                id_producto,
                cantidad,
                precio
            ))

            # -----------------------------------------
            # DESCONTAR INVENTARIO
            # -----------------------------------------

            cursor.execute("""
                UPDATE inventario
                SET stock_actual = stock_actual - %s
                WHERE id_producto = %s
                AND stock_actual >= %s
            """, (
                cantidad,
                id_producto,
                cantidad
            ))

            if cursor.rowcount == 0:

                raise Exception(
                    "No hay suficiente inventario."
                )

        # =============================================
        # REGISTRAR PAGO
        # =============================================

        metodo_pago = request.form.get(
            "metodo_pago",
            "prueba"
        )

        cursor.execute("""
            INSERT INTO pagos
            (
                id_pedido,
                id_usuario,
                monto,
                metodo_pago,
                estado
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            id_pedido,
            session["id_usuario"],
            total,
            metodo_pago,
            "aprobado"
        ))

        # =============================================
        # VACIAR CARRITO
        # =============================================

        cursor.execute("""
            DELETE FROM carrito_items
            WHERE id_carrito = %s
        """, (
            id_carrito,
        ))

        # =============================================
        # GUARDAR TODO
        # =============================================

        conexion.commit()

    except Exception as error:

        conexion.rollback()

        print(
            "ERROR EN PAGO:",
            error
        )

        return (
            "No se pudo procesar el pago. "
            "Revisa la terminal de Flask."
        )

    finally:

        cursor.close()
        conexion.close()

    return redirect(
        url_for("pedidos")
    )

# =====================================================
# MIS PEDIDOS — CLIENTE
# =====================================================

@app.route("/pedidos")
def pedidos():

    if "id_usuario" not in session:
        return redirect(
            url_for("login")
        )

    conexion = obtener_conexion()
    cursor = conexion.cursor()

    try:

        cursor.execute("""
            SELECT
                p.id_pedido,
                p.fecha_pedido,
                p.total,
                p.estado,
                COALESCE(e.estado, 'pendiente') AS estado_envio,
                COALESCE(e.direccion_envio, '') AS direccion_envio,
                COALESCE(e.ciudad, '') AS ciudad
            FROM pedidos p
            LEFT JOIN envios e
                ON p.id_pedido = e.id_pedido
            WHERE p.id_usuario = %s
            ORDER BY p.fecha_pedido DESC
        """, (
            session["id_usuario"],
        ))

        pedidos = cursor.fetchall()

    finally:

        cursor.close()
        conexion.close()

    return render_template(
        "pedidos.html",
        pedidos=pedidos
    )


# =====================================================
# EJECUTAR SERVIDOR
# =====================================================

if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )