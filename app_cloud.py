
import os
from io import BytesIO

import psycopg2
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect,
    session, send_file, send_from_directory
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.pdfgen import canvas
import cloudinary
import cloudinary.uploader

load_dotenv()
cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET"),
    secure=True
)

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")

if not app.secret_key or not DATABASE_URL:
    raise RuntimeError("SECRET_KEY or DATABASE_URL is missing.")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# PostgreSQL database helper functions

def db_query(sql, params=(), fetch=None):
    conn = psycopg2.connect(DATABASE_URL)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)

        if fetch == "one":
            result = cur.fetchone()
        elif fetch == "all":
            result = cur.fetchall()
        else:
            result = cur.rowcount
            conn.commit()

        cur.close()
        return result

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()


def predict_freshness(hours):
    if hours <= 4:
        return "Fresh"
    elif hours <= 8:
        return "Urgent"
    return "Expired"


def role_required(role):
    return (
        "user_id" in session
        and session.get("role") == role
    )


# Home

@app.route("/")
def home():
    return render_template("index.html")


# Registration

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]

        if role not in ["donor", "ngo", "volunteer"]:
            return "Invalid role", 400

        try:
            db_query(
                """INSERT INTO users(name,email,password,role)
                   VALUES(%s,%s,%s,%s)""",
                (name, email, password, role)
            )
            return redirect("/login")

        except psycopg2.errors.UniqueViolation:
            return "Email already registered. Please login."

    return render_template("register.html")


# Login

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        user = db_query(
            "SELECT * FROM users WHERE email=%s",
            (email,),
            fetch="one"
        )

        if user:
            stored_password = user[3] or ""

            if stored_password.startswith(("scrypt:", "pbkdf2:")):
                valid = check_password_hash(stored_password, password)
            else:
                # Support existing accounts with old plain-text passwords
                valid = password == stored_password

                if valid:
                    new_hash = generate_password_hash(password)
                    db_query(
                        "UPDATE users SET password=%s WHERE id=%s",
                        (new_hash, user[0])
                    )

            if valid:
                session["user_id"] = user[0]
                session["role"] = user[4]

                if user[4] == "donor":
                    return redirect("/donor_dashboard")
                elif user[4] == "ngo":
                    return redirect("/ngo_dashboard")
                elif user[4] == "volunteer":
                    return redirect("/volunteer_dashboard")
                elif user[4] == "admin":
                    return redirect("/admin_dashboard")

        return "Invalid Email or Password"

    return render_template("login.html")


# Donor Dashboard

@app.route("/donor_dashboard")
def donor_dashboard():
    if not role_required("donor"):
        return redirect("/login")

    donor_id = session["user_id"]

    donations = db_query("""
        SELECT id, food_name, quantity, location, status, image_path
        FROM donations
        WHERE donor_id=%s
        ORDER BY id DESC
    """, (donor_id,), fetch="all")
    print("DONATION DATA:", donations)

    pending_requests = db_query("""
        SELECT COUNT(*)
        FROM requests
        JOIN donations ON requests.donation_id = donations.id
        WHERE donations.donor_id=%s
        AND requests.status='Pending'
    """, (donor_id,), fetch="one")[0]

    fresh_count = db_query("""
        SELECT COUNT(*) FROM donations
        WHERE donor_id=%s AND status='Fresh'
    """, (donor_id,), fetch="one")[0]

    urgent_count = db_query("""
        SELECT COUNT(*) FROM donations
        WHERE donor_id=%s AND status='Urgent'
    """, (donor_id,), fetch="one")[0]

    expired_count = db_query("""
        SELECT COUNT(*) FROM donations
        WHERE donor_id=%s AND status='Expired'
    """, (donor_id,), fetch="one")[0]

    return render_template(
        "donor_dashboard.html",
        donations=donations,
        fresh_count=fresh_count,
        urgent_count=urgent_count,
        expired_count=expired_count,
        pending_requests=pending_requests
    )


# Add Donation


@app.route("/add_donation", methods=["POST"])
def add_donation():
    if not role_required("donor"):
        return redirect("/login")

    food_name = request.form["food_name"]
    quantity = request.form["quantity"]
    location = request.form["location"]
    hours = int(request.form["hours_since_prepared"])

    latitude = request.form.get("latitude") or None
    longitude = request.form.get("longitude") or None

    freshness = predict_freshness(hours)

    image = request.files.get("food_image")
    image_url = ""

    if image and image.filename:
        result = cloudinary.uploader.upload(
            image,
            folder="food_rescue_connect"
        )
        image_url = result["secure_url"]

    db_query("""
        INSERT INTO donations
        (donor_id, food_name, quantity, location,
         status, hours_since_prepared, image_path,
         latitude, longitude)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (
        session["user_id"], food_name, quantity,
        location, freshness, hours, image_url,
        latitude, longitude
    ))

    return redirect("/donor_dashboard")



# NGO Dashboard

@app.route("/ngo_dashboard")
def ngo_dashboard():
    if not role_required("ngo"):
        return redirect("/login")

    donations = db_query("""
        SELECT
            id,
            donor_id,
            food_name,
            quantity,
            location,
            pickup_time,
            status,
            hours_since_prepared,
            latitude,
            longitude,
            image_path
        FROM donations
        WHERE status != 'Expired'
        ORDER BY id DESC
    """, fetch="all")

    return render_template(
        "ngo_dashboard.html",
        donations=donations
    )


# NGO Requests Food

@app.route("/request_food/<int:id>")
def request_food(id):
    if not role_required("ngo"):
        return redirect("/login")

    ngo_id = session["user_id"]

    # Check whether donation exists
    donation = db_query("""
        SELECT id
        FROM donations
        WHERE id=%s AND status!='Expired'
    """, (id,), fetch="one")

    if not donation:
        return "Donation not available", 404

    # Prevent duplicate requests
    existing_request = db_query("""
        SELECT id
        FROM requests
        WHERE donation_id=%s AND ngo_id=%s
    """, (id, ngo_id), fetch="one")

    if existing_request:
        return redirect("/ngo_dashboard")

    # Insert new request
    db_query("""
        INSERT INTO requests (donation_id, ngo_id, status)
        VALUES (%s, %s, %s)
    """, (id, ngo_id, "Pending"))

    return redirect("/ngo_dashboard")

# Donor Requests

@app.route("/donor_requests")
def donor_requests():
    if not role_required("donor"):
        return redirect("/login")

    requests_data = db_query("""
        SELECT
            requests.id,
            donations.food_name,
            donations.quantity,
            donations.location,
            requests.status
        FROM requests
        JOIN donations ON requests.donation_id = donations.id
        WHERE donations.donor_id=%s
        ORDER BY requests.id DESC
    """, (session["user_id"],), fetch="all")

    return render_template(
        "donor_requests.html",
        requests=requests_data
    )


# Accept Request

@app.route("/accept_request/<int:id>")
def accept_request(id):
    if not role_required("donor"):
        return redirect("/login")

    db_query("""
        UPDATE requests
        SET status='Accepted'
        WHERE id=%s
        AND EXISTS (
            SELECT 1 FROM donations
            WHERE donations.id=requests.donation_id
            AND donations.donor_id=%s
        )
        AND status='Pending'
    """, (id, session["user_id"]))

    return redirect("/donor_requests")


# Reject Request

@app.route("/reject_request/<int:id>")
def reject_request(id):
    if not role_required("donor"):
        return redirect("/login")

    db_query("""
        UPDATE requests
        SET status='Rejected'
        WHERE id=%s
        AND EXISTS (
            SELECT 1 FROM donations
            WHERE donations.id=requests.donation_id
            AND donations.donor_id=%s
        )
        AND status='Pending'
    """, (id, session["user_id"]))

    return redirect("/donor_requests")


# Volunteer Dashboard

@app.route("/volunteer_dashboard")
def volunteer_dashboard():
    if not role_required("volunteer"):
        return redirect("/login")

    tasks = db_query("""
        SELECT
            requests.id,
            donations.food_name,
            donations.quantity,
            donations.location,
            requests.status,
            donations.latitude,
            donations.longitude
        FROM requests
        JOIN donations ON requests.donation_id = donations.id
        WHERE LOWER(requests.status) = 'accepted'
        ORDER BY requests.id DESC
    """, fetch="all")

    return render_template(
        "volunteer_dashboard.html",
        tasks=tasks
    )


# Mark Delivered

@app.route("/mark_delivered/<int:id>")
def mark_delivered(id):
    if not role_required("volunteer"):
        return redirect("/login")

    db_query("""
        UPDATE requests
        SET status='Delivered'
        WHERE id=%s AND status='Accepted'
    """, (id,))

    return redirect("/volunteer_dashboard")


# Admin Dashboard

@app.route("/admin_dashboard")
def admin_dashboard():
    if not role_required("admin"):
        return redirect("/login")

    total_users = db_query(
        "SELECT COUNT(*) FROM users", fetch="one"
    )[0]

    total_donations = db_query(
        "SELECT COUNT(*) FROM donations", fetch="one"
    )[0]

    total_requests = db_query(
        "SELECT COUNT(*) FROM requests", fetch="one"
    )[0]

    return render_template(
        "admin_dashboard.html",
        total_users=total_users,
        total_donations=total_donations,
        total_requests=total_requests
    )


# Live Map

@app.route("/map")
def map():
    if "user_id" not in session:
        return redirect("/login")

    donations = db_query("""
        SELECT
            id, food_name, quantity, location,
            status, image_path, latitude, longitude
        FROM donations
        WHERE latitude IS NOT NULL
        AND longitude IS NOT NULL
    """, fetch="all")

    return render_template(
        "map.html",
        donations=donations
    )


# PDF Report

@app.route("/download_report")
def download_report():
    if not role_required("admin"):
        return redirect("/login")

    total_users = db_query(
        "SELECT COUNT(*) FROM users", fetch="one"
    )[0]

    total_donations = db_query(
        "SELECT COUNT(*) FROM donations", fetch="one"
    )[0]

    total_requests = db_query(
        "SELECT COUNT(*) FROM requests", fetch="one"
    )[0]

    buffer = BytesIO()
    pdf = canvas.Canvas(buffer)

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(150, 800, "Food Rescue Connect Report")

    pdf.setFont("Helvetica", 14)
    pdf.drawString(100, 740, f"Total Users: {total_users}")
    pdf.drawString(100, 710, f"Total Donations: {total_donations}")
    pdf.drawString(100, 680, f"Total Requests: {total_requests}")

    pdf.save()
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="food_rescue_report.pdf",
        mimetype="application/pdf"
    )


# Logout

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# PWA Service Worker

@app.route("/service-worker.js")
def service_worker():
    response = send_from_directory(
        app.root_path,
        "service-worker.js",
        mimetype="application/javascript"
    )
    response.headers["Service-Worker-Allowed"] = "/"
    response.headers["Cache-Control"] = "no-cache"
    return response


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=False
    )
