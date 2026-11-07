from flask import Flask, render_template, request, redirect, session, send_file, send_from_directory
from flask_mysqldb import MySQL
import os
from werkzeug.utils import secure_filename
from reportlab.pdfgen import canvas
app = Flask(__name__)
app.secret_key = "foodrescue123"

app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = ''
app.config['MYSQL_DB'] = 'food_rescue'

# Upload Folder Configuration
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

mysql = MySQL(app)

def predict_freshness(hours):

    if hours <= 4:
        return "Fresh"

    elif hours <= 8:
        return "Urgent"

    else:
        return "Expired"

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():

    if request.method == 'POST':

        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']

        cur = mysql.connection.cursor()

        cur.execute(
            "INSERT INTO users(name,email,password,role) VALUES(%s,%s,%s,%s)",
            (name, email, password, role)
        )

        mysql.connection.commit()
        cur.close()

        return redirect('/login')

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        email = request.form['email']
        password = request.form['password']

        cur = mysql.connection.cursor()

        cur.execute(
          "SELECT * FROM users WHERE email=%s",
          (email,)
        )

        user = cur.fetchone()

        print("USER =", user)
        print("EMAIL ENTERED =", email)
        print("PASSWORD ENTERED =", password)

        cur.close()
        if user:
            session['user_id'] = user[0]
            session['role'] = user[4]

            if user[4] == 'donor':
               return redirect('/donor_dashboard')

            elif user[4] == 'ngo':
               return redirect('/ngo_dashboard')

            elif user[4] == 'volunteer':
               return redirect('/volunteer_dashboard')
            
            elif user[4] == 'admin':
                return redirect('/admin_dashboard')
        return "Invalid Email or Password"
    return render_template('login.html')

@app.route('/volunteer_dashboard')
def volunteer_dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            requests.id,
            donations.food_name,
            donations.quantity,
            donations.location,
            requests.status,
            donations.latitude,
            donations.longitude
        FROM requests
        JOIN donations
            ON requests.donation_id = donations.id
        WHERE LOWER(requests.status) = 'accepted'
        ORDER BY requests.id DESC
    """)

    tasks = cur.fetchall()

    cur.close()

    return render_template(
        "volunteer_dashboard.html",
        tasks=tasks
    )


@app.route('/donor_dashboard')
def donor_dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    # Get this donor's donations
    cur.execute("""
        SELECT
            id,
            food_name,
            quantity,
            location,
            status,
            image_path
        FROM donations
        WHERE donor_id=%s
    """, (session['user_id'],))

    donations = cur.fetchall()

    # Count pending NGO requests for this donor
    cur.execute("""
        SELECT COUNT(*)
        FROM requests
        JOIN donations
        ON requests.donation_id = donations.id
        WHERE donations.donor_id=%s
        AND requests.status='Pending'
    """, (session['user_id'],))

    pending_requests = cur.fetchone()[0]

    # Fresh donations
    cur.execute("""
        SELECT COUNT(*)
        FROM donations
        WHERE donor_id=%s
        AND status='Fresh'
    """, (session['user_id'],))

    fresh_count = cur.fetchone()[0]

    # Urgent donations
    cur.execute("""
        SELECT COUNT(*)
        FROM donations
        WHERE donor_id=%s
        AND status='Urgent'
    """, (session['user_id'],))

    urgent_count = cur.fetchone()[0]

    # Expired donations
    cur.execute("""
        SELECT COUNT(*)
        FROM donations
        WHERE donor_id=%s
        AND status='Expired'
    """, (session['user_id'],))

    expired_count = cur.fetchone()[0]

    cur.close()

    return render_template(
        'donor_dashboard.html',
        donations=donations,
        fresh_count=fresh_count,
        urgent_count=urgent_count,
        expired_count=expired_count,
        pending_requests=pending_requests
    )
@app.route('/add_donation', methods=['POST'])
def add_donation():

    if 'user_id' not in session:
        return redirect('/login')

    food_name = request.form['food_name']
    quantity = request.form['quantity']
    location = request.form['location']
    hours = int(request.form['hours_since_prepared'])

    latitude = request.form['latitude']
    longitude = request.form['longitude']

    freshness = predict_freshness(hours)

    image = request.files['food_image']
    filename = ""

    if image and image.filename != "":
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    cur = mysql.connection.cursor()

    cur.execute("""
INSERT INTO donations
(donor_id, food_name, quantity, location,
status, hours_since_prepared,
image_path, latitude, longitude)
VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
""", (
    session['user_id'],
    food_name,
    quantity,
    location,
    freshness,
    hours,
    filename,
    latitude,
    longitude
))

    mysql.connection.commit()
    cur.close()

    return redirect('/donor_dashboard')

@app.route('/ngo_dashboard')
def ngo_dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("SELECT * FROM donations WHERE status!='Expired'")
    donations = cur.fetchall()

    cur.close()

    return render_template(
        'ngo_dashboard.html',
        donations=donations
    )

@app.route('/request_food/<int:id>')
def request_food(id):

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("""
        INSERT INTO requests(donation_id, ngo_id, status)
        VALUES(%s, %s, %s)
    """, (
        id,
        session['user_id'],
        "Pending"
    ))

    mysql.connection.commit()
    cur.close()

    return redirect('/ngo_dashboard')
@app.route('/accept_request/<int:id>')
def accept_request(id):

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute(
        "UPDATE requests SET status='Accepted' WHERE id=%s",
        (id,)
    )

    mysql.connection.commit()
    cur.close()

    return redirect('/donor_requests')


@app.route('/reject_request/<int:id>')
def reject_request(id):
    cur = mysql.connection.cursor()
    cur.execute("UPDATE requests SET status='Rejected' WHERE id=%s", (id,))
    mysql.connection.commit()
    cur.close()
    return redirect('/donor_requests')

@app.route('/admin_dashboard')
def admin_dashboard():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM donations")
    total_donations = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM requests")
    total_requests = cur.fetchone()[0]

    cur.close()

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_donations=total_donations,
        total_requests=total_requests
    )
@app.route('/mark_delivered/<int:id>')
def mark_delivered(id):

    cur = mysql.connection.cursor()

    cur.execute("UPDATE requests SET status='Delivered' WHERE id=%s", (id,))
    mysql.connection.commit()

    cur.close()

    return redirect('/volunteer_dashboard')
@app.route('/donor_requests')
def donor_requests():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("""
    SELECT
        requests.id,
        donations.food_name,
        donations.quantity,
        donations.location,
        requests.status
    FROM requests
    JOIN donations
    ON requests.donation_id = donations.id
    """)

    requests_data = cur.fetchall()

    cur.close()

    return render_template(
        "donor_requests.html",
        requests=requests_data
    )

@app.route('/map')
def map():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("""
        SELECT
            id,
            food_name,
            quantity,
            location,
            status,
            image_path,
            latitude,
            longitude
        FROM donations
        WHERE latitude IS NOT NULL
        AND longitude IS NOT NULL
    """)

    donations = cur.fetchall()

    cur.close()

    return render_template(
        "map.html",
        donations=donations
    )

@app.route('/download_report')
def download_report():

    if 'user_id' not in session:
        return redirect('/login')

    cur = mysql.connection.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM donations")
    total_donations = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM requests")
    total_requests = cur.fetchone()[0]

    cur.close()

    pdf = canvas.Canvas("report.pdf")

    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(180, 800, "Food Rescue Connect Report")

    pdf.setFont("Helvetica", 14)
    pdf.drawString(100, 740, f"Total Users : {total_users}")
    pdf.drawString(100, 710, f"Total Donations : {total_donations}")
    pdf.drawString(100, 680, f"Total Requests : {total_requests}")

    pdf.save()

    return send_file("report.pdf", as_attachment=True)

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


@app.route('/service-worker.js')
def service_worker():
    response = send_from_directory(app.root_path, 'service-worker.js', mimetype='application/javascript')
    response.headers['Service-Worker-Allowed'] = '/'
    response.headers['Cache-Control'] = 'no-cache'
    return response

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
