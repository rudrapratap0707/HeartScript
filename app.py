import io
import os
import random
import tempfile
import urllib.parse
import json
import time
import uuid
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
import firebase_admin
from firebase_admin import auth, credentials, firestore
from flask import (
    Flask, flash, jsonify, redirect, render_template,
    request, session, url_for, send_file
)
from flask_cors import CORS
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_mail import Mail, Message
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect, generate_csrf
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from fpdf import FPDF
from PIL import Image, UnidentifiedImageError

# ==========================================
# LOAD ENVIRONMENT VARIABLES
# ==========================================
load_dotenv()

# ==========================================
# FLASK APP
# ==========================================
app = Flask(__name__)
CORS(app)

# ==========================================
# BASIC CONFIGURATION
# ==========================================
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is missing from .env")

app.config["SECRET_KEY"] = SECRET_KEY

# Security & Upload Configuration
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB max upload limit
csrf = CSRFProtect(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ==========================================
# FLASK LOGIN
# ==========================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'user_login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# ==========================================
# FIREBASE
# ==========================================
try:
    local_key = os.getenv("FIREBASE_LOCAL_KEY", "google-key.json")
    server_key = os.getenv("FIREBASE_SERVER_KEY")

    if not os.path.isabs(local_key):
        local_key = os.path.join(BASE_DIR, local_key)

    cred_path = None

    if os.path.exists(local_key):
        cred_path = local_key
    elif server_key and os.path.exists(server_key):
        cred_path = server_key

    if cred_path:
        if not firebase_admin._apps:
            cred = credentials.Certificate(cred_path)
            firebase_admin.initialize_app(cred)

        fs_db = firestore.client()
        print(f"✅ Firebase Connected Successfully via: {cred_path}")
    else:
        fs_db = None
        print("⚠️ Firebase credentials not found. Running in Local Mode.")

except Exception as e:
    fs_db = None
    print(f"⚠️ Firebase Connection Warning: {e}")

# ==========================================
# DATABASE
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    db_path = os.path.join(BASE_DIR, "heartscript_v2.db")
    DATABASE_URL = "sqlite:///" + db_path

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ==========================================
# MAIL CONFIGURATION
# ==========================================
app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER", "smtp.gmail.com")
app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
app.config["MAIL_USE_TLS"] = (os.getenv("MAIL_USE_TLS", "true").lower() == "true")
app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")

if not app.config["MAIL_USERNAME"]:
    raise RuntimeError("MAIL_USERNAME is missing from .env")

if not app.config["MAIL_PASSWORD"]:
    raise RuntimeError("MAIL_PASSWORD is missing from .env")

mail = Mail(app)

# --- Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    address = db.Column(db.Text, nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    role = db.Column(db.String(20), default="customer")

    ans1 = db.Column(db.String(200), nullable=True)
    ans2 = db.Column(db.String(200), nullable=True)
    ans3 = db.Column(db.String(200), nullable=True)
    ans4 = db.Column(db.String(200), nullable=True)
    ans5 = db.Column(db.String(200), nullable=True)
    ans6 = db.Column(db.String(200), nullable=True)
    ans7 = db.Column(db.String(200), nullable=True)

    profile_pic = db.Column(db.String(500), default="/static/uploads/default_avatar.png")
    orders = db.relationship("Order", backref="customer", lazy=True)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    products = db.relationship("Product", backref="category_ref", lazy=True)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(500), default="https://via.placeholder.com/300")
    image_url2 = db.Column(db.String(500), nullable=True)
    image_url3 = db.Column(db.String(500), nullable=True)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    house_no = db.Column(db.String(100), nullable=True)
    address = db.Column(db.Text, nullable=False)
    landmark = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(10), nullable=True)
    custom_details = db.Column(db.Text, nullable=True)
    total = db.Column(db.String(20), nullable=False)
    items = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default="pending")
    payment_confirmed = db.Column(db.Boolean, default=False)
    delivery_mode = db.Column(db.String(20), default="Standard")
    date_ordered = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

# --- Helpers ---
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            flash("Unauthorized Access!", "danger")
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

def validate_and_save_image(file_to_upload, prefix, upload_folder):
    if not file_to_upload:
        raise ValueError("No image file provided.")

    if not file_to_upload.filename:
        raise ValueError("Invalid image filename.")

    if not allowed_file(file_to_upload.filename):
        raise ValueError("Invalid image format. Only PNG, JPG, JPEG, GIF, and WEBP allowed.")

    try:
        image = Image.open(file_to_upload)
        # Verify actual image structure
        image.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        raise ValueError("Corrupted or invalid image file.")

    # Reset pointer after verify()
    file_to_upload.seek(0)

    original_filename = secure_filename(file_to_upload.filename)
    extension = os.path.splitext(original_filename)[1].lower()

    unique_filename = f"{prefix}_{uuid.uuid4().hex}{extension}"
    file_path = os.path.join(upload_folder, unique_filename)

    file_to_upload.save(file_path)

    return unique_filename

def generate_whatsapp_link(order):
    phone_number = os.getenv("WHATSAPP_PHONE")
    
    if not phone_number:
        raise RuntimeError("WHATSAPP_PHONE is missing from .env")
        
    message = (
        f"🌟 *NEW ORDER PLACED* 🌟\n\n"
        f"Hi HeartScript, I want to proceed with my payment for:\n\n"
        f"🔖 *Order ID:* #HS-{order.id:05d}\n"
        f"🛍️ *Items:* {order.items}\n"
        f"💰 *Amount to Pay:* ₹{order.total}\n\n"
        f"👤 *Customer:* {order.name}\n"
        f"📞 *Contact:* {order.phone}\n"
        f"🏠 *Address:* {order.house_no}, {order.address}, {order.pincode}\n"
        f"📍 *Landmark:* {order.landmark if order.landmark else 'N/A'}\n"
        f"📝 *Note:* {order.custom_details if order.custom_details else 'None'}\n\n"
        f"Please provide payment details to confirm this order. Thank you!"
    )
    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/{phone_number}?text={encoded_message}" 

def validate_password(password): 
    if not password or len(password) < 8: 
        return False 
    return True 

@app.after_request
def add_header(response):
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response
# --- Authentication Routes & Logic --- 

@app.route("/register", methods=["GET", "POST"]) 
def register(): 
    if current_user.is_authenticated: 
        return redirect(url_for('home')) 

    if request.method == "POST": 
        email = request.form.get("email", "").strip().lower() 
        if User.query.filter_by(email=email).first(): 
            flash("Email already registered!", "danger") 
            return redirect(url_for('register')) 
            
        password = request.form.get("password") 
        if not validate_password(password): 
            flash("Password must be at least 8 characters long.", "warning") 
            return redirect(url_for('register')) 

        hashed_pw = generate_password_hash(password) 

        ans_data = {} 
        filled_count = 0 
        for i in range(1, 8): 
            ans_val = request.form.get(f"ans{i}", "").strip().lower() 
            if ans_val: 
                ans_data[f"ans{i}"] = generate_password_hash(ans_val) 
                filled_count += 1 
            else: 
                ans_data[f"ans{i}"] = None 

        if filled_count < 3: 
            flash("Please answer at least 3 security questions!", "warning") 
            return redirect(url_for('register')) 

        new_user = User( 
            username=request.form.get("username"), 
            email=email, 
            password_hash=hashed_pw, 
            phone=request.form.get("phone"), 
            address=request.form.get("address"), 
            pincode=request.form.get("pincode"), 
            **ans_data, 
        ) 
        db.session.add(new_user) 
        db.session.commit() 

        if fs_db: 
            try: 
                fs_db.collection("users").document(email).set( 
                    { 
                        "username": request.form.get("username"), 
                        "email": email, 
                        "phone": request.form.get("phone"), 
                        "address": request.form.get("address"), 
                        "pincode": request.form.get("pincode"), 
                        "role": "customer", 
                        "created_at": datetime.now(timezone.utc), 
                    } 
                ) 
            except Exception as e: 
                print(f"Cloud Sync Error: {e}") 

        flash("Account created! Welcome to HeartScript.", "success") 
        return redirect(url_for('user_login')) 
    return render_template("register.html") 

@app.route("/user_login", methods=["GET", "POST"])
def user_login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password")

        user = User.query.filter_by(email=email).first()

        if user and user.password_hash and check_password_hash(user.password_hash, password):
            # Session clear karke purana stale data hata dein
            session.clear()

            login_user(user, remember=False)

            session["user_id"] = user.id
            session["user_name"] = user.username
            session["user_email"] = user.email
            session["user_profile_pic"] = user.profile_pic

            flash(f"Welcome back, {user.username}! ✨", "success")

            next_page = request.args.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('home'))

        flash("Invalid email or password.", "danger")
    return render_template("user_login.html")


@app.route("/profile", methods=["GET", "POST"]) 
@login_required 
def profile(): 
    user = db.session.get(User, current_user.id) 
    if request.method == "POST": 
        user.phone = request.form.get("phone") 
        user.address = request.form.get("address") 
        user.pincode = request.form.get("pincode") 
        file_to_upload = request.files.get("profile_pic") 

        if file_to_upload and file_to_upload.filename != "":
            try:
                filename = validate_and_save_image(
                    file_to_upload=file_to_upload,
                    prefix=f"profile_{user.id}",
                    upload_folder=app.config["UPLOAD_FOLDER"]
                )

                user.profile_pic = f"/static/uploads/{filename}"
                session["user_profile_pic"] = user.profile_pic

            except ValueError as e:
                flash(str(e), "danger")
                return redirect(url_for("profile"))
            except Exception as e:
                print(f"Profile Upload Error: {e}")
                flash("Unable to upload profile picture.", "danger")
                return redirect(url_for("profile"))

        db.session.commit() 
        flash("Profile updated! ❤️", "success") 
        return redirect(url_for('profile')) 

    orders = ( 
        Order.query.filter_by(user_id=user.id) 
        .order_by(Order.date_ordered.desc()) 
        .all() 
    ) 
    return render_template("profile.html", user=user, orders=orders) 

@app.route("/api/firebase-login", methods=["POST"]) 
def firebase_login(): 
    data = request.get_json(silent=True) or {} 
    id_token = data.get("idToken") 

    if not id_token: 
        return jsonify({"status": "error", "message": "No token provided"}), 400 

    try: 
        decoded_token = auth.verify_id_token(id_token) 
        uid = decoded_token["uid"] 
        email = decoded_token.get("email", "").strip().lower() 
        name = decoded_token.get("name", "Art Lover") 
        picture = decoded_token.get( 
            "picture", "/static/uploads/default_avatar.png" 
        ) 

        user = User.query.filter_by(email=email).first() 
        is_new_user = False 

        if not user: 
            is_new_user = True 
            user = User( 
                username=name, 
                email=email, 
                firebase_uid=uid, 
                profile_pic=picture, 
                role="customer", 
            ) 
            db.session.add(user) 
            db.session.commit() 

            if fs_db: 
                try: 
                    fs_db.collection("users").document(email).set( 
                        { 
                            "username": name, 
                            "email": email, 
                            "firebase_uid": uid, 
                            "role": "customer", 
                            "created_at": datetime.now(timezone.utc), 
                        } 
                    ) 
                except Exception as e: 
                    print(f"Cloud Sync Error: {e}") 
        else: 
            if not user.password_hash: 
                is_new_user = True 
            if not user.firebase_uid: 
                user.firebase_uid = uid 
                db.session.commit() 

        login_user(user, remember=False) 

        session["user_id"] = user.id 
        session["user_name"] = user.username 
        session["user_email"] = user.email 
        session["user_profile_pic"] = user.profile_pic 

        if is_new_user: 
            session["show_password_modal"] = True 

        return jsonify( 
            { 
                "status": "success", 
                "redirect": url_for('home'), 
                "is_new_user": is_new_user, 
            } 
        ) 

    except Exception as e: 
        print(f"Firebase Auth Error: {e}") 
        return jsonify({"status": "error", "message": str(e)}), 401 

@app.route("/set_initial_password", methods=["POST"]) 
@login_required 
def set_initial_password(): 
    password = request.form.get("password") 
    confirm_password = request.form.get("confirm_password") 

    if not validate_password(password) or password != confirm_password: 
        flash("Passwords do not match or are less than 8 characters!", "danger") 
        return redirect(url_for('home')) 

    try: 
        user = db.session.get(User, current_user.id) 
        user.password_hash = generate_password_hash(password) 
        db.session.commit() 
        session.pop("show_password_modal", None) 

        flash( 
            "Password set successfully! You can now login manually too. ❤️", 
            "success", 
        ) 
    except Exception as e: 
        db.session.rollback() 
        flash("Something went wrong. Please try again.", "danger") 

    return redirect(url_for('home')) 

@app.route("/admin/user/<int:user_id>")
@admin_required
def admin_user_detail(user_id): 
    user = User.query.get_or_404(user_id) 
    user_orders = ( 
        Order.query.filter_by(user_id=user.id) 
        .order_by(Order.date_ordered.desc()) 
        .all() 
    ) 
    return render_template( 
        "admin_user_detail.html", user=user, orders=user_orders 
    ) 

# --- Forgot Password & OTP Routes --- 

@app.route("/forgot_password", methods=["GET", "POST"]) 
def forgot_password(): 
    if request.method == "POST": 
        email = request.form.get("email", "").strip().lower() 
        user = User.query.filter_by(email=email).first() 

        if user: 
            otp = str(random.randint(100000, 999999)) 
            session["reset_otp"] = otp 
            session["reset_email"] = email 
            session["reset_otp_created"] = datetime.now(timezone.utc).timestamp() 
            session["otp_attempts"] = 0 
            session.pop("otp_verified", None) 

            try: 
                msg = Message( 
                    "HeartScript - Password Reset OTP", 
                    sender=app.config["MAIL_USERNAME"], 
                    recipients=[email], 
                ) 
                msg.body = f"Hello,\n\nAapka password reset OTP hai: {otp}\n\nYe code 10 minutes mein expire ho jayega. Agar aapne ye request nahi ki hai, toh is email ko ignore karein.\n\nRegards,\nTeam HeartScript" 
                mail.send(msg) 

                flash("OTP aapke registered email par bhej diya gaya hai! ✨", "info") 
                return redirect(url_for('verify_otp')) 
            except Exception as e: 
                print(f"Mail Error: {e}") 
                flash("Email bhejne mein problem aayi. Please dobara try karein.", "danger") 
        else: 
            flash("Ye email registered nahi hai.", "danger") 

    return render_template("forgot_password.html") 

@app.route("/verify_otp", methods=["GET", "POST"]) 
def verify_otp(): 
    if "reset_email" not in session: 
        return redirect(url_for('forgot_password')) 

    if request.method == "POST": 
        attempts = session.get("otp_attempts", 0) 
        
        if attempts >= 5: 
            session.pop("reset_otp", None) 
            session.pop("reset_email", None) 
            session.pop("reset_otp_created", None) 
            session.pop("otp_attempts", None) 
            flash("Too many OTP attempts. Please request a new OTP.", "danger") 
            return redirect(url_for("forgot_password")) 
            
        session["otp_attempts"] = attempts + 1 

        created_at = session.get("reset_otp_created") 
        if not created_at or (datetime.now(timezone.utc).timestamp() - created_at) > 600: 
            session.pop("reset_otp", None) 
            session.pop("reset_email", None) 
            session.pop("reset_otp_created", None) 
            flash("OTP expired. Please request a new one.", "danger") 
            return redirect(url_for("forgot_password")) 

        user_otp = request.form.get("otp") 
        if user_otp == session.get("reset_otp"): 
            session["otp_verified"] = True 
            flash("OTP Verified! Ab naya password set karein.", "success") 
            return redirect(url_for('reset_password')) 
        else: 
            flash("Galat OTP! Fir se try karein.", "danger") 

    return render_template("verify_otp.html") 

@app.route("/reset_password", methods=["GET", "POST"]) 
def reset_password(): 
    if not session.get("reset_email"): 
        return redirect(url_for('forgot_password')) 
        
    if not session.get("otp_verified"): 
        flash("Please verify OTP first.", "warning") 
        return redirect(url_for('verify_otp')) 

    if request.method == "POST": 
        new_pass = request.form.get("password") 
        confirm_pass = request.form.get("confirm_password") 

        if not validate_password(new_pass): 
            flash("Password must be at least 8 characters long.", "warning") 
            return redirect(url_for('reset_password')) 

        if new_pass == confirm_pass: 
            user = User.query.filter_by(email=session["reset_email"]).first() 
            if user: 
                user.password_hash = generate_password_hash(new_pass) 
                db.session.commit() 

                session.pop("reset_otp", None) 
                session.pop("reset_email", None) 
                session.pop("reset_otp_created", None) 
                session.pop("otp_attempts", None) 
                session.pop("otp_verified", None) 

                flash("Password successfully update ho gaya! ❤️", "success") 
                return redirect(url_for('user_login')) 
        else: 
            flash("Passwords match nahi ho rahe.", "danger") 

    return render_template("reset_password.html") 

# --- Store Routes --- 
@app.route("/") 
def home(): 
    return render_template("index.html") 

@app.route("/shop") 
def shop(): 
    categories = Category.query.all() 
    selected_cat = request.args.get("category") 
    if selected_cat and selected_cat != "None": 
        products = Product.query.filter_by(category_id=selected_cat).all() 
    else: 
        products = Product.query.all() 
    return render_template( 
        "shop.html", 
        products=products, 
        categories=categories, 
        selected_cat=selected_cat, 
    ) 

@app.route("/product/<int:product_id>") 
def product_view(product_id): 
    product = Product.query.get_or_404(product_id) 
    related = ( 
        Product.query.filter( 
            Product.category_id == product.category_id, 
            Product.id != product_id, 
        ) 
        .limit(3) 
        .all() 
    ) 
    return render_template("product_view.html", product=product, related=related) 

# --- Checkout & Order Management --- 

@app.route("/checkout/<int:product_id>") 
@login_required 
def checkout_page(product_id): 
    product = Product.query.get_or_404(product_id) 
    user = db.session.get(User, current_user.id) 
    return render_template("checkout.html", product=product, user=user) 

@app.route("/submit_order", methods=["POST"])
@csrf.exempt  # <-- FIX: Ye line add ki gayi hai CSRF bypass karne ke liye
@login_required
def submit_order():
    try:
        # ---------------------------------------------------------
        # 1. Read JSON safely
        # ---------------------------------------------------------
        data = request.get_json(silent=True)

        if not isinstance(data, dict):
            return jsonify({
                "success": False,
                "message": "Invalid order request. JSON data was not received."
            }), 400

        # ---------------------------------------------------------
        # 2. Get required customer/order fields
        # ---------------------------------------------------------
        name = str(data.get("name", "")).strip()
        phone = str(data.get("phone", "")).strip()
        address = str(data.get("address", "")).strip()
        house_no = str(data.get("house_no", "")).strip()
        pincode = str(data.get("pincode", "")).strip()
        custom_details = str(data.get("custom_details", "")).strip()
        delivery_mode = str(data.get("delivery_mode", "self")).strip()

        product_id = data.get("product_id")

        # ---------------------------------------------------------
        # 3. Validate customer information
        # ---------------------------------------------------------
        if not name:
            return jsonify({
                "success": False,
                "message": "Recipient name is required."
            }), 400

        if not phone:
            return jsonify({
                "success": False,
                "message": "WhatsApp number is required."
            }), 400

        # Indian mobile number validation
        clean_phone = "".join(ch for ch in phone if ch.isdigit())

        if len(clean_phone) != 10 or clean_phone[0] not in "6789":
            return jsonify({
                "success": False,
                "message": "Please enter a valid 10-digit WhatsApp number."
            }), 400

        if not house_no:
            return jsonify({
                "success": False,
                "message": "House / flat / street details are required."
            }), 400

        if not address:
            return jsonify({
                "success": False,
                "message": "Delivery address is required."
            }), 400

        if not pincode or len(pincode) != 6 or not pincode.isdigit():
            return jsonify({
                "success": False,
                "message": "Please enter a valid 6-digit pincode."
            }), 400

        # ---------------------------------------------------------
        # 4. Product ID validation
        # ---------------------------------------------------------
        if product_id is None or str(product_id).strip() == "":
            return jsonify({
                "success": False,
                "message": "Product ID is missing from the order request."
            }), 400

        try:
            product_id = int(product_id)
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "message": "Invalid product ID."
            }), 400

        # ---------------------------------------------------------
        # 5. Quantity
        # ---------------------------------------------------------
        try:
            quantity = int(data.get("quantity", 1))
        except (ValueError, TypeError):
            return jsonify({
                "success": False,
                "message": "Quantity must be a valid number."
            }), 400

        if quantity < 1 or quantity > 50:
            return jsonify({
                "success": False,
                "message": "Quantity must be between 1 and 50."
            }), 400

        # ---------------------------------------------------------
        # 6. Fetch product from database
        # ---------------------------------------------------------
        product = db.session.get(Product, product_id)

        if not product:
            return jsonify({
                "success": False,
                "message": "The selected product was not found."
            }), 404

        # ---------------------------------------------------------
        # 7. Get logged-in user
        # ---------------------------------------------------------
        user = db.session.get(User, current_user.id)

        if not user:
            return jsonify({
                "success": False,
                "message": "User account could not be found."
            }), 401

        # ---------------------------------------------------------
        # 8. Backend-controlled pricing
        # ---------------------------------------------------------
        calculated_total = product.price * quantity

        item_description = f"{product.name} (x{quantity})"

        # ---------------------------------------------------------
        # 9. Create order
        # ---------------------------------------------------------
        new_order = Order(
            user_id=user.id,

            # Use checkout recipient name instead of blindly
            # using the account username.
            name=name,

            # Use the number entered on checkout.
            phone=clean_phone,

            email=user.email,

            house_no=house_no,

            address=address,

            landmark=str(data.get("landmark", "")).strip(),

            pincode=pincode,

            custom_details=custom_details,

            # Backend controls final price.
            total=str(calculated_total),

            items=item_description,

            delivery_mode=delivery_mode,

            status="pending"
        )

        # ---------------------------------------------------------
        # 10. Save to SQL database
        # ---------------------------------------------------------
        db.session.add(new_order)
        db.session.commit()

        # ---------------------------------------------------------
        # 11. Sync with Firebase if available
        # ---------------------------------------------------------
        if fs_db:
            try:
                fs_db.collection("orders").document(
                    f"HS-{new_order.id}"
                ).set({
                    "order_id": new_order.id,
                    "customer_name": new_order.name,
                    "customer_phone": new_order.phone,
                    "customer_email": new_order.email,
                    "items": new_order.items,
                    "total_amount": new_order.total,
                    "address": new_order.address,
                    "house_no": new_order.house_no,
                    "pincode": new_order.pincode,
                    "delivery_mode": new_order.delivery_mode,
                    "custom_details": new_order.custom_details,
                    "status": "pending",
                    "date_ordered": datetime.now(timezone.utc),
                })

            except Exception as cloud_e:
                # Firebase failure should NOT destroy the SQL order.
                print(f"Cloud Order Sync Error: {cloud_e}")

        # ---------------------------------------------------------
        # 12. Success response
        # ---------------------------------------------------------
        return jsonify({
            "success": True,
            "order_id": new_order.id,
            "message": "Your order request has been received successfully."
        }), 201

    # -------------------------------------------------------------
    # Validation / known application errors
    # -------------------------------------------------------------
    except Exception as e:

        db.session.rollback()

        print("SUBMIT ORDER ERROR:")
        print(repr(e))

        return jsonify({
            "success": False,
            "message": "Unable to submit your order right now.",
            "error": str(e)
        }), 500

@app.route("/thank_you/<int:order_id>") 
@login_required 
def thank_you(order_id): 
    order = Order.query.get_or_404(order_id) 
    
    # Order Authorization Check 
    if order.user_id != current_user.id and not session.get("admin_logged_in"): 
        return "Unauthorized Access", 403 
        
    whatsapp_link = generate_whatsapp_link(order) 
    return render_template( 
        "thank_you.html", order=order, whatsapp_link=whatsapp_link 
    ) 

def clean_pdf_text(text): 
    if not text: 
        return "" 
    return str(text).encode('ascii', 'ignore').decode('ascii').strip()

@app.route("/download_invoice/<int:order_id>") 
@login_required 
def download_invoice(order_id): 
    order = Order.query.get_or_404(order_id) 
    
    # Order Authorization Check 
    if order.user_id != current_user.id and not session.get("admin_logged_in"): 
        return "Unauthorized Access", 403 
        
    is_confirmed = order.status.lower() in [ 
        "confirmed", 
        "shipped", 
        "delivered", 
        "success", 
    ] 

    try: 
        try: 
            total_amount = float(order.total) 
        except (ValueError, TypeError): 
            total_amount = 0.0 

        pdf = FPDF(orientation="P", unit="mm", format="A4") 
        pdf.add_page() 
        pdf.set_auto_page_break(auto=True, margin=15) 

        primary_color = (255, 65, 108) 
        text_dark = (44, 62, 80) 
        text_light = (127, 140, 141) 

        pdf.set_draw_color(*primary_color) 
        pdf.set_line_width(0.5) 
        pdf.rect(5, 5, 200, 287) 
        pdf.set_line_width(1.5) 
        pdf.rect(7, 7, 196, 283) 

        pdf.ln(12) 
        pdf.set_font("Helvetica", "B", 32) 
        pdf.set_text_color(*primary_color) 
        pdf.cell(0, 12, "HEARTSCRIPT", 0, 1, "C") 
        pdf.set_font("Helvetica", "I", 11) 
        pdf.set_text_color(*text_light) 
        pdf.cell( 
            0, 8, "Artisan Handcrafted Legacies - Shipped Globally", 0, 1, "C" 
        ) 
        pdf.ln(5) 

        if not is_confirmed: 
            pdf.set_fill_color(255, 200, 200) 
            pdf.set_text_color(200, 0, 0) 
            pdf.set_font("Helvetica", "B", 12) 
            pdf.cell( 
                0, 
                10, 
                "ATTENTION: Order is not confirmed yet, please complete the payment", 
                0, 
                1, 
                "C", 
                True, 
            ) 
            pdf.ln(5) 
        else: 
            pdf.set_fill_color(200, 255, 200) 
            pdf.set_text_color(0, 128, 0) 
            pdf.set_font("Helvetica", "B", 12) 
            pdf.cell( 
                0, 
                10, 
                "SUCCESS: ORDER CONFIRMED & SUCCESSFUL", 
                0, 
                1, 
                "C", 
                True, 
            ) 
            pdf.ln(5) 

        pdf.set_fill_color(255, 245, 247) 
        pdf.set_font("Times", "I", 10) 
        pdf.set_text_color(60, 60, 60) 
        brand_description = ( 
            "Welcome to HeartScript, a premier global destination where artisan craftsmanship meets deep human emotions. " 
            "Our platform is dedicated to preserving your most cherished memories through meticulously handcrafted masterpieces. " 
            "HeartScript is recognized globally for its commitment to quality, elegance, and soul-stirring designs." 
        ) 
        pdf.set_x(15) 
        pdf.multi_cell(180, 5, brand_description, 0, "C", True) 
        pdf.ln(10) 

        pdf.set_draw_color(230, 230, 230) 
        pdf.line(15, pdf.get_y(), 195, pdf.get_y()) 
        pdf.ln(5) 

        curr_y = pdf.get_y() 
        pdf.set_font("Helvetica", "B", 10) 
        pdf.set_text_color(*text_dark) 
        pdf.set_xy(15, curr_y) 
        pdf.cell(90, 6, f"ORDER ID: #HS-{order.id:05d}", 0, 1) 
        pdf.set_font("Helvetica", "", 10) 
        pdf.cell( 
            90, 6, f"DATE: {order.date_ordered.strftime('%d %b, %Y')}", 0, 1 
        ) 

        pdf.set_xy(110, curr_y) 
        pdf.set_font("Helvetica", "B", 10) 
        status_text = "CONFIRMED" if is_confirmed else "PENDING" 
        pdf.cell(85, 6, f"PAYMENT STATUS: {status_text}", 0, 1, "R") 
        pdf.ln(8) 

        pdf.set_font("Helvetica", "B", 11) 
        pdf.set_text_color(*primary_color) 
        pdf.set_x(15) 
        pdf.cell(90, 7, "SHIPPING DETAILS:", 0, 1) 
        pdf.set_font("Helvetica", "", 10) 
        pdf.set_text_color(*text_dark) 
        pdf.set_x(15) 

        safe_name = clean_pdf_text(order.name).upper() 
        safe_house = clean_pdf_text(order.house_no) 
        safe_address = clean_pdf_text(order.address) 
        safe_pincode = clean_pdf_text(order.pincode) 
        safe_items = clean_pdf_text(order.items) 

        pdf.cell(90, 6, safe_name, 0, 1) 
        pdf.set_font("Helvetica", "I", 9) 
        pdf.set_x(15) 
        pdf.multi_cell( 
            90, 5, f"{safe_house}, {safe_address}, PIN: {safe_pincode}" 
        ) 
        pdf.ln(10) 

        pdf.set_x(15) 
        pdf.set_fill_color(*primary_color) 
        pdf.set_text_color(255, 255, 255) 
        pdf.set_font("Helvetica", "B", 11) 
        pdf.cell(130, 12, "  ITEM DESCRIPTION", 0, 0, "L", True) 
        pdf.cell(50, 12, "TOTAL (Rs.)  ", 0, 1, "R", True) 

        pdf.set_x(15) 
        pdf.set_fill_color(252, 252, 252) 
        pdf.set_text_color(*text_dark) 
        pdf.set_font("Helvetica", "", 10) 
        pdf.cell(130, 15, f"  {safe_items}", "B", 0, "L", True) 
        pdf.set_font("Helvetica", "B", 11) 
        pdf.cell(50, 15, f"Rs. {total_amount:,.2f}  ", "B", 1, "R", True) 

        pdf.ln(5) 
        pdf.set_x(15) 
        pdf.set_font("Helvetica", "B", 16) 
        pdf.set_text_color(255, 75, 43) 
        pdf.cell(180, 15, f"GRAND TOTAL: Rs. {total_amount:,.2f}", 0, 1, "R") 

        pdf.set_y(-45) 
        pdf.set_draw_color(*primary_color) 
        pdf.line(40, pdf.get_y(), 170, pdf.get_y()) 
        pdf.ln(5) 
        pdf.set_font("Helvetica", "B", 10) 
        pdf.set_text_color(*primary_color) 
        pdf.cell(0, 5, "WWW.HEARTSCRIPT.COM", 0, 1, "C") 
        pdf.set_font("Helvetica", "", 8) 
        pdf.set_text_color(*text_light) 
        pdf.cell( 
            0, 
            4, 
            "Global Luxury Gifting | Hand-Carved Memories | Secure Worldwide Shipping", 
            0, 
            1, 
            "C", 
        ) 

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp: 
            pdf.output(tmp.name) 
            return send_file( 
                tmp.name, 
                as_attachment=True, 
                download_name=f"Invoice_HS_{order.id}.pdf", 
            ) 

    except Exception as e: 
        print(f"Invoice Generation Error: {e}") 
        return f"Invoice Error: {str(e)}", 500 

# --- Admin Routes & Logic --- 

@app.route("/admin-login", methods=["GET", "POST"]) 
def admin_login(): 
    if request.method == "POST": 
        admin_email = os.getenv("ADMIN_EMAIL", "admin@heartscript.com") 
        admin_pass_hash = os.getenv("ADMIN_PASSWORD_HASH") 
        legacy_pass = os.getenv("ADMIN_PASSWORD") 
        
        req_email = request.form.get("email", "").strip().lower() 
        req_pass = request.form.get("password", "") 

        is_valid = False 
        if admin_pass_hash and req_email == admin_email: 
            is_valid = check_password_hash(admin_pass_hash, req_pass) 
        elif legacy_pass and req_pass == legacy_pass: # Legacy fallback for dev 
            is_valid = True 

        if is_valid: 
            session["admin_logged_in"] = True 
            flash("Welcome Admin!", "success") 
            return redirect(url_for('admin')) 
            
        flash("Unauthorized Access!", "danger") 
    return render_template("login.html") 

@app.route("/admin") 
@admin_required
def admin(): 
    orders = Order.query.order_by(Order.date_ordered.desc()).all() 
    products = Product.query.all() 
    categories = Category.query.all() 
    return render_template( 
        "admin.html", orders=orders, products=products, categories=categories 
    ) 

@app.route("/update_status/<int:order_id>", methods=["POST"]) 
@admin_required
def update_status(order_id): 
    order = Order.query.get_or_404(order_id) 
    new_status = None 

    if request.form and request.form.get("status"): 
        new_status = request.form.get("status") 
    elif request.is_json: 
        json_data = request.get_json(silent=True) or {} 
        new_status = json_data.get("status") 

    if new_status: 
        try: 
            formatted_status = str(new_status).strip().lower() 
            order.status = formatted_status 

            if formatted_status in ["confirmed", "processing", "shipped", "delivered"]: 
                order.payment_confirmed = True 
            elif formatted_status == "pending": 
                order.payment_confirmed = False 

            db.session.commit() 

            if fs_db: 
                try: 
                    doc_ref = fs_db.collection("orders").document(f"HS-{order_id}") 
                    doc_ref.update({ 
                        "status": formatted_status, 
                        "payment_confirmed": order.payment_confirmed, 
                    }) 
                except Exception as cloud_e: 
                    print(f"Cloud Update Warning: {cloud_e}") 

            if request.headers.get("X-Requested-With") == "XMLHttpRequest" or request.is_json: 
                return jsonify({ 
                    "success": True, 
                    "message": f"Order #{order_id} set to {formatted_status}", 
                    "status": formatted_status, 
                    "payment_confirmed": order.payment_confirmed 
                }) 

            flash(f"Order #{order_id} updated successfully!", "success") 
            return redirect(url_for('admin')) 

        except Exception as e: 
            db.session.rollback() 
            return jsonify({"success": False, "message": str(e)}), 500 

    return jsonify({"success": False, "message": "Invalid Status Data."}), 400 

@app.route("/confirm_payment/<int:order_id>", methods=["POST"]) 
@admin_required
def confirm_payment(order_id): 
    try: 
        order = Order.query.get_or_404(order_id) 
        order.payment_confirmed = not order.payment_confirmed 

        if order.payment_confirmed: 
            order.status = "confirmed" 
        else: 
            order.status = "pending" 

        db.session.commit() 

        if fs_db: 
            try: 
                fs_db.collection("orders").document(f"HS-{order.id}").update({ 
                    "status": order.status, 
                    "payment_confirmed": order.payment_confirmed, 
                }) 
            except Exception as fs_err: 
                print(f"Firestore Sync Error: {fs_err}") 

        return jsonify({ 
            "success": True, 
            "is_paid": order.payment_confirmed, 
            "status": order.status, 
            "message": f"Payment status updated to {'Paid' if order.payment_confirmed else 'Unpaid'}", 
        }) 

    except Exception as e: 
        db.session.rollback() 
        return jsonify({"success": False, "message": str(e)}), 500 

# --- Catalog Management --- 

@app.route('/add_category', methods=['POST']) 
@admin_required
def add_category(): 
    name = request.form.get('name') 
    if name and not Category.query.filter_by(name=name).first(): 
        try: 
            new_cat = Category(name=name) 
            db.session.add(new_cat) 
            db.session.commit() 
            flash(f"Category '{name}' added successfully! 🎉", "success") 
        except Exception as e: 
            db.session.rollback() 
            flash(f"Error adding category: {str(e)}", "danger") 
    else: 
        flash("Category already exists or name is empty!", "warning") 
    return redirect(url_for('admin')) 

@app.route('/add_product', methods=['POST']) 
@admin_required
def add_product(): 
    try: 
        name = request.form.get('name') 
        price = int(request.form.get('price', 0)) 
        description = request.form.get('description') 
        category_id = int(request.form.get('category_id', 0)) 

        uploaded_urls = [] 
        for i in range(1, 4): 
            file_field = 'product_image' if i == 1 else f'product_image{i}' 
            url_field = 'manual_image_url' if i == 1 else f'manual_image_url{i}' 

            file = request.files.get(file_field) 

            if file and file.filename != '':
                try:
                    filename = validate_and_save_image(
                        file_to_upload=file,
                        prefix=f"prod_{i}",
                        upload_folder=app.config["UPLOAD_FOLDER"]
                    )
                    uploaded_urls.append(f"/static/uploads/{filename}")
                except ValueError as e:
                    raise ValueError(f"Product image {i}: {str(e)}")
            else: 
                fallback_url = request.form.get(url_field, '').strip() 

                if fallback_url: 
                    uploaded_urls.append(fallback_url) 
                else: 
                    uploaded_urls.append("" if i == 1 else None) 

        new_product = Product( 
            name=name, 
            price=price, 
            description=description, 
            category_id=category_id, 
            image_url=uploaded_urls[0], 
            image_url2=uploaded_urls[1], 
            image_url3=uploaded_urls[2] 
        ) 

        db.session.add(new_product) 
        db.session.commit() 
        flash("Product added to catalog successfully! ❤️", "success") 

    except Exception as e: 
        db.session.rollback() 
        flash(f"Catalog Error: {str(e)}", "danger") 

    return redirect(url_for('admin')) 

@app.route('/delete_product/<int:product_id>', methods=['POST']) 
@admin_required
def delete_product(product_id): 
    try: 
        product = db.session.get(Product, product_id) 
        if not product: 
            return jsonify({"success": False, "message": "Product not found in system."}), 404 

        db.session.delete(product) 
        db.session.commit() 

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest': 
            return jsonify({"success": True, "message": "Product removed from catalog successfully!"}) 

        flash("Product removed successfully.", "info") 
        return redirect(url_for('admin')) 
    except Exception as e: 
        db.session.rollback() 
        return jsonify({"success": False, "message": str(e)}), 500 

@app.route('/delete_order/<int:order_id>', methods=['POST']) 
@admin_required
def delete_order(order_id): 
    try: 
        order = db.session.get(Order, order_id) 
        if not order: 
            return jsonify({"success": False, "message": "Order not found in system."}), 404 

        db.session.delete(order) 
        db.session.commit() 

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest': 
            return jsonify({"success": True, "message": "Order deleted successfully!"}) 

        flash("Order removed successfully.", "info") 
        return redirect(url_for('admin')) 
    except Exception as e: 
        db.session.rollback() 
        return jsonify({"success": False, "message": str(e)}), 500 

@app.route('/logout')
def logout():
    logout_user()    # <-- Ye sabse zaroori hai (Flask-Login cookie/remember token delete karega)
    session.clear()  # <-- Saara session data saaf kar dega
    flash("Logged out successfully. See you soon!", "info")
    return redirect(url_for('home'))

# --- Database Initialization & App Runner --- 
if __name__ == "__main__": 

    with app.app_context(): 
        db.create_all() 

    debug_mode = ( 
        os.getenv("FLASK_DEBUG", "false").lower() == "true" 
    ) 

    host = os.getenv("FLASK_HOST", "0.0.0.0") 
    port = int(os.getenv("FLASK_PORT", "5000")) 

    app.run( 
        debug=debug_mode, 
        host=host, 
        port=port 
    )