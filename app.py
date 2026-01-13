import sqlite3
import hashlib
import os
import binascii
from datetime import datetime

DB_NAME = "tienda.db"

# CONEXIÓN BASE DE DATOS
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nombre TEXT NOT NULL,
        email TEXT NOT NULL UNIQUE,
        contrasena TEXT NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS productos (
        id INTEGER PRIMARY KEY,
        nombre TEXT NOT NULL,
        precio REAL NOT NULL CHECK(precio >= 0)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedidos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id INTEGER NOT NULL,
        fecha TEXT NOT NULL,
        total REAL NOT NULL CHECK(total >= 0),
        FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pedido_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pedido_id INTEGER NOT NULL,
        producto_id INTEGER NOT NULL,
        cantidad INTEGER NOT NULL CHECK(cantidad > 0),
        subtotal REAL NOT NULL CHECK(subtotal >= 0),
        FOREIGN KEY (pedido_id) REFERENCES pedidos(id),
        FOREIGN KEY (producto_id) REFERENCES productos(id)
    )
    """)

    # Seed de productos (solo si no hay)
    cur.execute("SELECT COUNT(*) AS c FROM productos")
    if cur.fetchone()["c"] == 0:
        cur.executemany(
            "INSERT INTO productos (id, nombre, precio) VALUES (?, ?, ?)",
            [
                (1, "Camiseta", 20),
                (2, "Pantalón", 35),
                (3, "Zapatillas", 50),
            ]
        )

    conn.commit()
    conn.close()


def hash_password(password: str, iterations: int = 100_000):
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return f"pbkdf2_sha256${iterations}${binascii.hexlify(salt).decode()}${binascii.hexlify(dk).decode()}"


def verify_password(stored_password: str, password: str):
    try:
        algo, iterations, salt_hex, hash_hex = stored_password.split("$")
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iterations)
        salt = binascii.unhexlify(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
        return binascii.hexlify(dk).decode() == hash_hex
    except Exception:
        return False


# -------------------------
# FUNCIONES APP
# -------------------------
def registrar_usuario():
    print("=== Registrar Usuario ===")
    nombre = input("Nombre: ").strip()
    email = input("Email: ").strip().lower()
    contrasena = input("Contraseña: ").strip()

    if not nombre or not email or not contrasena:
        print("Faltan datos. Inténtalo de nuevo.\n")
        return

    conn = get_conn()
    cur = conn.cursor()
    try:
        hashed = hash_password(contrasena)
        cur.execute(
            "INSERT INTO usuarios (nombre, email, contrasena) VALUES (?, ?, ?)",
            (nombre, email, hashed)
        )
        conn.commit()
        print(f"Usuario {nombre} registrado con éxito.\n")
    except sqlite3.IntegrityError:
        print("Ese email ya está registrado.\n")
    finally:
        conn.close()


def mostrar_productos():
    print("=== Productos Disponibles ===")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, precio FROM productos ORDER BY id")
    productos = cur.fetchall()
    conn.close()

    for p in productos:
        print(f"{p['id']}: {p['nombre']} - ${p['precio']}")
    print()


def obtener_usuario_por_email(email: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, email FROM usuarios WHERE email = ?", (email,))
    u = cur.fetchone()
    conn.close()
    return u


def autenticar_usuario(email: str, password: str):
    """Devuelve el usuario si las credenciales son correctas, o None si fallan."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, email, contrasena FROM usuarios WHERE email = ?", (email,))
    u = cur.fetchone()
    conn.close()
    if not u:
        return None
    if verify_password(u["contrasena"], password):
        return u
    return None


def obtener_producto_por_id(producto_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT id, nombre, precio FROM productos WHERE id = ?", (producto_id,))
    p = cur.fetchone()
    conn.close()
    return p


def crear_pedido():
    # Comprobar que hay usuarios
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM usuarios")
    if cur.fetchone()["c"] == 0:
        conn.close()
        print("No hay usuarios registrados. Regístrate primero.\n")
        return
    conn.close()

    email = input("Introduce tu email para iniciar pedido: ").strip().lower()
    contrasena = input("Contraseña: ").strip()
    usuario = autenticar_usuario(email, contrasena)
    if not usuario:
        print("Email o contraseña incorrectos.\n")
        return

    mostrar_productos()

    try:
        producto_id = int(input("ID del producto a pedir: ").strip())
        cantidad = int(input("Cantidad: ").strip())
    except ValueError:
        print("Entrada no válida. Debes introducir números.\n")
        return

    if cantidad <= 0:
        print("La cantidad debe ser mayor que 0.\n")
        return

    producto = obtener_producto_por_id(producto_id)
    if not producto:
        print("Producto no encontrado.\n")
        return

    subtotal = float(producto["precio"]) * cantidad
    fecha = datetime.now().isoformat(timespec="seconds")

    # Insertar pedido + item (transacción)
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO pedidos (usuario_id, fecha, total) VALUES (?, ?, ?)",
            (usuario["id"], fecha, subtotal)
        )
        pedido_id = cur.lastrowid

        cur.execute(
            "INSERT INTO pedido_items (pedido_id, producto_id, cantidad, subtotal) VALUES (?, ?, ?, ?)",
            (pedido_id, producto["id"], cantidad, subtotal)
        )

        conn.commit()
        print(f"Pedido de {cantidad} x {producto['nombre']} realizado con éxito. Total: ${subtotal}\n")
    except Exception as e:
        conn.rollback()
        print(f"Error creando pedido: {e}\n")
    finally:
        conn.close()


def mostrar_pedidos():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) AS c FROM pedidos")
    if cur.fetchone()["c"] == 0:
        conn.close()
        print("No hay pedidos realizados.\n")
        return

    print("=== Pedidos Realizados ===")
    cur.execute("""
        SELECT p.id AS pedido_id, u.nombre AS usuario, u.email AS email,
        p.fecha AS fecha, pr.nombre AS producto,
        i.cantidad AS cantidad, i.subtotal AS total
        FROM pedidos p
        JOIN usuarios u ON u.id = p.usuario_id
        JOIN pedido_items i ON i.pedido_id = p.id
        JOIN productos pr ON pr.id = i.producto_id
        ORDER BY p.id DESC
    """)
    rows = cur.fetchall()
    conn.close()

    for r in rows:
        print(f"#{r['pedido_id']} | {r['usuario']} ({r['email']}) | {r['producto']} x {r['cantidad']} = ${r['total']} | {r['fecha']}")
    print()


def menu():
    while True:
        print("=== Tienda Online (BD) ===")
        print("1. Registrar Usuario")
        print("2. Mostrar Productos")
        print("3. Realizar Pedido")
        print("4. Ver Pedidos")
        print("5. Salir")
        opcion = input("Elige una opción: ").strip()
        print()

        if opcion == "1":
            registrar_usuario()
        elif opcion == "2":
            mostrar_productos()
        elif opcion == "3":
            crear_pedido()
        elif opcion == "4":
            mostrar_pedidos()
        elif opcion == "5":
            print("¡Gracias por usar la tienda online!")
            break
        else:
            print("Opción no válida.\n")


if __name__ == "__main__":
    init_db()
    menu()
