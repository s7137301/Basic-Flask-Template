from flask import *
import sys, os
import logging
from interfaces.databaseinterface import Database
from interfaces.hashing import *
from werkzeug.utils import secure_filename    


#---CONFIGURE APP---------------------------------------------------
app = Flask(__name__)
logging.basicConfig(filename='logs/flask.log', level=logging.INFO)
sys.tracebacklimit = 10

# Configure the upload folder and allowed file extensions
UPLOAD_FOLDER = 'profilephotos'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['SECRET_KEY'] = "Type in secret line of text"

# Function to check the file extension
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

DATABASE = Database("database/test.db", app.logger)

#---VIEW FUNCTIONS----------------------------------------------------
@app.route('/init-db')
def init_db():
    DATABASE.ModifyQuery("""
        CREATE TABLE IF NOT EXISTS listings (
            listingid INTEGER PRIMARY KEY AUTOINCREMENT,
            sellerid INTEGER NOT NULL,
            title TEXT,
            hardware_type TEXT,
            ram_gb INTEGER,
            hourly_price REAL,
            status TEXT DEFAULT 'available',
            FOREIGN KEY(sellerid) REFERENCES users(userid) ON DELETE CASCADE
        )
    """)
    DATABASE.ModifyQuery("""
        CREATE TABLE IF NOT EXISTS agreements (
            agreementid INTEGER PRIMARY KEY AUTOINCREMENT,
            listingid INTEGER NOT NULL,
            buyerid INTEGER NOT NULL,
            hours INTEGER,
            seller_payout REAL,
            buyer_fee REAL,
            total_cost REAL,
            status TEXT DEFAULT 'active',
            FOREIGN KEY(listingid) REFERENCES listings(listingid),
            FOREIGN KEY(buyerid) REFERENCES users(userid)
        )
    """)
    return "Marketplace database tables are ready."

@app.route('/init-full-db')
def init_full_db():
    init_db()
    DATABASE.ModifyQuery("""
        CREATE TABLE IF NOT EXISTS ratings (
            ratingid INTEGER PRIMARY KEY AUTOINCREMENT,
            agreementid INTEGER NOT NULL,
            raterid INTEGER NOT NULL,
            sellerid INTEGER NOT NULL,
            score INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
            comment TEXT,
            FOREIGN KEY(agreementid) REFERENCES agreements(agreementid),
            FOREIGN KEY(raterid) REFERENCES users(userid),
            FOREIGN KEY(sellerid) REFERENCES users(userid)
        )
    """)
    migrations = [
        ("users", "is_enterprise", "INTEGER DEFAULT 0"),
        ("users", "company_name", "TEXT"),
        ("users", "enterprise_status", "TEXT DEFAULT 'none'"),
        ("users", "rating", "REAL DEFAULT 5.0"),
        ("listings", "enterprise_only", "INTEGER DEFAULT 0"),
        ("listings", "benchmark_score", "INTEGER DEFAULT 100"),
        ("listings", "allow_failover", "INTEGER DEFAULT 1"),
        ("agreements", "fee_rate", "REAL DEFAULT 0.15"),
        ("agreements", "contract_type", "TEXT DEFAULT 'standard'"),
        ("agreements", "escrow_status", "TEXT DEFAULT 'held'"),
        ("agreements", "completed_hours", "INTEGER DEFAULT 0"),
        ("agreements", "offloaded_to_sellerid", "INTEGER NULL"),
        ("agreements", "penalty_fee", "REAL DEFAULT 0.0"),
        ("agreements", "allow_failover", "INTEGER DEFAULT 1"),
    ]
    for table, column, definition in migrations:
        existing_columns = DATABASE.ViewQuery("PRAGMA table_info(" + table + ")")
        if not existing_columns or column not in {row['name'] for row in existing_columns}:
            DATABASE.ModifyQuery("ALTER TABLE " + table + " ADD COLUMN " + column + " " + definition)
    return "Full marketplace database schema is ready."

@app.route('/create-listing', methods=['GET', 'POST'])
def create_listing():
    if 'userid' not in session:
        return redirect('./')

    if request.method == 'POST':
        DATABASE.ModifyQuery(
            "INSERT INTO listings (sellerid, title, hardware_type, ram_gb, hourly_price, enterprise_only, benchmark_score, allow_failover) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session['userid'], request.form['title'], request.form['hardware_type'],
             int(request.form['ram_gb']), float(request.form['hourly_price']),
             int(request.form.get('enterprise_only', 0)), int(request.form.get('benchmark_score', 100)),
             int(request.form.get('allow_failover', 1)))
        )
        return redirect('./products')

    return render_template('create_listing.html')

@app.route('/logout')
def logout():
    app.logger.info("Log out")
    session.clear()
    return redirect('./')

@app.route('/admin', methods=["GET","POST"])
def admin():

    if 'permission' not in session:
        return redirect("./")
    else:
        if session['permission'] != 'admin':
            return redirect("./")

    results = DATABASE.ViewQuery("SELECT * FROM users") or []
    enterprise_requests = DATABASE.ViewQuery(
        "SELECT userid, firstname, lastname, email, company_name, enterprise_status FROM users WHERE enterprise_status = 'pending'"
    ) or []

    if request.method == "POST":
        approve_id = request.form.get('approve_enterprise')
        reject_id = request.form.get('reject_enterprise')
        if approve_id:
            DATABASE.ModifyQuery(
                "UPDATE users SET is_enterprise = 1, enterprise_status = 'approved' WHERE userid = ?",
                (approve_id,))
            return redirect("./admin")
        if reject_id:
            DATABASE.ModifyQuery(
                "UPDATE users SET is_enterprise = 0, enterprise_status = 'rejected' WHERE userid = ?",
                (reject_id,))
            return redirect("./admin")
        selectedusers = request.form.getlist("selectedusers")
        for userid in selectedusers:
            if int(userid) != 1:
                DATABASE.ModifyQuery("DELETE FROM users WHERE userid = ?", (userid,))
        return redirect("./admin")

    app.logger.info("Admin")
    return render_template("admin.html", results=results, enterprise_requests=enterprise_requests)

@app.route('/home')
def home():

    if 'userid' not in session:
        return redirect('./')

    user = DATABASE.ViewQuery("SELECT * FROM users WHERE userid = ?", (session['userid'],))
    if not user:
        session.clear()
        return redirect('./')

    user = user[0]
    active_rentals = DATABASE.ViewQuery(
        "SELECT agreements.*, listings.title FROM agreements JOIN listings ON agreements.listingid = listings.listingid WHERE agreements.buyerid = ? AND agreements.status = 'active'",
        (session['userid'],)) or []
    listings_count = DATABASE.ViewQuery(
        "SELECT COUNT(*) AS total FROM listings WHERE sellerid = ?", (session['userid'],))
    earnings = DATABASE.ViewQuery(
        "SELECT COALESCE(SUM(agreements.seller_payout), 0) AS total FROM agreements JOIN listings ON agreements.listingid = listings.listingid WHERE listings.sellerid = ?",
        (session['userid'],))
    escrow = DATABASE.ViewQuery(
        "SELECT COALESCE(SUM(total_cost), 0) AS total FROM agreements WHERE buyerid = ? AND escrow_status IN ('held', 'partial_released')",
        (session['userid'],))
    reliability = DATABASE.ViewQuery(
        "SELECT COALESCE(AVG(CASE WHEN hours = 0 THEN 100.0 ELSE completed_hours * 100.0 / hours END), 100.0) AS score FROM agreements WHERE buyerid = ?",
        (session['userid'],))
    dashboard = {
        'active_rentals': active_rentals,
        'total_earnings': earnings[0]['total'] if earnings else 0,
        'escrow_balance': escrow[0]['total'] if escrow else 0,
        'reliability_score': reliability[0]['score'] if reliability else 100,
        'listings_count': listings_count[0]['total'] if listings_count else 0,
        'enterprise_pending': user.get('enterprise_status') == 'pending',
    }
    app.logger.info("Home")
    template = "enterprise_dashboard.html" if user.get('is_enterprise') == 1 else "home.html"
    return render_template(template, user=user, **dashboard)

@app.route('/products')
def products_for_rent():

    if 'userid' not in session:
        return redirect('./')

    buyer = DATABASE.ViewQuery("SELECT is_enterprise, enterprise_status FROM users WHERE userid = ?", (session['userid'],))
    enterprise_access = 1 if buyer and buyer[0].get('is_enterprise') == 1 and buyer[0].get('enterprise_status') == 'approved' else 0
    listings = DATABASE.ViewQuery("SELECT listings.*, users.firstname FROM listings JOIN users ON listings.sellerid = users.userid WHERE listings.status = 'available' AND (listings.enterprise_only = 0 OR listings.enterprise_only = ?)", (enterprise_access,))
    active_agreements = DATABASE.ViewQuery("SELECT agreements.* FROM agreements WHERE agreements.buyerid = ? AND agreements.status = 'active' ORDER BY agreements.agreementid DESC LIMIT 1", (session['userid'],))
    app.logger.info("Products for rent")
    return render_template("products.html", listings=listings or [], active_agreement=active_agreements[0] if active_agreements else None)

@app.route('/checkout/<int:listing_id>', methods=['GET', 'POST'])
def checkout(listing_id):
    if 'userid' not in session:
        return redirect('./')

    listings = DATABASE.ViewQuery("SELECT listings.*, users.firstname FROM listings JOIN users ON listings.sellerid = users.userid WHERE listings.listingid = ? AND listings.status = 'available'", (listing_id,))
    if not listings:
        return "Listing is not available.", 404

    listing = listings[0]
    buyer = DATABASE.ViewQuery("SELECT is_enterprise, enterprise_status FROM users WHERE userid = ?", (session['userid'],))
    is_enterprise = bool(buyer and buyer[0].get('is_enterprise') == 1 and buyer[0].get('enterprise_status') == 'approved')
    if listing.get('enterprise_only') and not is_enterprise:
        return "This listing is available to approved enterprise accounts only.", 403
    fee_rate = 0.22 if is_enterprise else 0.15
    hours = int(request.form.get('hours', 1)) if request.method == 'POST' else 1
    allow_failover = request.form.get('allow_failover') == 'on' if request.method == 'POST' else bool(listing.get('allow_failover', 1))
    if hours < 1:
        return render_template('checkout.html', listing=listing, hours=hours,
                               error='Hours must be at least 1.', fee_rate=fee_rate,
                               allow_failover=allow_failover, is_enterprise=is_enterprise), 400

    seller_payout = listing['hourly_price'] * hours
    buyer_fee = seller_payout * fee_rate
    total_cost = seller_payout + buyer_fee

    if request.method == 'POST':
        DATABASE.ModifyQuery(
            "INSERT INTO agreements (listingid, buyerid, hours, seller_payout, buyer_fee, total_cost, fee_rate, contract_type, escrow_status, allow_failover) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (listing_id, session['userid'], hours, seller_payout, buyer_fee, total_cost, fee_rate,
             'enterprise' if is_enterprise else 'standard', 'held', int(allow_failover))
        )
        DATABASE.ModifyQuery("UPDATE listings SET status = 'rented' WHERE listingid = ?", (listing_id,))
        return redirect('./products')

    return render_template('checkout.html', listing=listing, hours=hours,
                           seller_payout=seller_payout, buyer_fee=buyer_fee,
                           total_cost=total_cost, fee_rate=fee_rate,
                           allow_failover=allow_failover, is_enterprise=is_enterprise)

@app.route('/api/run-task', methods=['POST'])
def run_task():
    return jsonify({'status': 'success', 'output': 'Task executed inside simulated sandbox container.'})

@app.route('/api/simulate-failover', methods=['POST'])
def simulate_failover():
    if 'userid' not in session:
        return jsonify({'status': 'error', 'message': 'Login required.'}), 401
    try:
        agreement_id = int(request.form['agreement_id'])
        actual_hours = int(request.form['actual_completed_hours'])
    except (KeyError, TypeError, ValueError):
        return jsonify({'status': 'error', 'message': 'Valid agreement and completed hours are required.'}), 400

    agreements = DATABASE.ViewQuery(
        "SELECT agreements.*, listings.hourly_price, listings.sellerid, listings.allow_failover FROM agreements JOIN listings ON agreements.listingid = listings.listingid WHERE agreements.agreementid = ? AND agreements.buyerid = ?",
        (agreement_id, session['userid']))
    if not agreements:
        return jsonify({'status': 'error', 'message': 'Agreement not found.'}), 404
    agreement = agreements[0]
    if not agreement['allow_failover'] or not agreement.get('allow_failover', 1):
        return jsonify({'status': 'error', 'message': 'Failover is disabled for this agreement.'}), 400
    if actual_hours < 0 or actual_hours > agreement['hours']:
        return jsonify({'status': 'error', 'message': 'Completed hours are outside the agreement.'}), 400

    remaining_hours = agreement['hours'] - actual_hours
    secondary = DATABASE.ViewQuery(
        "SELECT listings.listingid, listings.sellerid, listings.hourly_price, users.firstname FROM listings JOIN users ON listings.sellerid = users.userid WHERE listings.status = 'available' AND listings.sellerid != ? ORDER BY listings.hourly_price ASC LIMIT 1",
        (agreement['sellerid'],))
    if remaining_hours and not secondary:
        return jsonify({'status': 'error', 'message': 'No available secondary seller found.'}), 409

    partial_payout = actual_hours * agreement['hourly_price']
    penalty_fee = remaining_hours * agreement['hourly_price'] * 0.20
    secondary_sellerid = secondary[0]['sellerid'] if remaining_hours else None
    DATABASE.ModifyQuery(
        "UPDATE agreements SET completed_hours = ?, offloaded_to_sellerid = ?, penalty_fee = ?, escrow_status = 'partial_released' WHERE agreementid = ?",
        (actual_hours, secondary_sellerid, penalty_fee, agreement_id))
    if secondary_sellerid:
        DATABASE.ModifyQuery("UPDATE listings SET status = 'failed_over' WHERE listingid = ?", (agreement['listingid'],))
        DATABASE.ModifyQuery("UPDATE listings SET status = 'rented' WHERE listingid = ?", (secondary[0]['listingid'],))
    return jsonify({'status': 'success', 'partial_payout': partial_payout,
                    'remaining_hours': remaining_hours, 'discounted_rate': agreement['hourly_price'] * 0.80,
                    'penalty_fee': penalty_fee, 'offloaded_to_sellerid': secondary_sellerid,
                    'escrow_status': 'partial_released'})

@app.route('/agreement/<int:agreement_id>')
def agreement(agreement_id):
    if 'userid' not in session:
        return redirect('./')
    agreements = DATABASE.ViewQuery(
        "SELECT agreements.*, listings.title, listings.hourly_price, listings.sellerid, sellers.firstname AS seller_name, buyers.firstname AS buyer_name FROM agreements JOIN listings ON agreements.listingid = listings.listingid JOIN users AS sellers ON listings.sellerid = sellers.userid JOIN users AS buyers ON agreements.buyerid = buyers.userid WHERE agreements.agreementid = ? AND (agreements.buyerid = ? OR listings.sellerid = ?)",
        (agreement_id, session['userid'], session['userid']))
    if not agreements:
        return "Agreement not found.", 404
    return render_template('agreement.html', agreement=agreements[0])

@app.route('/agreement/<int:agreement_id>/rate', methods=['POST'])
def rate_agreement(agreement_id):
    if 'userid' not in session:
        return redirect('./')
    try:
        score = int(request.form['score'])
    except (KeyError, TypeError, ValueError):
        return "Rating must be a whole number from 1 to 5.", 400
    agreement_rows = DATABASE.ViewQuery(
        "SELECT listings.sellerid FROM agreements JOIN listings ON agreements.listingid = listings.listingid WHERE agreements.agreementid = ? AND agreements.buyerid = ?",
        (agreement_id, session['userid']))
    if not agreement_rows or score < 1 or score > 5:
        return "Rating is not valid for this agreement.", 400
    sellerid = agreement_rows[0]['sellerid']
    DATABASE.ModifyQuery("INSERT INTO ratings (agreementid, raterid, sellerid, score, comment) VALUES (?, ?, ?, ?, ?)",
                          (agreement_id, session['userid'], sellerid, score, request.form.get('comment', '')))
    DATABASE.ModifyQuery("UPDATE users SET rating = (SELECT AVG(score) FROM ratings WHERE sellerid = ?) WHERE userid = ?", (sellerid, sellerid))
    return redirect('/agreement/' + str(agreement_id))

@app.route('/terms')
def terms():
    return render_template('terms.html')

@app.route('/privacy')
def privacy():
    return render_template('privacy.html')

@app.route('/platform-agreement')
def platform_agreement():
    return render_template('platform_agreement.html')

@app.route('/login')
def login_page():
    return render_template('login.html', message='Please login')

@app.route('/', methods=["GET","POST"])
def login():
    app.logger.info("Login")

    if 'userid' in session:
        return redirect("./home")

    message = "Please login"
    if request.method == "POST":
        email = request.form['email']
        password = request.form['password']
        results = DATABASE.ViewQuery("SELECT * FROM users WHERE email = ?", (email,))
        if results:
            userdetails = results[0] #row in the user table (Python Dictionary)
            if check_password(userdetails['password'], password):
                message = "Login Successful"

                session['permission'] = userdetails['permission']
                session['userid'] = userdetails['userid']
                session['name'] = userdetails['firstname'] + " " + userdetails['lastname']
                session['profilephoto'] = userdetails.get('profilephoto', '')
                session['is_enterprise'] = userdetails.get('is_enterprise', 0)
                session['enterprise_status'] = userdetails.get('enterprise_status', 'none')

                if session['permission'] == 'admin':
                    return redirect('./admin')
                else:
                    return redirect('./home')
            else: 
                message = "Password incorrect"
        else:
            message = "User does not exist, email is incorrect!!"

    if request.method == "GET":
        return render_template("landing.html")
    return render_template("login.html", message=message)

@app.route('/register', methods=['GET','POST'])
def register():
    app.logger.info("Register")
    message = "Please register"
    if request.method == "POST":

        firstname = request.form['fname']
        lastname = request.form['lname']
        password = request.form['password']
        passwordconfirm = request.form['passwordconfirm']
        email = request.form['email']
        enterprise_requested = request.form.get('enterprise_account') == 'on'
        company_name = request.form.get('company_name', '').strip() or None

        if password != passwordconfirm:
            message = "Error, passwords do not match"
        else:
            results = DATABASE.ViewQuery("SELECT * FROM users WHERE email = ?", (email,))
            if results:
                message = "Error, user already exists"
            else:

                #UPLOAD A FILE
                filepath = ''
                app.logger.info(request.files)
                if 'file' in request.files:
                    
                    file = request.files['file']
                    if file and allowed_file(file.filename):
                        filename = secure_filename(file.filename)
                        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                        file.save(filepath)
                        flash("File uploaded successfully")
                    else:
                        flash("Problem with file upload")
                else:
                    flash("File not found")

                password = hash_password(password)
                DATABASE.ModifyQuery("INSERT INTO users (firstname, lastname, email, password, profilephoto, is_enterprise, company_name, enterprise_status) VALUES (?,?,?,?,?,?,?,?)", (firstname, lastname, email, password, filepath, 0, company_name if enterprise_requested else None, 'pending' if enterprise_requested else 'none'))
                new_user = DATABASE.ViewQuery("SELECT * FROM users WHERE email = ?", (email,))[0]
                session['userid'] = new_user['userid']
                session['permission'] = new_user.get('permission', 'user')
                session['name'] = new_user['firstname'] + " " + new_user['lastname']
                session['profilephoto'] = new_user.get('profilephoto', '')
                session['is_enterprise'] = new_user.get('is_enterprise', 0)
                session['enterprise_status'] = new_user.get('enterprise_status', 'none')
                return redirect('/home')

    return render_template("register.html", message=message)

#return a profile photo
@app.route('/profilephotos/<filename>')
def serve_file(filename):
    if os.path.exists(os.path.join(app.config['UPLOAD_FOLDER'], filename)): # Ensure the file exists
        return send_from_directory(app.config['UPLOAD_FOLDER'], filename)
    else:
        abort(404) # If the file does not exist, return a 404 error

#main method called web server application
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True) #runs a local server on port 5000
