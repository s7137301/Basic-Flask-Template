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

    results = DATABASE.ViewQuery("SELECT * FROM users")

    if request.method == "POST":
        selectedusers = request.form.getlist("selectedusers")
        for userid in selectedusers:
            if int(userid) != 1:
                DATABASE.ModifyQuery("DELETE FROM users WHERE userid = ?", (userid,))
        return redirect("./admin")

    app.logger.info("Admin")
    return render_template("admin.html", results=results)

@app.route('/home')
def home():

    if 'userid' not in session:
        return redirect('./')

    app.logger.info("Home")
    return render_template("home.html")

@app.route('/', methods=["GET","POST"])
def login():
    app.logger.info("Login")

    if 'permission' in session:
        if session['permission'] == 'admin':
            return redirect("./admin")
        else:
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
                session['profilephoto'] = userdetails['profilephoto']

                if session['permission'] == 'admin':
                    return redirect('./admin')
                else:
                    return redirect('./home')
            else: 
                message = "Password incorrect"
        else:
            message = "User does not exist, email is incorrect!!"

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
                DATABASE.ModifyQuery("INSERT INTO users (firstname, lastname, email, password, profilephoto) VALUES (?,?,?,?,?)", (firstname, lastname, email, password,filepath))
                message = "Success, users has been added"
                return redirect('./')

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
