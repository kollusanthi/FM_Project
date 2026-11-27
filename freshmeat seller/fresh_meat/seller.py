from flask import (
    Flask, send_from_directory, jsonify, request,
    session
)
from werkzeug.utils import secure_filename
import os
import secrets
from functools import wraps
from dotenv import load_dotenv
import mysql.connector
from mysql.connector import Error as MySQLError
from mysql.connector import IntegrityError as MySQLIntegrityError
from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)
from werkzeug.utils import secure_filename

from datetime import timedelta
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Load .env BEFORE reading secret key
load_dotenv(os.path.join(BASE_DIR, ".env"))

app = Flask(__name__)

app.secret_key = os.getenv("SECRET_KEY")

if not app.secret_key:
    raise RuntimeError("FRESHMEAT_SECRET_KEY is missing in .env")

app.config["SESSION_COOKIE_NAME"] = "freshmeat_session"
app.config["SESSION_COOKIE_PATH"] = "/"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = False

app.permanent_session_lifetime = timedelta(days=7)

FRONTEND_FOLDER = os.path.join(BASE_DIR, "frontend")
UPLOAD_FOLDER = os.path.join(FRONTEND_FOLDER, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
# ---------------- MYSQL DATABASE ----------------

MYSQL_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", ""),
    "database": os.environ.get(
    "DB_NAME",
    "freshmeat_integrated"
),
    "autocommit": False
}


def get_db():
    return mysql.connector.connect(**MYSQL_CONFIG)



def setup_database():
    connection = get_db()
    cursor = connection.cursor()

    try:
        # 1. SELLERS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sellers (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                full_name VARCHAR(255) NOT NULL,
                shop_name VARCHAR(255) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                email VARCHAR(255) NOT NULL UNIQUE,
                password VARCHAR(255) NOT NULL,
                business_type VARCHAR(255),
                fssai_number VARCHAR(100),
                pan_number VARCHAR(100),
                city VARCHAR(100),
                state VARCHAR(100),
                pincode VARCHAR(20),
                address TEXT,
                status VARCHAR(50) DEFAULT 'Active',
                reason VARCHAR(500) DEFAULT '',
                aadhaar_file VARCHAR(500),
                pan_file VARCHAR(500),
                fssai_file VARCHAR(500),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 2. PRODUCTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                seller_id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT,
                category VARCHAR(100),
                price DECIMAL(10,2) NOT NULL,
                quantity DECIMAL(10,2) NOT NULL DEFAULT 0,
                quantity_unit VARCHAR(30) DEFAULT 'kg',
                image VARCHAR(500) DEFAULT '',
                status VARCHAR(50) DEFAULT 'Active',
                reason VARCHAR(500) DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL,
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)

        # 3. ORDERS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                customer_name VARCHAR(255) NOT NULL,
                customer_phone VARCHAR(20) NOT NULL,
                customer_address TEXT NOT NULL,
                total_amount DECIMAL(10,2) NOT NULL DEFAULT 0,
                order_status VARCHAR(50) DEFAULT 'Pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 4. ORDER ITEMS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS order_items (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_id BIGINT NOT NULL,
                product_id BIGINT NOT NULL,
                seller_id BIGINT NOT NULL,
                quantity DECIMAL(10,2) NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)

        # 5. SELLER NOTIFICATIONS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                seller_id BIGINT NOT NULL,
                title VARCHAR(255) NOT NULL,
                message TEXT NOT NULL,
                is_read TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)

        # 6. RETURN REQUESTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS return_requests (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_id BIGINT NOT NULL,
                order_item_id BIGINT NOT NULL,
                product_id BIGINT NOT NULL,
                seller_id BIGINT NOT NULL,
                customer_name VARCHAR(255) NOT NULL,
                customer_phone VARCHAR(20) NOT NULL,
                customer_address TEXT,
                quantity DECIMAL(10,2) NOT NULL,
                reason TEXT NOT NULL,
                status VARCHAR(50) DEFAULT 'Requested',
                seller_note TEXT,
                item_condition VARCHAR(100) DEFAULT '',
                rider_name VARCHAR(255) DEFAULT '',
                rider_phone VARCHAR(20) DEFAULT '',
                rider_status VARCHAR(50) DEFAULT 'Not Assigned',
                restocked TINYINT(1) DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP NULL,
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (order_item_id) REFERENCES order_items(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)

        # 7. PRODUCT REVIEWS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                order_id BIGINT NOT NULL,
                product_id BIGINT NOT NULL,
                seller_id BIGINT NOT NULL,
                customer_name VARCHAR(255) NOT NULL,
                rating INT NOT NULL,
                comment TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_order_product (order_id, product_id),
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (product_id) REFERENCES products(id),
                FOREIGN KEY (seller_id) REFERENCES sellers(id)
            )
        """)

        # IMPORTANT:
        # Do NOT create another riders table.
        # The existing Rider application owns that table.
        # Its primary key is riders.rider_id.

        # 8. SHARED RIDER ASSIGNMENTS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rider_assignments (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                seller_id BIGINT NOT NULL,
                order_id BIGINT NOT NULL,
                rider_id BIGINT NOT NULL,
                delivery_status VARCHAR(50) DEFAULT 'Assigned',
                rejection_reason VARCHAR(500) DEFAULT '',
                assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                picked_up_at TIMESTAMP NULL,
                delivered_at TIMESTAMP NULL,

                FOREIGN KEY (seller_id) REFERENCES sellers(id),
                FOREIGN KEY (order_id) REFERENCES orders(id),
                FOREIGN KEY (rider_id) REFERENCES riders(rider_id)
            )
        """)

        # 9. SELLER ORDER ACTIONS
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS seller_order_actions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                seller_id BIGINT NOT NULL,
                order_id BIGINT NOT NULL,
                status VARCHAR(50) DEFAULT 'Pending',

                UNIQUE KEY unique_seller_order (seller_id, order_id),

                FOREIGN KEY (seller_id) REFERENCES sellers(id),
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
        """)

        connection.commit()
        print("Seller tables and shared Rider assignments are ready!")

    except MySQLError:
        connection.rollback()
        raise

    finally:
        cursor.close()
        connection.close()


# ---------------- COMMON HELPERS ----------------



def seller_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        seller_id = session.get("seller_id")

        if not seller_id:
            return jsonify({
                "error": "Please log in first."
            }), 401

        connection = get_db()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT id, status FROM sellers WHERE id = %s",
                (seller_id,)
            )

            seller = cursor.fetchone()

        finally:
            cursor.close()
            connection.close()

        if not seller:
            session.pop("seller_id", None)
            return jsonify({
                "error": "Seller account not found."
            }), 403

        # Check Admin approval
        status = str(seller.get("status", "")).strip()

        if status != "Approved":
            session.pop("seller_id", None)
            return jsonify({
                "error": "Your seller account is not approved by Admin yet.",
                "status": status
            }), 403

        return function(*args, **kwargs)

    return wrapper


# Get currently logged-in seller ID
def get_seller_id():
    return session.get("seller_id")
def request_value(key, default=None):
    if request.is_json:
        data = request.get_json(silent=True) or {}
        return data.get(key, default)

    return request.form.get(key, default)

def save_product_image(image_file):
    if not image_file or not image_file.filename:
        return ""

    allowed_extensions = {"png", "jpg", "jpeg", "webp"}

    filename = secure_filename(image_file.filename)

    if "." not in filename:
        raise ValueError("Invalid image file.")

    extension = filename.rsplit(".", 1)[1].lower()

    if extension not in allowed_extensions:
        raise ValueError("Only PNG, JPG, JPEG and WEBP images are allowed.")

    unique_filename = f"{secrets.token_hex(16)}.{extension}"

    image_path = os.path.join(
        UPLOAD_FOLDER,
        unique_filename
    )

    image_file.save(image_path)

    return unique_filename


# ---------------- FRONTEND ----------------

@app.route("/")
def home():
    return send_from_directory(FRONTEND_FOLDER, "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(FRONTEND_FOLDER, filename)


@app.route("/uploads/<path:filename>")
def uploaded_images(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/test")
def test():
    return jsonify({
        "message": "FreshMeet seller backend is running successfully!"
    })
# ---------------- SELLER REGISTRATION ----------------

@app.route("/api/seller/register", methods=["POST"])
def register_seller():
    data = request.get_json(silent=True) or {}

    required = [
        "name", "shop", "phone", "email",
        "password", "category", "city", "state",
        "address", "pincode"
    ]

    if any(not str(data.get(field, "")).strip() for field in required):
        return jsonify({"error": "Please fill all required fields."}), 400

    if len(data["password"]) < 6:
        return jsonify({
            "error": "Password must contain at least 6 characters."
        }), 400

    connection = get_db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            INSERT INTO sellers (
                full_name, shop_name, phone, email, password,
                business_type, fssai_number, pan_number,
                city, state, pincode, address, status, reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, 'Pending', '')
        """, (
            data["name"].strip(),
            data["shop"].strip(),
            data["phone"].strip(),
            data["email"].strip().lower(),
            generate_password_hash(data["password"]),
            data["category"].strip(),
            data.get("fssai", ""),
            data.get("pan", ""),
            data["city"].strip(),
            data["state"].strip(),
            data["pincode"].strip(),
            data["address"].strip()
        ))

        connection.commit()

        return jsonify({
            "message": "Registration successful. You can now log in to your seller portal."
        }), 201

    except MySQLIntegrityError:
        connection.rollback()
        return jsonify({
            "error": "This email is already registered."
        }), 409

    except MySQLError as error:
        connection.rollback()
        print("Registration error:", error)
        return jsonify({
            "error": "Database error during registration."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- SELLER LOGIN ----------------


@app.route("/api/seller/login", methods=["POST"])
def seller_login():
    data = request.get_json(silent=True) or {}

    email = str(data.get("email", "")).strip().lower()
    password = str(data.get("password", ""))

    if not email or not password:
        return jsonify({
            "error": "Enter your email and password."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT * FROM sellers WHERE email = %s",
            (email,)
        )
        seller = cursor.fetchone()

        # Check email and password
        if not seller or not check_password_hash(
            seller["password"], password
        ):
            return jsonify({
                "error": "Invalid email or password."
            }), 401

        # Check Admin approval status
        status = str(seller.get("status", "")).strip()

        if status == "Pending":
            return jsonify({
                "error": "Your seller account is awaiting Admin approval."
            }), 403

        if status == "Rejected":
            return jsonify({
                "error": "Your seller account has been rejected. Please contact Admin."
            }), 403

        if status != "Approved":
            return jsonify({
                "error": "Your seller account is not approved yet. Please contact Admin."
            }), 403

        # Allow login only after Admin approval
        session["seller_id"] = seller["id"]
        session.permanent = True

        return jsonify({
            "message": "Login successful.",
            "seller": {
                "id": seller["id"],
                "name": seller["full_name"],
                "shop": seller["shop_name"],
                "email": seller["email"]
            }
        })

    except MySQLError as error:
        print("Login error:", error)
        return jsonify({"error": "Unable to log in."}), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- SELLER LOGOUT ----------------

@app.route("/api/seller/logout", methods=["POST"])
def seller_logout():
    session.pop("seller_id", None)

    return jsonify({
        "message": "Logged out successfully."
    })

# ---------------- SELLER PROFILE ----------------

@app.route("/api/seller/me", methods=["GET"])
@seller_required
def seller_profile():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                id, full_name, phone, email, shop_name,
                business_type, address, city, state,
                pincode, fssai_number, pan_number, status, created_at
            FROM sellers
            WHERE id = %s
        """, (get_seller_id(),))

        seller = cursor.fetchone()

        return jsonify({"seller": seller})

    except MySQLError as error:
        print("Profile error:", error)
        return jsonify({"error": "Unable to load profile."}), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- DASHBOARD ANALYTICS ----------------

@app.route("/api/seller/stats", methods=["GET"])
@seller_required
def seller_stats():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    seller_id = get_seller_id()

    try:
        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM products
            WHERE seller_id = %s
        """, (seller_id,))
        products = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(DISTINCT order_id) AS total
            FROM order_items
            WHERE seller_id = %s
        """, (seller_id,))
        orders = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(DISTINCT oi.order_id) AS total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE oi.seller_id = %s
            AND LOWER(TRIM(o.order_status)) = 'pending'
        """, (seller_id,))
        pending = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM notifications
            WHERE seller_id = %s AND is_read = 0
        """, (seller_id,))
        notifications = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COALESCE(SUM(oi.quantity * oi.price), 0) AS total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE oi.seller_id = %s
            AND LOWER(TRIM(o.order_status)) = 'delivered'
        """, (seller_id,))
        revenue = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COALESCE(SUM(oi.quantity * oi.price), 0) AS total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE oi.seller_id = %s
            AND LOWER(TRIM(o.order_status)) = 'delivered'
            AND DATE(o.created_at) = CURDATE()
        """, (seller_id,))
        today_sales = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT COALESCE(SUM(oi.quantity * oi.price), 0) AS total
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            WHERE oi.seller_id = %s
            AND LOWER(TRIM(o.order_status)) = 'delivered'
            AND YEAR(o.created_at) = YEAR(CURDATE())
            AND MONTH(o.created_at) = MONTH(CURDATE())
        """, (seller_id,))
        month_sales = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT id, name, category, price, quantity
            FROM products
            WHERE seller_id = %s AND quantity <= 5
            ORDER BY quantity ASC
        """, (seller_id,))
        low_stock_products = cursor.fetchall()

        cursor.execute("""
            SELECT
                DATE(o.created_at) AS sale_date,
                COALESCE(SUM(oi.quantity * oi.price), 0) AS total
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE oi.seller_id = %s
            AND LOWER(TRIM(o.order_status)) = 'delivered'
            AND DATE(o.created_at) >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
            GROUP BY DATE(o.created_at)
            ORDER BY sale_date ASC
        """, (seller_id,))
        chart_rows = cursor.fetchall()

        sales_chart = [
            {
                "date": str(row["sale_date"]),
                "amount": float(row["total"])
            }
            for row in chart_rows
        ]

        return jsonify({
            "products": products,
            "orders": orders,
            "pending": pending,
            "notifications": notifications,
            "revenue": float(revenue),
            "today_sales": float(today_sales),
            "month_sales": float(month_sales),
            "low_stock_count": len(low_stock_products),
            "low_stock_products": low_stock_products,
            "sales_chart": sales_chart
        })

    except MySQLError as error:
        print("Dashboard error:", error)
        return jsonify({
            "error": "Unable to load dashboard analytics."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- PRODUCT MANAGEMENT ----------------

@app.route("/api/seller/products", methods=["GET", "POST"])
@seller_required
def seller_products():
    seller_id = get_seller_id()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    if request.method == "GET":
        try:
            cursor.execute("""
                SELECT * FROM products
                WHERE seller_id = %s
                ORDER BY id DESC
            """, (seller_id,))

            rows = cursor.fetchall()
            return jsonify({"products": rows})

        except MySQLError as error:
            print("Get products error:", error)
            return jsonify({"error": "Unable to load products."}), 500

        finally:
            cursor.close()
            connection.close()

    # POST Method - Safe extraction with fallbacks
    name = str(request_value("name") or "").strip()
    price_val = request_value("price")
    quantity_val = request_value("quantity")
    quantity_unit = str(request_value("quantity_unit", "kg")).strip().lower()

    if not name or price_val in (None, "") or quantity_val in (None, ""):
        cursor.close()
        connection.close()
        return jsonify({"error": "Enter product name, price and quantity."}), 400

    try:
        price = float(price_val)
        quantity = float(quantity_val)

        if price < 0 or quantity < 0:
            raise ValueError("Price and quantity cannot be negative.")

        if quantity_unit not in ("kg", "grams"):
            raise ValueError("Select kg or grams.")

        # Save image securely
        image = save_product_image(request.files.get("image"))

        cursor.execute("""
            INSERT INTO products (
                seller_id, name, description, category,
                price, quantity, quantity_unit, image, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Active')
        """, (
            seller_id,
            name,
            request_value("description", ""),
            request_value("category", ""),
            price,
            quantity,
            quantity_unit,
            image
        ))

        connection.commit()
        return jsonify({"message": "Product added successfully."}), 201

    except ValueError as error:
        connection.rollback()
        return jsonify({"error": str(error)}), 400

    except MySQLError as error:
        connection.rollback()
        print("Add product error:", error)
        return jsonify({"error": "Unable to save product."}), 500

    finally:
        cursor.close()
        connection.close()


@app.route("/api/seller/products/<int:product_id>", methods=["PUT", "DELETE"])
@seller_required
def manage_product(product_id):
    seller_id = get_seller_id()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT * FROM products
            WHERE id = %s AND seller_id = %s
        """, (product_id, seller_id))

        product = cursor.fetchone()

        if not product:
            return jsonify({"error": "Product not found."}), 404

        if request.method == "DELETE":
            cursor.execute("""
                DELETE FROM products
                WHERE id = %s AND seller_id = %s
            """, (product_id, seller_id))

            connection.commit()

            return jsonify({
                "message": "Product deleted successfully."
            })

        name = str(
            request_value("name", product["name"])
        ).strip()

        price = float(
            request_value("price", product["price"])
        )

        quantity = float(
            request_value("quantity", product["quantity"])
        )

        quantity_unit = str(
            request_value(
                "quantity_unit",
                product["quantity_unit"] or "kg"
            )
        ).strip().lower()

        if not name or price < 0 or quantity < 0:
            raise ValueError("Enter valid product details.")

        if quantity_unit not in ("kg", "grams"):
            raise ValueError("Select kg or grams.")

        image = product["image"] or ""
        uploaded_file = request.files.get("image")

        if uploaded_file and uploaded_file.filename:
            image = save_product_image(uploaded_file)

        cursor.execute("""
            UPDATE products
            SET name = %s,
                description = %s,
                category = %s,
                price = %s,
                quantity = %s,
                quantity_unit = %s,
                image = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND seller_id = %s
        """, (
            name,
            request_value(
                "description",
                product["description"] or ""
            ),
            request_value(
                "category",
                product["category"] or ""
            ),
            price,
            quantity,
            quantity_unit,
            image,
            product_id,
            seller_id
        ))

        connection.commit()

        return jsonify({
            "message": "Product updated successfully."
        })

    except (ValueError, TypeError) as error:
        connection.rollback()
        return jsonify({"error": str(error)}), 400

    except MySQLError as error:
        connection.rollback()
        print("Manage product error:", error)
        return jsonify({"error": "Unable to manage product."}), 500

    finally:
        cursor.close()
        connection.close()
       
# ---------------- SELLER ORDERS ----------------

# ---------------- SELLER ORDERS ----------------

@app.route("/api/seller/orders", methods=["GET"])
@seller_required
def seller_orders():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    seller_id = get_seller_id()

    try:
        cursor.execute("""
            SELECT
                o.id,
                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount,
                o.order_status,
                o.created_at,
                GROUP_CONCAT(
                    CONCAT(p.name, ' x ', oi.quantity)
                    SEPARATOR ', '
                ) AS items_summary,
                COALESCE(soa.status, 'Pending') AS seller_status
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            JOIN products p ON p.id = oi.product_id
            LEFT JOIN seller_order_actions soa
                ON soa.order_id = o.id
                AND soa.seller_id = %s
            WHERE oi.seller_id = %s
            GROUP BY
                o.id, o.customer_name, o.customer_phone,
                o.customer_address, o.total_amount,
                o.order_status, o.created_at, soa.status
            ORDER BY o.id DESC
        """, (seller_id, seller_id))

        return jsonify({"orders": cursor.fetchall()})

    except MySQLError as error:
        print("Seller orders error:", error)
        return jsonify({"error": "Unable to load orders."}), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- ACCEPT SELLER ORDER ----------------

@app.route(
    "/api/seller/orders/<int:order_id>/accept",
    methods=["POST"]
)
@seller_required
def accept_seller_order(order_id):
    seller_id = get_seller_id()
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        # Check that this order contains products belonging to this Seller.
        cursor.execute("""
            SELECT id
            FROM order_items
            WHERE order_id = %s
              AND seller_id = %s
            LIMIT 1
        """, (order_id, seller_id))

        if not cursor.fetchone():
            return jsonify({"error": "Order not found."}), 404

        # Save or update this Seller's decision.
        cursor.execute("""
            INSERT INTO seller_order_actions (
                seller_id, order_id, status
            )
            VALUES (%s, %s, 'Accepted')
            ON DUPLICATE KEY UPDATE status = 'Accepted'
        """, (seller_id, order_id))

        connection.commit()

        return jsonify({
            "message": "Order accepted successfully."
        })

    except MySQLError as error:
        connection.rollback()
        print("Accept order error:", error)
        return jsonify({
            "error": "Unable to accept order."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ================= RIDER MANAGEMENT =================


# ---------------- GET AVAILABLE RIDERS ----------------

@app.route("/api/seller/riders", methods=["GET"])
@seller_required
def get_riders():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                r.rider_id,
                r.full_name AS rider_name,
                r.phone,
                r.vehicle_number,
                r.status,
                r.verification_submitted,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM rider_assignments ra
                        WHERE ra.rider_id = r.rider_id
                          AND ra.delivery_status IN (
                              'Assigned',
                              'Accepted',
                              'Picked Up',
                              'On the Way'
                          )
                    )
                    THEN 'Busy'
                    ELSE 'Available'
                END AS availability
            FROM riders r
            WHERE r.status = 'Approved'
              AND r.verification_submitted = 1
            ORDER BY r.rider_id DESC
        """)

        return jsonify({"riders": cursor.fetchall()})

    except MySQLError as error:
        print("Get riders error:", error)
        return jsonify({"error": "Unable to load riders."}), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- ADD RIDER ----------------

@app.route("/api/seller/riders", methods=["POST"])
@seller_required
def add_rider():
    return jsonify({
        "error": "Rider accounts must register through the Rider application."
    }), 403


# ---------------- ASSIGN RIDER TO ORDER ----------------

@app.route(
    "/api/seller/orders/<int:order_id>/assign-rider",
    methods=["POST"]
)
@seller_required
def assign_order_rider(order_id):
    data = request.get_json(silent=True) or {}

    try:
        rider_id = int(data.get("rider_id"))
    except (TypeError, ValueError):
        return jsonify({"error": "Select a valid rider."}), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    seller_id = get_seller_id()

    try:
        connection.start_transaction()

        # 1. Confirm that Seller accepted this order.
        cursor.execute("""
            SELECT id
            FROM seller_order_actions
            WHERE seller_id = %s
              AND order_id = %s
              AND status = 'Accepted'
            FOR UPDATE
        """, (seller_id, order_id))

        if not cursor.fetchone():
            connection.rollback()
            return jsonify({
                "error": "Accept the order before assigning a rider."
            }), 409

        # 2. Confirm that this order belongs to this Seller.
        cursor.execute("""
            SELECT id
            FROM order_items
            WHERE order_id = %s
              AND seller_id = %s
            LIMIT 1
        """, (order_id, seller_id))

        if not cursor.fetchone():
            connection.rollback()
            return jsonify({"error": "Order not found."}), 404

        # 3. Confirm that the Rider is approved and verified.
        cursor.execute("""
            SELECT rider_id, full_name
            FROM riders
            WHERE rider_id = %s
              AND status = 'Approved'
              AND verification_submitted = 1
            FOR UPDATE
        """, (rider_id,))

        rider = cursor.fetchone()

        if not rider:
            connection.rollback()
            return jsonify({
                "error": "Rider is not approved or verified."
            }), 404

        # 4. Check whether this Rider already has an active assignment.
        cursor.execute("""
            SELECT id
            FROM rider_assignments
            WHERE rider_id = %s
              AND delivery_status IN (
                  'Assigned',
                  'Accepted',
                  'Picked Up',
                  'On the Way'
              )
            LIMIT 1
            FOR UPDATE
        """, (rider_id,))

        if cursor.fetchone():
            connection.rollback()
            return jsonify({
                "error": "This rider is already busy with another order."
            }), 409

        # 5. Check whether this Seller already assigned a Rider
        # to this order.
        cursor.execute("""
            SELECT id
            FROM rider_assignments
            WHERE order_id = %s
              AND seller_id = %s
              AND delivery_status IN (
                  'Assigned',
                  'Accepted',
                  'Picked Up',
                  'On the Way'
              )
            LIMIT 1
            FOR UPDATE
        """, (order_id, seller_id))

        if cursor.fetchone():
            connection.rollback()
            return jsonify({
                "error": "A rider is already assigned to this order."
            }), 409

        # 6. Create the shared assignment.
        cursor.execute("""
            INSERT INTO rider_assignments (
                seller_id,
                order_id,
                rider_id,
                delivery_status
            )
            VALUES (%s, %s, %s, 'Assigned')
        """, (seller_id, order_id, rider_id))

        connection.commit()

        return jsonify({
            "message": "Rider assigned successfully.",
            "rider_name": rider["full_name"]
        }), 200

    except MySQLError as error:
        connection.rollback()
        print("Assign rider error:", error)
        return jsonify({
            "error": "Unable to assign rider."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- GET RIDER ASSIGNMENTS ----------------

@app.route("/api/seller/rider-assignments", methods=["GET"])
@seller_required
def get_rider_assignments():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    seller_id = get_seller_id()

    try:
        cursor.execute("""
            SELECT
                ra.id AS assignment_id,
                ra.order_id,
                ra.rider_id,
                ra.delivery_status,
                ra.rejection_reason,
                ra.assigned_at,
                ra.picked_up_at,
                ra.delivered_at,

                r.full_name AS rider_name,
                r.phone AS rider_phone,
                r.vehicle_number,

                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount,

                GROUP_CONCAT(
                    CONCAT(p.name, ' x ', oi.quantity)
                    SEPARATOR ', '
                ) AS items_summary

            FROM rider_assignments ra

            JOIN riders r
                ON r.rider_id = ra.rider_id

            JOIN orders o
                ON o.id = ra.order_id

            JOIN order_items oi
                ON oi.order_id = ra.order_id
                AND oi.seller_id = ra.seller_id

            JOIN products p
                ON p.id = oi.product_id

            WHERE ra.seller_id = %s

            GROUP BY
                ra.id,
                ra.order_id,
                ra.rider_id,
                ra.delivery_status,
                ra.rejection_reason,
                ra.assigned_at,
                ra.picked_up_at,
                ra.delivered_at,
                r.full_name,
                r.phone,
                r.vehicle_number,
                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount

            ORDER BY ra.id DESC
        """, (seller_id,))

        return jsonify({
            "assignments": cursor.fetchall()
        })

    except MySQLError as error:
        print("Get rider assignments error:", error)
        return jsonify({
            "error": "Unable to load rider assignments."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- SELLER DELIVERY STATUS ----------------
# The Rider application owns delivery-status updates.
# Seller can view the status but cannot change it.

@app.route(
    "/api/seller/rider-assignments/<int:assignment_id>/status",
    methods=["PATCH"]
)
@seller_required
def update_rider_status(assignment_id):
    return jsonify({
        "error": "Delivery status must be updated through the Rider application."
    }), 403



# ---------------- NOTIFICATIONS ----------------

@app.route("/api/seller/notifications", methods=["GET"])
@seller_required
def seller_notifications():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM notifications
            WHERE seller_id = %s
            ORDER BY id DESC
        """, (get_seller_id(),))

        rows = cursor.fetchall()
        return jsonify({"notifications": rows})

    except MySQLError as error:
        print("Notifications error:", error)
        return jsonify({
            "error": "Unable to load notifications."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route(
    "/api/seller/notifications/<int:notification_id>/read",
    methods=["PATCH"]
)
@seller_required
def mark_notification_read(notification_id):
    connection = get_db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE id = %s AND seller_id = %s
        """, (notification_id, get_seller_id()))

        connection.commit()

        if cursor.rowcount == 0:
            return jsonify({"error": "Notification not found."}), 404

        return jsonify({
            "message": "Notification marked as read."
        })

    except MySQLError as error:
        connection.rollback()
        print("Mark notification error:", error)
        return jsonify({
            "error": "Unable to update notification."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route(
    "/api/seller/notifications/read-all",
    methods=["PATCH"]
)
@seller_required
def mark_all_notifications_read():
    connection = get_db()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE notifications
            SET is_read = 1
            WHERE seller_id = %s
        """, (get_seller_id(),))

        connection.commit()

        return jsonify({
            "message": "All notifications marked as read."
        })

    except MySQLError as error:
        connection.rollback()
        print("Read all notifications error:", error)
        return jsonify({
            "error": "Unable to update notifications."
        }), 500

    finally:
        cursor.close()
        connection.close()

# ---------------- CUSTOMER PRODUCT RETURNS ----------------

@app.route("/api/customer/orders/<int:order_id>/returns", methods=["POST"])
def customer_create_return(order_id):
    data = request.get_json(silent=True) or {}

    customer_phone = str(data.get("customer_phone", "")).strip()
    reason = str(data.get("reason", "")).strip()

    try:
        order_item_id = int(data.get("order_item_id"))
        quantity = float(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Valid order item and quantity are required."
        }), 400

    if not customer_phone or not reason or quantity <= 0:
        return jsonify({
            "error": "Phone, return reason and valid quantity are required."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                oi.id, oi.order_id, oi.product_id, oi.seller_id,
                oi.quantity, p.name AS product_name,
                o.customer_name, o.customer_phone,
                o.customer_address, o.order_status
            FROM order_items oi
            JOIN orders o ON o.id = oi.order_id
            JOIN products p ON p.id = oi.product_id
            WHERE oi.id = %s AND oi.order_id = %s
        """, (order_item_id, order_id))

        item = cursor.fetchone()

        if not item or str(item["customer_phone"]).strip() != customer_phone:
            return jsonify({
                "error": "Order item/customer details do not match."
            }), 404

        if quantity > float(item["quantity"]):
            return jsonify({
                "error": "Return quantity cannot exceed purchased quantity."
            }), 400

        if str(item["order_status"]).lower() in ("cancelled", "canceled"):
            return jsonify({
                "error": "Cancelled orders cannot be returned."
            }), 400

        cursor.execute("""
            SELECT id
            FROM return_requests
            WHERE order_item_id = %s
              AND status NOT IN ('Rejected', 'Closed')
        """, (order_item_id,))

        if cursor.fetchone():
            return jsonify({
                "error": "A return request already exists for this item."
            }), 409

        cursor.execute("""
            INSERT INTO return_requests (
                order_id, order_item_id, product_id, seller_id,
                customer_name, customer_phone, customer_address,
                quantity, reason
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            order_id,
            order_item_id,
            item["product_id"],
            item["seller_id"],
            item["customer_name"],
            customer_phone,
            item["customer_address"],
            quantity,
            reason
        ))

        return_id = cursor.lastrowid

        cursor.execute("""
            INSERT INTO notifications (seller_id, title, message)
            VALUES (%s, %s, %s)
        """, (
            item["seller_id"],
            "New return request",
            f"Return requested for {item['product_name']} "
            f"(Order #{order_id}). Reason: {reason}"
        ))

        connection.commit()

        return jsonify({
            "message": "Return request submitted to seller.",
            "return_id": return_id
        }), 201

    except MySQLError as error:
        connection.rollback()
        print("Customer return error:", error)
        return jsonify({
            "error": "Unable to submit return request."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- SELLER RETURN MANAGEMENT ----------------

@app.route("/api/seller/returns", methods=["GET"])
@seller_required
def seller_get_returns():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                r.*,
                p.name AS product_name,
                p.image AS product_image
            FROM return_requests r
            JOIN products p ON p.id = r.product_id
            WHERE r.seller_id = %s
            ORDER BY r.id DESC
        """, (get_seller_id(),))

        rows = cursor.fetchall()
        return jsonify({"returns": rows})

    except MySQLError as error:
        print("Get returns error:", error)
        return jsonify({"error": "Unable to load returns."}), 500

    finally:
        cursor.close()
        connection.close()


@app.route(
    "/api/seller/returns/<int:return_id>/decision",
    methods=["PATCH"]
)
@seller_required
def seller_decide_return(return_id):
    data = request.get_json(silent=True) or {}

    decision = str(data.get("decision", "")).strip().lower()
    note = str(data.get("seller_note", "")).strip()

    if decision not in ("approve", "reject"):
        return jsonify({
            "error": "Decision must be approve or reject."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM return_requests
            WHERE id = %s AND seller_id = %s
            FOR UPDATE
        """, (return_id, get_seller_id()))

        row = cursor.fetchone()

        if not row:
            return jsonify({
                "error": "Return request not found."
            }), 404

        if row["status"] != "Requested":
            return jsonify({
                "error": "Return request already processed."
            }), 409

        status = "Approved" if decision == "approve" else "Rejected"

        cursor.execute("""
            UPDATE return_requests
            SET status = %s,
                seller_note = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND seller_id = %s
        """, (status, note, return_id, get_seller_id()))

        connection.commit()

        return jsonify({
            "message": f"Return request {status.lower()}."
        })

    except MySQLError as error:
        connection.rollback()
        print("Return decision error:", error)
        return jsonify({
            "error": "Unable to process return request."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route(
    "/api/seller/returns/<int:return_id>/assign-rider",
    methods=["PATCH"]
)
@seller_required
def seller_assign_return_rider(return_id):
    data = request.get_json(silent=True) or {}

    rider_name = str(data.get("rider_name", "")).strip()
    rider_phone = str(data.get("rider_phone", "")).strip()

    if not rider_name or not rider_phone:
        return jsonify({
            "error": "Rider name and phone are required."
        }), 400

    if not rider_phone.isdigit() or len(rider_phone) != 10:
        return jsonify({
            "error": "Enter a valid 10-digit rider phone number."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT *
            FROM return_requests
            WHERE id = %s AND seller_id = %s
            FOR UPDATE
        """, (return_id, get_seller_id()))

        row = cursor.fetchone()

        if not row:
            return jsonify({
                "error": "Return request not found."
            }), 404

        if row["status"] != "Approved":
            return jsonify({
                "error": "Approve the return before assigning a rider."
            }), 409

        cursor.execute("""
            UPDATE return_requests
            SET rider_name = %s,
                rider_phone = %s,
                rider_status = 'Assigned',
                status = 'Pickup Assigned',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND seller_id = %s
        """, (
            rider_name,
            rider_phone,
            return_id,
            get_seller_id()
        ))

        connection.commit()

        return jsonify({
            "message": f"Rider {rider_name} assigned successfully."
        })

    except MySQLError as error:
        connection.rollback()
        print("Return rider error:", error)
        return jsonify({
            "error": "Unable to assign return pickup rider."
        }), 500

    finally:
        cursor.close()
        connection.close()


@app.route(
    "/api/seller/returns/<int:return_id>/received",
    methods=["PATCH"]
)
@seller_required
def seller_confirm_return_received(return_id):
    data = request.get_json(silent=True) or {}

    condition = str(data.get("item_condition", "")).strip().lower()
    note = str(data.get("seller_note", "")).strip()

    allowed_conditions = (
        "resellable",
        "damaged",
        "wrong_item",
        "opened",
        "expired"
    )

    if condition not in allowed_conditions:
        return jsonify({
            "error": "Condition must be resellable, damaged, "
                     "wrong_item, opened or expired."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        cursor.execute("""
            SELECT *
            FROM return_requests
            WHERE id = %s AND seller_id = %s
            FOR UPDATE
        """, (return_id, get_seller_id()))

        row = cursor.fetchone()

        if not row:
            connection.rollback()
            return jsonify({
                "error": "Return request not found."
            }), 404

        if row["status"] not in ("Approved", "Pickup Assigned"):
            connection.rollback()
            return jsonify({
                "error": "Only approved returns can be marked received."
            }), 409

        restocked = 0
        status = "Received - Not Restocked"

        if condition == "resellable":
            cursor.execute("""
                UPDATE products
                SET quantity = quantity + %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND seller_id = %s
            """, (
                row["quantity"],
                row["product_id"],
                get_seller_id()
            ))

            restocked = 1
            status = "Closed"

        cursor.execute("""
            UPDATE return_requests
            SET status = %s,
                item_condition = %s,
                seller_note = %s,
                restocked = %s,
                rider_status = 'Completed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND seller_id = %s
        """, (
            status,
            condition,
            note,
            restocked,
            return_id,
            get_seller_id()
        ))

        connection.commit()

        return jsonify({
            "message": "Return received and inspected. "
                       "Stock updated only if resellable.",
            "restocked": bool(restocked)
        })

    except MySQLError as error:
        connection.rollback()
        print("Return received error:", error)
        return jsonify({
            "error": "Unable to update received return."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- CHANGE PASSWORD ----------------

@app.route("/api/seller/change-password", methods=["POST"])
@seller_required
def change_password():
    data = request.get_json(silent=True) or {}

    current_password = data.get("current_password", "")
    new_password = data.get("new_password", "")
    confirm_password = data.get("confirm_password", "")

    if not current_password or not new_password or not confirm_password:
        return jsonify({
            "error": "Please fill all password fields."
        }), 400

    if new_password != confirm_password:
        return jsonify({
            "error": "New passwords do not match."
        }), 400

    if len(new_password) < 6:
        return jsonify({
            "error": "New password must contain at least 6 characters."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT password
            FROM sellers
            WHERE id = %s
        """, (get_seller_id(),))

        seller = cursor.fetchone()

        if not seller or not check_password_hash(
            seller["password"], current_password
        ):
            return jsonify({
                "error": "Current password is incorrect."
            }), 400

        cursor.execute("""
            UPDATE sellers
            SET password = %s
            WHERE id = %s
        """, (
            generate_password_hash(new_password),
            get_seller_id()
        ))

        connection.commit()

        return jsonify({
            "message": "Password changed successfully."
        })

    except MySQLError as error:
        connection.rollback()
        print("Change password error:", error)
        return jsonify({
            "error": "Unable to change password."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- SELLER CUSTOMER REVIEWS ----------------

@app.route("/api/seller/reviews", methods=["GET"])
@seller_required
def seller_reviews():
    connection = get_db()
    cursor = connection.cursor(dictionary=True)
    seller_id = get_seller_id()

    try:
        cursor.execute("""
            SELECT
                r.id,
                r.order_id,
                r.product_id,
                r.customer_name,
                r.rating,
                r.comment,
                r.created_at,
                p.name AS product_name,
                p.image AS product_image
            FROM reviews r
            JOIN products p ON p.id = r.product_id
            WHERE r.seller_id = %s
            ORDER BY r.created_at DESC, r.id DESC
        """, (seller_id,))

        rows = cursor.fetchall()
        return jsonify({"reviews": rows})

    except MySQLError as error:
        print("Seller reviews error:", error)
        return jsonify({"error": "Unable to load reviews."}), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- CUSTOMER SUBMIT PRODUCT REVIEW ----------------

@app.route("/api/reviews", methods=["POST"])
def create_product_review():
    data = request.get_json(silent=True) or {}

    try:
        order_id = int(data.get("order_id"))
        product_id = int(data.get("product_id"))
        rating = int(data.get("rating"))
    except (TypeError, ValueError):
        return jsonify({
            "error": "Enter a valid order ID, product ID and rating."
        }), 400

    customer_phone = str(data.get("customer_phone", "")).strip()
    comment = str(data.get("comment", "")).strip()

    if not customer_phone or not comment:
        return jsonify({
            "error": "Customer phone and review comment are required."
        }), 400

    if rating < 1 or rating > 5:
        return jsonify({
            "error": "Rating must be between 1 and 5."
        }), 400

    if len(comment) > 1000:
        return jsonify({
            "error": "Review must be 1000 characters or less."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                o.id AS order_id,
                o.customer_name,
                oi.product_id,
                oi.seller_id
            FROM orders o
            JOIN order_items oi ON oi.order_id = o.id
            WHERE o.id = %s
              AND oi.product_id = %s
              AND o.customer_phone = %s
        """, (order_id, product_id, customer_phone))

        purchased_item = cursor.fetchone()

        if not purchased_item:
            return jsonify({
                "error": "No matching purchase was found. "
                         "Check your order ID and phone number."
            }), 404

        cursor.execute("""
            INSERT INTO reviews (
                order_id, product_id, seller_id,
                customer_name, rating, comment
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            purchased_item["order_id"],
            purchased_item["product_id"],
            purchased_item["seller_id"],
            purchased_item["customer_name"],
            rating,
            comment
        ))

        connection.commit()

        return jsonify({
            "message": "Thank you! Your product review was submitted."
        }), 201

    except MySQLIntegrityError:
        connection.rollback()
        return jsonify({
            "error": "You have already reviewed this product for this order."
        }), 409

    except MySQLError as error:
        connection.rollback()
        print("Create review error:", error)
        return jsonify({
            "error": "Unable to save your review."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- CUSTOMER ORDER API ----------------

@app.route("/api/orders", methods=["POST"])
def create_customer_order():
    data = request.get_json(silent=True) or {}

    customer_name = str(data.get("customer_name", "")).strip()
    customer_phone = str(data.get("customer_phone", "")).strip()
    customer_address = str(data.get("customer_address", "")).strip()
    items = data.get("items", [])

    if not customer_name or not customer_phone or not customer_address:
        return jsonify({
            "error": "Enter all customer details."
        }), 400

    if not isinstance(items, list) or not items:
        return jsonify({
            "error": "Your order has no products."
        }), 400

    connection = get_db()
    cursor = connection.cursor(dictionary=True)

    try:
        connection.start_transaction()

        order_lines = []
        total_amount = 0

        for item in items:
            product_id = int(item.get("product_id"))
            quantity = float(item.get("quantity"))

            if quantity <= 0:
                raise ValueError("Invalid product quantity.")

            cursor.execute("""
                SELECT id, seller_id, name, price, quantity
                FROM products
                WHERE id = %s AND status = 'Active'
                FOR UPDATE
            """, (product_id,))

            product = cursor.fetchone()

            if not product:
                raise ValueError("A selected product is unavailable.")

            if float(product["quantity"] or 0) < quantity:
                raise ValueError(
                    "Not enough stock for " + product["name"]
                )

            line_total = float(product["price"]) * quantity
            total_amount += line_total

            order_lines.append({
                "product_id": product["id"],
                "seller_id": product["seller_id"],
                "name": product["name"],
                "quantity": quantity,
                "price": product["price"]
            })

        cursor.execute("""
            INSERT INTO orders (
                customer_name,
                customer_phone,
                customer_address,
                total_amount,
                order_status
            )
            VALUES (%s, %s, %s, %s, 'Pending')
        """, (
            customer_name,
            customer_phone,
            customer_address,
            total_amount
        ))

        order_id = cursor.lastrowid

        for item in order_lines:
            cursor.execute("""
                INSERT INTO order_items (
                    order_id, product_id, seller_id, quantity, price
                )
                VALUES (%s, %s, %s, %s, %s)
            """, (
                order_id,
                item["product_id"],
                item["seller_id"],
                item["quantity"],
                item["price"]
            ))

            cursor.execute("""
                UPDATE products
                SET quantity = quantity - %s
                WHERE id = %s
            """, (item["quantity"], item["product_id"]))

            cursor.execute("""
                INSERT INTO notifications (
                    seller_id, title, message
                )
                VALUES (%s, %s, %s)
            """, (
                item["seller_id"],
                "New order received",
                "You received an order for " + item["name"]
                + " (Quantity: " + str(item["quantity"]) + ")."
            ))

        connection.commit()

        return jsonify({
            "message": "Order placed successfully.",
            "order_id": order_id,
            "total_amount": total_amount
        }), 201

    except (ValueError, TypeError) as error:
        connection.rollback()
        return jsonify({"error": str(error)}), 400

    except MySQLError as error:
        connection.rollback()
        print("Customer order error:", error)
        return jsonify({
            "error": "Unable to place order."
        }), 500

    finally:
        cursor.close()
        connection.close()


# ---------------- START SERVER ----------------

if __name__ == "__main__":
    setup_database()
    app.run(debug=True, port=5002)

