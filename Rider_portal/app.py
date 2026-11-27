from flask import Flask, render_template, redirect, url_for, request, flash, session
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import mysql.connector
from dotenv import load_dotenv
from datetime import timedelta


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))
app = Flask(__name__)
app.secret_key = "fresh_meat_super_secret_key_2026_secure"
app.permanent_session_lifetime = timedelta(days=1)

def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "freshmeat_integrated")
    )


def create_tables():
    connection = get_db_connection()
    cursor = connection.cursor()

    # Riders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS riders (
            rider_id BIGINT AUTO_INCREMENT PRIMARY KEY,
            full_name VARCHAR(100) NOT NULL,
            phone VARCHAR(15) NOT NULL UNIQUE,
            email VARCHAR(100) NOT NULL UNIQUE,
            address TEXT NOT NULL,
            vehicle_number VARCHAR(20) NOT NULL UNIQUE,
            licence_number VARCHAR(50) NOT NULL UNIQUE,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            status VARCHAR(20) DEFAULT 'Approved',
            verification_submitted BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Rider documents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS rider_documents (
            document_id INT AUTO_INCREMENT PRIMARY KEY,
            rider_id BIGINT NOT NULL UNIQUE,
            rider_photo VARCHAR(255),
            license_front VARCHAR(255),
            license_back VARCHAR(255),
            rc_front VARCHAR(255),
            rc_back VARCHAR(255),
            vehicle_photo VARCHAR(255),
            submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (rider_id)
                REFERENCES riders(rider_id)
                ON DELETE CASCADE
        )
    """)

    connection.commit()
    cursor.close()
    connection.close()

    print("Riders and documents tables are ready!")
# Rider document storage
UPLOAD_FOLDER = os.path.join(app.instance_path, "rider_documents")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# Test MySQL connection and create tables
try:
    connection = get_db_connection()
    print("MySQL Connected Successfully!")
    connection.close()

    create_tables()

except mysql.connector.Error as err:
    print("MySQL Connection Failed:", err)



# ---------------- RIDER DOCUMENT STORAGE ----------------

UPLOAD_FOLDER = os.path.join(app.instance_path, "rider_documents")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}


def allowed_file(filename):
    return (
        "." in filename and
        filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
    )


# ---------------- RIDER ACCOUNTS ----------------

riders = {}
next_rider_id = 1

notifications = []


# ---------------- ADMIN CREDENTIALS ----------------

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------------- SHARED ORDER DATA ----------------

orders = [
    {"id": 101, "customer": "Rahul Sharma", "phone": "9000000001", "item": "Chicken Biryani", "address": "Rajahmundry", "amount": 250, "seller_status": "Accepted", "rider_status": "Pending", "rejection_reason": ""},
    {"id": 102, "customer": "Priya Reddy", "phone": "9000000002", "item": "Mutton Biryani", "address": "Danavaipeta, Rajahmundry", "amount": 350, "seller_status": "Accepted", "rider_status": "Pending", "rejection_reason": ""},
    {"id": 103, "customer": "Arjun Kumar", "phone": "9000000003", "item": "Chicken 65", "address": "Morampudi, Rajahmundry", "amount": 220, "seller_status": "Accepted", "rider_status": "Accepted", "rejection_reason": ""},
    {"id": 104, "customer": "Sneha Patel", "phone": "9000000004", "item": "Chicken Biryani", "address": "Kakinada", "amount": 280, "seller_status": "Accepted", "rider_status": "Delivered", "rejection_reason": ""},
    {"id": 105, "customer": "Karthik Rao", "phone": "9000000005", "item": "Mutton Curry", "address": "Vijayawada", "amount": 400, "seller_status": "Accepted", "rider_status": "Rejected", "rejection_reason": "Vehicle breakdown"},
    {"id": 106, "customer": "Ananya Das", "phone": "9000000006", "item": "Chicken Fry", "address": "Bommuru, Rajahmundry", "amount": 180, "seller_status": "Accepted", "rider_status": "Delivered", "rejection_reason": ""},
    {"id": 107, "customer": "Vikram Singh", "phone": "9000000007", "item": "Fish Biryani", "address": "Kakinada", "amount": 320, "seller_status": "Accepted", "rider_status": "Pending", "rejection_reason": ""},
    {"id": 108, "customer": "Divya Rani", "phone": "9000000008", "item": "Chicken Lollipop", "address": "Lalacheruvu, Rajahmundry", "amount": 240, "seller_status": "Accepted", "rider_status": "Accepted", "rejection_reason": ""},
    {"id": 109, "customer": "Sai Teja", "phone": "9000000009", "item": "Mutton Biryani", "address": "Samalkot", "amount": 380, "seller_status": "Accepted", "rider_status": "Delivered", "rejection_reason": ""},
    {"id": 110, "customer": "Meghana", "phone": "9000000010", "item": "Chicken Shawarma", "address": "Dowleswaram", "amount": 190, "seller_status": "Accepted", "rider_status": "Pending", "rejection_reason": ""},
    {"id": 111, "customer": "Rohit Verma", "phone": "9000000011", "item": "Chicken Biryani", "address": "Tapeswaram", "amount": 260, "seller_status": "Accepted", "rider_status": "Accepted", "rejection_reason": ""},
    {"id": 112, "customer": "Pooja Nair", "phone": "9000000012", "item": "Fish Fry", "address": "Bhanugudi, Kakinada", "amount": 210, "seller_status": "Accepted", "rider_status": "Delivered", "rejection_reason": ""}
]


# ---------------- HELPER FUNCTIONS ----------------


def current_rider():

    username = session.get("rider_username")

    if not username:
        return None

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                rider_id AS id,
                full_name AS name,
                phone,
                email,
                address,
                vehicle_number AS vehicle,
                licence_number AS license,
                username,
                password_hash AS password,
                status,
                verification_submitted
            FROM riders
            WHERE username = %s
        """, (username,))

        rider = cursor.fetchone()

        if rider:
            rider["documents"] = {}

        return rider

    finally:
        cursor.close()
        connection.close()



def login_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("rider_username"):
            return redirect(url_for("login"))
        return func(*args, **kwargs)
    return wrapper


def approved_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):

        rider = current_rider()

        if not rider:
            return redirect(url_for("login"))

        if rider["status"] != "Approved":
            return redirect(url_for("rider_status"))

        # Do not allow dashboard access before verification
        if not rider.get("verification_submitted", False):
            return redirect(url_for("rider_verification"))

        return func(*args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return func(*args, **kwargs)
    return wrapper


# ---------------- HOME ----------------


@app.route("/")
def home():

    rider = current_rider()

    if rider:

        if rider["status"] != "Approved":
            return redirect(url_for("rider_status"))

        if not rider.get("verification_submitted", False):
            return redirect(url_for("rider_verification"))

        session["show_bike_splash"] = True
        return redirect(url_for("rider_dashboard"))

    return redirect(url_for("login"))



# ---------------- RIDER REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip().lower()
        address = request.form.get("address", "").strip()
        vehicle = request.form.get("vehicle", "").strip()
        license_number = request.form.get("license", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        # Check empty fields
        if not all([
            name, phone, email, address,
            vehicle, license_number, username, password
        ]):
            flash("Please fill all fields.", "error")
            return redirect(url_for("register"))

        # Validate phone number
        if len(phone) != 10 or not phone.isdigit():
            flash("Enter a valid 10-digit phone number.", "error")
            return redirect(url_for("register"))

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            # Check duplicate phone
            cursor.execute(
                "SELECT rider_id FROM riders WHERE phone = %s",
                (phone,)
            )
            if cursor.fetchone():
                flash("Phone number already registered!", "error")
                return redirect(url_for("register"))

            # Check duplicate email
            cursor.execute(
                "SELECT rider_id FROM riders WHERE email = %s",
                (email,)
            )
            if cursor.fetchone():
                flash("Email address already registered!", "error")
                return redirect(url_for("register"))

            # Check duplicate username
            cursor.execute(
                "SELECT rider_id FROM riders WHERE username = %s",
                (username,)
            )
            if cursor.fetchone():
                flash("Username already taken!", "error")
                return redirect(url_for("register"))

            # Check duplicate driving licence
            cursor.execute(
                "SELECT rider_id FROM riders WHERE licence_number = %s",
                (license_number,)
            )
            if cursor.fetchone():
                flash("Driving licence already registered!", "error")
                return redirect(url_for("register"))

            # Insert rider into MySQL
            password_hash = generate_password_hash(password)

            cursor.execute("""
                INSERT INTO riders (
                    full_name, phone, email, address,
                    vehicle_number, licence_number,
                    username, password_hash, status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                name, phone, email, address,
                vehicle, license_number,
                username, password_hash, "Pending"
            ))

            connection.commit()

            flash("Registration successful! Please login.", "success")
            return redirect(url_for("login"))

        except mysql.connector.Error as err:
            connection.rollback()
            print("Registration database error:", err)
            flash("Something went wrong during registration.", "error")
            return redirect(url_for("register"))

        finally:
            cursor.close()
            connection.close()

    return render_template("register.html")



# ---------------- RIDER LOGIN ----------------


@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        connection = get_db_connection()
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM riders WHERE username = %s",
                (username,)
            )

            rider = cursor.fetchone()

            # Check whether username exists
            if not rider:
                flash("Username not found. Please register first.", "error")
                return redirect(url_for("login"))

            # Check password
            if not check_password_hash(rider["password_hash"], password):
                flash("Invalid password. Please try again.", "error")
                return redirect(url_for("login"))

            # Login successful
            session["rider_username"] = username

            # Check Admin approval
            if rider["status"] == "Rejected":
                return redirect(url_for("rider_status"))

            if rider["status"] != "Approved":
                return redirect(url_for("rider_status"))

            # Check document verification
            if not rider["verification_submitted"]:
                return redirect(url_for("rider_verification"))

            flash("Login successful!", "success")
            return redirect(url_for("rider_dashboard"))

        except mysql.connector.Error as err:
            print("Login database error:", err)
            flash("Something went wrong. Please try again.", "error")

        finally:
            cursor.close()
            connection.close()

    return render_template("login.html")


# ---------------- RIDER VERIFICATION ----------------


@app.route("/rider-verification", methods=["GET", "POST"])
@login_required
def rider_verification():

    rider = current_rider()

    if not rider:
        session.pop("rider_username", None)
        return redirect(url_for("login"))

    if rider.get("verification_submitted", False):
        return redirect(url_for("rider_dashboard"))

    if request.method == "POST":

        document_fields = [
            "rider_photo",
            "license_front",
            "license_back",
            "rc_front",
            "rc_back",
            "vehicle_photo"
        ]

        saved_documents = {}

        rider_folder = os.path.join(
            UPLOAD_FOLDER,
            str(rider["id"])
        )

        os.makedirs(rider_folder, exist_ok=True)

        for field in document_fields:

            file = request.files.get(field)

            if not file or file.filename == "":
                flash("Please capture all required photographs.", "error")
                return redirect(url_for("rider_verification"))

            if not allowed_file(file.filename):
                flash("Only JPG, PNG and WEBP images are allowed.", "error")
                return redirect(url_for("rider_verification"))

            extension = file.filename.rsplit(".", 1)[1].lower()
            filename = secure_filename(f"{field}.{extension}")

            file_path = os.path.join(rider_folder, filename)
            file.save(file_path)

            saved_documents[field] = filename

        connection = get_db_connection()
        cursor = connection.cursor()

        try:

            # Save document filenames in MySQL
            cursor.execute("""
                INSERT INTO rider_documents (
                    rider_id,
                    rider_photo,
                    license_front,
                    license_back,
                    rc_front,
                    rc_back,
                    vehicle_photo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    rider_photo = VALUES(rider_photo),
                    license_front = VALUES(license_front),
                    license_back = VALUES(license_back),
                    rc_front = VALUES(rc_front),
                    rc_back = VALUES(rc_back),
                    vehicle_photo = VALUES(vehicle_photo)
            """, (
                rider["id"],
                saved_documents["rider_photo"],
                saved_documents["license_front"],
                saved_documents["license_back"],
                saved_documents["rc_front"],
                saved_documents["rc_back"],
                saved_documents["vehicle_photo"]
            ))

            # Update verification status in MySQL
            cursor.execute("""
                UPDATE riders
                SET verification_submitted = TRUE
                WHERE rider_id = %s
            """, (rider["id"],))

            connection.commit()

            flash("Documents submitted successfully!", "success")

            return redirect(url_for("rider_dashboard"))

        except mysql.connector.Error as err:

            connection.rollback()
            print("Document verification database error:", err)

            flash("Unable to save documents. Please try again.", "error")

            return redirect(url_for("rider_verification"))

        finally:
            cursor.close()
            connection.close()

    return render_template("verification.html", rider=rider)


# ---------------- RIDER STATUS ----------------

@app.route("/rider-status")
@login_required
def rider_status():
    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    return render_template("rider_status.html", rider=rider)


# ---------------- RIDER LOGOUT ----------------

@app.route("/logout")
def logout():

    session.pop("rider_username", None)

    return redirect(url_for("login"))


# ---------------- ADMIN LOGIN ----------------

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():

    if request.method == "POST":

        username = request.form.get("username", "")
        password = request.form.get("password", "")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:

            session["admin_logged_in"] = True

            return redirect(url_for("admin_dashboard"))

        flash("Invalid admin credentials.", "error")

    return render_template("admin_login.html")


# ---------------- ADMIN LOGOUT ----------------

@app.route("/admin-logout")
def admin_logout():

    session.pop("admin_logged_in", None)

    return redirect(url_for("admin_login"))


# ---------------- ADMIN DASHBOARD ----------------


@app.route("/admin")
@admin_required
def admin_dashboard():

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                r.rider_id AS id,
                r.full_name AS name,
                r.phone,
                r.email,
                r.address,
                r.vehicle_number AS vehicle,
                r.licence_number AS license,
                r.username,
                r.status,
                r.verification_submitted,
                r.created_at,

                d.rider_photo,
                d.license_front,
                d.license_back,
                d.rc_front,
                d.rc_back,
                d.vehicle_photo

            FROM riders r

            LEFT JOIN rider_documents d
                ON r.rider_id = d.rider_id

            ORDER BY r.created_at DESC
        """)

        all_riders = cursor.fetchall()

        # Keep the same document structure used by the templates
        for rider in all_riders:
            rider["documents"] = {
                "rider_photo": rider.pop("rider_photo"),
                "license_front": rider.pop("license_front"),
                "license_back": rider.pop("license_back"),
                "rc_front": rider.pop("rc_front"),
                "rc_back": rider.pop("rc_back"),
                "vehicle_photo": rider.pop("vehicle_photo")
            }

        pending_riders = [
            rider for rider in all_riders
            if rider["status"] == "Pending"
        ]

        return render_template(
            "admin_dashboard.html",
            orders=orders,
            rider=all_riders[0] if all_riders else {},
            riders=all_riders,
            pending_riders=pending_riders
        )

    except mysql.connector.Error as err:
        print("Admin dashboard database error:", err)
        flash("Unable to load rider information.", "error")

        return redirect(url_for("admin_login"))

    finally:
        cursor.close()
        connection.close()


# ---------------- APPROVE RIDER ----------------


@app.route("/admin/approve/<int:rider_id>", methods=["POST"])
@admin_required
def approve_rider(rider_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT full_name FROM riders WHERE rider_id = %s",
            (rider_id,)
        )

        rider = cursor.fetchone()

        if not rider:
            flash("Rider not found.", "warning")

        else:
            cursor.execute("""
                UPDATE riders
                SET status = 'Approved'
                WHERE rider_id = %s
            """, (rider_id,))

            connection.commit()

            flash(
                f"{rider['full_name']} has been approved!",
                "success"
            )

    except mysql.connector.Error as err:
        connection.rollback()
        print("Approve rider database error:", err)
        flash("Unable to approve rider.", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_dashboard"))



# ---------------- REJECT RIDER ----------------


@app.route("/admin/reject/<int:rider_id>", methods=["POST"])
@admin_required
def reject_rider(rider_id):

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute(
            "SELECT full_name FROM riders WHERE rider_id = %s",
            (rider_id,)
        )

        rider = cursor.fetchone()

        if not rider:
            flash("Rider not found.", "warning")

        else:
            cursor.execute("""
                UPDATE riders
                SET status = 'Rejected'
                WHERE rider_id = %s
            """, (rider_id,))

            connection.commit()

            flash(
                f"{rider['full_name']} has been rejected.",
                "success"
            )

    except mysql.connector.Error as err:
        connection.rollback()
        print("Reject rider database error:", err)
        flash("Unable to reject rider.", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("admin_dashboard"))



# ---------------- RIDER DASHBOARD ----------------


@app.route("/rider")
@approved_required
def rider_dashboard():

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        # Get only the orders assigned to the logged-in rider
        cursor.execute("""
            SELECT
                ra.id AS assignment_id,
                o.id AS id,
                o.customer_name AS customer,
                o.customer_phone AS phone,
                o.customer_address AS address,
                o.total_amount AS amount,

                COALESCE(
                    GROUP_CONCAT(
                        DISTINCT CONCAT(p.name, ' x ', oi.quantity)
                        SEPARATOR ', '
                    ),
                    'Order items'
                ) AS item,

                COALESCE(soa.status, 'Accepted') AS seller_status,

                CASE
                    WHEN ra.delivery_status = 'Assigned'
                    THEN 'Pending'
                    ELSE ra.delivery_status
                END AS rider_status,

                ra.rejection_reason AS rejection_reason

            FROM rider_assignments ra

            JOIN orders o
                ON ra.order_id = o.id

            JOIN riders r
                ON ra.rider_id = r.rider_id

            LEFT JOIN order_items oi
                ON oi.order_id = o.id
                AND oi.seller_id = ra.seller_id

            LEFT JOIN products p
                ON oi.product_id = p.id

            LEFT JOIN seller_order_actions soa
                ON soa.order_id = o.id
                AND soa.seller_id = ra.seller_id

            WHERE r.rider_id = %s

            GROUP BY
                ra.id,
                o.id,
                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount,
                soa.status,
                ra.delivery_status,
                ra.rejection_reason

            ORDER BY ra.assigned_at DESC
        """, (rider["id"],))

        orders = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    # Active orders assigned to this rider
    assigned_orders = [
        o for o in orders
        if o["rider_status"] in [
            "Pending", "Accepted", "Picked Up", "On the Way"
        ]
    ]

    # Completed deliveries
    delivery_history = [
        o for o in orders
        if o["rider_status"] == "Delivered"
    ]

    # Dashboard statistics
    total_assigned = len(orders)

    pending_count = sum(
        o["rider_status"] == "Pending" for o in orders
    )

    accepted_count = sum(
        o["rider_status"] in ["Accepted", "Picked Up", "On the Way"]
        for o in orders
    )

    delivered_count = sum(
        o["rider_status"] == "Delivered" for o in orders
    )

    rejected_count = sum(
        o["rider_status"] == "Rejected" for o in orders
    )

    success_rate = round(
        (delivered_count / total_assigned) * 100, 1
    ) if total_assigned else 0

    chart_data = {
        "labels": ["Pending", "Accepted", "Delivered", "Rejected"],
        "values": [
            pending_count,
            accepted_count,
            delivered_count,
            rejected_count
        ]
    }

    total_order_value = sum(
        float(o["amount"] or 0) for o in orders
    )

    delivered_value = sum(
        float(o["amount"] or 0)
        for o in orders
        if o["rider_status"] == "Delivered"
    )

    food_summary = {}

    for order in orders:
        item = order["item"]
        food_summary[item] = food_summary.get(item, 0) + 1

    food_chart = {
        "labels": list(food_summary.keys()),
        "values": list(food_summary.values())
    }

    return render_template(
        "rider_dashboard.html",
        rider=rider,
        orders=assigned_orders,
        history=delivery_history,
        notifications=notifications,
        total_assigned=total_assigned,
        pending_count=pending_count,
        accepted_count=accepted_count,
        delivered_count=delivered_count,
        rejected_count=rejected_count,
        success_rate=success_rate,
        total_order_value=total_order_value,
        delivered_value=delivered_value,
        chart_data=chart_data,
        food_chart=food_chart,
        show_bike_splash=session.pop("show_bike_splash", False)
    )


# ---------------- ACCEPT ORDER ----------------


# ---------------- ACCEPT ORDER ----------------

@app.route("/accept/<int:order_id>", methods=["POST"])
@approved_required
def accept_order(order_id):

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE rider_assignments
            SET delivery_status = 'Accepted'
            WHERE order_id = %s
              AND rider_id = %s
              AND delivery_status = 'Assigned'
        """, (order_id, rider["id"]))

        if cursor.rowcount > 0:
            connection.commit()

            session["show_bike_splash"] = True

            notifications.insert(0, {
                "title": "Order Accepted",
                "message": f"Order #{order_id} accepted successfully.",
                "date": "Just now"
            })

            flash("Order accepted successfully!", "success")

        else:
            connection.rollback()
            flash("This order is no longer available to accept.", "warning")

    except mysql.connector.Error as err:
        connection.rollback()
        print("Accept order database error:", err)
        flash("Unable to accept this order. Please try again.", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("assigned_orders"))


# ---------------- REJECT ORDER ----------------


# ---------------- REJECT ORDER ----------------

@app.route("/reject/<int:order_id>", methods=["POST"])
@approved_required
def reject_order(order_id):

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    reason = request.form.get("reason", "").strip()

    if not reason:
        reason = "Not specified"

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE rider_assignments
            SET
                delivery_status = 'Rejected',
                rejection_reason = %s
            WHERE order_id = %s
              AND rider_id = %s
              AND delivery_status = 'Assigned'
        """, (reason, order_id, rider["id"]))

        if cursor.rowcount > 0:
            connection.commit()

            notifications.insert(0, {
                "title": "Order Rejected",
                "message": f"Order #{order_id} was rejected.",
                "date": "Just now"
            })

            flash("Order rejected successfully.", "warning")

        else:
            connection.rollback()
            flash("This order is no longer available to reject.", "warning")

    except mysql.connector.Error as err:
        connection.rollback()
        print("Reject order database error:", err)
        flash("Unable to reject this order. Please try again.", "error")

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("rider_dashboard"))


# ---------------- DELIVER ORDER ----------------

@app.route("/deliver/<int:order_id>", methods=["POST"])
@approved_required
def deliver_order(order_id):

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor()

    try:
        # Step 1: Mark this rider's assignment as Delivered
        print("DELIVER ROUTE CALLED")
        print("Order ID:", order_id)
        print("Logged-in Rider ID:", rider["id"])
        cursor.execute("""
            UPDATE rider_assignments
            SET
                delivery_status = 'Delivered',
                delivered_at = NOW()
            WHERE order_id = %s
              AND rider_id = %s
              AND delivery_status IN (
                  'Accepted',
                  'Picked Up',
                  'On the Way'
              )
        """, (order_id, rider["id"]))
        print("Updated assignment rows:", cursor.rowcount)

        if cursor.rowcount > 0:

            # Step 2: Check whether any assignments are still incomplete
            cursor.execute("""
                SELECT COUNT(*)
                FROM rider_assignments
                WHERE order_id = %s
                  AND delivery_status NOT IN (
                      'Delivered',
                      'Rejected'
                  )
            """, (order_id,))

            remaining_assignments = cursor.fetchone()[0]

            # Step 3: Update the main order only when all assignments finish
            if remaining_assignments == 0:
                cursor.execute("""
                    UPDATE orders
                    SET
                        order_status = 'Delivered',
                        delivery_status = 'Delivered'
                    WHERE id = %s
                """, (order_id,))

            # Step 4: Save all database changes
            connection.commit()

            notifications.insert(0, {
                "title": "Order Delivered",
                "message": f"Order #{order_id} delivered successfully.",
                "date": "Just now"
            })

            flash("Order delivered successfully!", "success")

        else:
            connection.rollback()
            flash(
                "This order cannot be marked as delivered.",
                "warning"
            )

    except mysql.connector.Error as err:
        connection.rollback()
        print("Deliver order database error:", err)
        flash(
            "Unable to update delivery status. Please try again.",
            "error"
        )

    finally:
        cursor.close()
        connection.close()

    return redirect(url_for("rider_dashboard"))


# ---------------- ASSIGNED ORDERS ----------------


@app.route("/assigned-orders")
@approved_required
def assigned_orders():

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                ra.id AS assignment_id,
                o.id AS id,
                o.customer_name AS customer,
                o.customer_phone AS phone,
                o.customer_address AS address,
                o.total_amount AS amount,

                COALESCE(
                    GROUP_CONCAT(
                        DISTINCT CONCAT(p.name, ' x ', oi.quantity)
                        SEPARATOR ', '
                    ),
                    'Order items'
                ) AS item,

                COALESCE(soa.status, 'Accepted') AS seller_status,

                CASE
                    WHEN ra.delivery_status = 'Assigned'
                    THEN 'Pending'
                    ELSE ra.delivery_status
                END AS rider_status,

                ra.rejection_reason

            FROM rider_assignments ra

            JOIN orders o
                ON ra.order_id = o.id

            LEFT JOIN order_items oi
                ON oi.order_id = o.id
                AND oi.seller_id = ra.seller_id

            LEFT JOIN products p
                ON oi.product_id = p.id

            LEFT JOIN seller_order_actions soa
                ON soa.order_id = o.id
                AND soa.seller_id = ra.seller_id

            WHERE ra.rider_id = %s
              AND ra.delivery_status IN (
                  'Assigned',
                  'Accepted',
                  'Picked Up',
                  'On the Way'
              )

            GROUP BY
                ra.id,
                o.id,
                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount,
                soa.status,
                ra.delivery_status,
                ra.rejection_reason

            ORDER BY ra.assigned_at DESC
        """, (rider["id"],))

        assigned_orders_list = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "assigned_orders.html",
        rider=rider,
        orders=assigned_orders_list,
        show_bike_splash=session.pop("show_bike_splash", False)
    )
# ---------------- DELIVERY ANALYTICS ----------------


@app.route("/delivery-analytics")
@approved_required
def delivery_analytics():

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                ra.delivery_status AS rider_status,
                o.total_amount AS amount,

                COALESCE(
                    GROUP_CONCAT(
                        DISTINCT CONCAT(p.name, ' x ', oi.quantity)
                        SEPARATOR ', '
                    ),
                    'Order items'
                ) AS item

            FROM rider_assignments ra

            JOIN orders o
                ON ra.order_id = o.id

            LEFT JOIN order_items oi
                ON oi.order_id = o.id
                AND oi.seller_id = ra.seller_id

            LEFT JOIN products p
                ON oi.product_id = p.id

            WHERE ra.rider_id = %s

            GROUP BY
                ra.id,
                ra.delivery_status,
                o.total_amount

            ORDER BY ra.assigned_at DESC
        """, (rider["id"],))

        orders = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    total_assigned = len(orders)

    pending_count = sum(
        o["rider_status"] == "Assigned" for o in orders
    )

    accepted_count = sum(
        o["rider_status"] in ["Accepted", "Picked Up", "On the Way"]
        for o in orders
    )

    delivered_count = sum(
        o["rider_status"] == "Delivered" for o in orders
    )

    rejected_count = sum(
        o["rider_status"] == "Rejected" for o in orders
    )

    success_rate = round(
        (delivered_count / total_assigned) * 100, 1
    ) if total_assigned else 0

    chart_data = {
        "labels": ["Pending", "Accepted", "Delivered", "Rejected"],
        "values": [
            pending_count,
            accepted_count,
            delivered_count,
            rejected_count
        ]
    }

    total_order_value = sum(
        float(o["amount"] or 0) for o in orders
    )

    delivered_value = sum(
        float(o["amount"] or 0)
        for o in orders
        if o["rider_status"] == "Delivered"
    )

    food_summary = {}

    for order in orders:
        item = order["item"]
        food_summary[item] = food_summary.get(item, 0) + 1

    food_chart = {
        "labels": list(food_summary.keys()),
        "values": list(food_summary.values())
    }

    return render_template(
        "delivery_analytics.html",
        rider=rider,
        success_rate=success_rate,
        total_order_value=total_order_value,
        delivered_value=delivered_value,
        chart_data=chart_data,
        food_chart=food_chart
    )



# ---------------- RIDER PROFILE ----------------

@app.route("/rider-profile", methods=["GET", "POST"])
@approved_required

def rider_profile():
    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        vehicle = request.form.get("vehicle", "").strip()

        if not name or not phone or not vehicle:
            flash("Please fill in all profile fields.", "warning")
            return redirect(url_for("rider_profile"))

        connection = get_db_connection()
        cursor = connection.cursor()

        try:
            cursor.execute("""
                UPDATE riders
                SET
                    full_name = %s,
                    phone = %s,
                    vehicle_number = %s
                WHERE rider_id = %s
            """, (name, phone, vehicle, rider["id"]))

            connection.commit()

            flash("Profile updated successfully!", "success")

        except mysql.connector.IntegrityError:
            connection.rollback()
            flash(
                "This phone number or vehicle number is already registered.",
                "error"
            )

        except mysql.connector.Error as err:
            connection.rollback()
            print("Profile update database error:", err)
            flash("Unable to update profile. Please try again.", "error")

        finally:
            cursor.close()
            connection.close()

        return redirect(url_for("rider_profile"))

    return render_template(
        "rider_profile.html",
        rider=rider
    )


# ---------------- ORDER HISTORY ----------------


@app.route("/order-history")
@approved_required
def order_history():

    rider = current_rider()

    if not rider:
        return redirect(url_for("login"))

    connection = get_db_connection()
    cursor = connection.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                ra.id AS assignment_id,
                o.id AS id,
                o.customer_name AS customer,
                o.customer_phone AS phone,
                o.customer_address AS address,
                o.total_amount AS amount,

                COALESCE(
                    GROUP_CONCAT(
                        DISTINCT CONCAT(p.name, ' x ', oi.quantity)
                        SEPARATOR ', '
                    ),
                    'Order items'
                ) AS item,

                COALESCE(soa.status, 'Accepted') AS seller_status,
                ra.delivery_status AS rider_status,
                ra.rejection_reason,
                ra.assigned_at,
                ra.delivered_at

            FROM rider_assignments ra

            JOIN orders o
                ON ra.order_id = o.id

            LEFT JOIN order_items oi
                ON oi.order_id = o.id
                AND oi.seller_id = ra.seller_id

            LEFT JOIN products p
                ON oi.product_id = p.id

            LEFT JOIN seller_order_actions soa
                ON soa.order_id = o.id
                AND soa.seller_id = ra.seller_id

            WHERE ra.rider_id = %s
              AND ra.delivery_status = 'Delivered'

            GROUP BY
                ra.id,
                o.id,
                o.customer_name,
                o.customer_phone,
                o.customer_address,
                o.total_amount,
                soa.status,
                ra.delivery_status,
                ra.rejection_reason,
                ra.assigned_at,
                ra.delivered_at

            ORDER BY ra.delivered_at DESC
        """, (rider["id"],))

        delivery_history = cursor.fetchall()

    finally:
        cursor.close()
        connection.close()

    return render_template(
        "order_history.html",
        rider=rider,
        history=delivery_history
    )



# ---------------- RIDER NOTIFICATIONS ----------------

@app.route("/rider-notifications")
@approved_required
def rider_notifications():

    rider = current_rider()

    return render_template(
        "notifications.html",
        rider=rider,
        notifications=notifications
    )


# ---------------- RUN APPLICATION ----------------

if __name__ == "__main__":
    app.run(debug=True, port=5001)
