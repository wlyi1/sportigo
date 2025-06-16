from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, g
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import calendar
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask_migrate import Migrate
from flask.cli import FlaskGroup
from sqlalchemy import distinct, or_
import midtransclient
import json
from uuid import uuid4
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import atexit
from sqlalchemy import extract
from secrets import token_urlsafe
from flask_mail import Message, Mail
import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env file

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:linkinpark1@localhost/sportigo_windows'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your-secret-key-here'  
db = SQLAlchemy(app)
migrate = Migrate(app, db)

MIDTRANS_SERVER_KEY = 'SB-Mid-server-1EZNZC7WrVYhVQhK_V22gtDM'  # Ganti dengan server key Anda
MIDTRANS_CLIENT_KEY = 'SB-Mid-client-_2sU7mKfWAXz2N4S'  # Ganti dengan client key Anda

# Add these configurations after creating the Flask app
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')  # Replace with your email

mail = Mail(app)

#db = SQLAlchemy(app)
#migrate = Migrate(app, db)

snap = midtransclient.Snap(
    is_production=False,  # Tentukan apakah Anda menggunakan lingkungan produksi
    server_key=MIDTRANS_SERVER_KEY,
    client_key=MIDTRANS_CLIENT_KEY
)

def translate_day(day_name):
    translations = {
        'Monday': 'Senin',
        'Tuesday': 'Selasa',
        'Wednesday': 'Rabu',
        'Thursday': 'Kamis',
        'Friday': 'Jumat',
        'Saturday': 'Sabtu',
        'Sunday': 'Minggu'
    }
    return translations.get(day_name, day_name)


app.jinja_env.filters['translate_day'] = translate_day

@app.template_filter('status_color')
def status_color(status):
    colors = {
        'scheduled': 'secondary',
        'present': 'success',
        'absent': 'danger',
        'cancelled': 'warning'
    }
    return colors.get(status, 'secondary')

# Models
class Location(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    monthly_price = db.Column(db.Integer, nullable=False)  
    daily_price = db.Column(db.Integer, nullable=False)    
    quotas = db.relationship('Quota', backref='location', lazy=True)

class Quota(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    day_name = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    quota = db.Column(db.Integer, nullable=False)

class Booking(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    group_id = db.Column(db.String(50), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey('location.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payment_status = db.Column(db.String(20), default='pending')
    presence_status = db.Column(db.String(20), default='pending')
    notes = db.Column(db.Text, nullable=True)
    location = db.relationship('Location', backref='bookings', lazy=True)

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    registration_date = db.Column(db.DateTime, nullable=True, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    full_name = db.Column(db.String(100))
    birthdate = db.Column(db.Date)
    parent_name = db.Column(db.String(100))
    address = db.Column(db.Text)
    mobile_phone = db.Column(db.String(20))
    school = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    bookings = db.relationship('Booking', backref='user', lazy=True)
    reset_token = db.Column(db.String(100), unique=True)
    reset_token_expiry = db.Column(db.DateTime)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(20), unique=True, nullable=False)
    discount_amount = db.Column(db.Integer, nullable=False)  # Store as fixed amount (e.g., 50000)
    valid_until = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # NULL means coupon for all users
    
    # Add relationship to User model
    user = db.relationship('User', backref='coupons')

class ASAPool(db.Model):
    __tablename__ = 'asa_packages'
    id = db.Column(db.Integer, primary_key=True)
    package_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    is_morning_available = db.Column(db.Boolean, default=False)  # For "Reguler + Pagi"
    sessions_per_month = db.Column(db.Integer, default=12)  # Both packages have 12 sessions
    is_trial = db.Column(db.Boolean, default=False)  # Add this line

class ASASchedule(db.Model):
    __tablename__ = 'asa_schedules'
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('asa_packages.id'), nullable=False)
    day_name = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    quota = db.Column(db.Integer, default=20)  # Adjust default quota as needed
    
    package = db.relationship('ASAPool', backref='schedules')

class ASABooking(db.Model):
    __tablename__ = 'asa_bookings'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('asa_packages.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status = db.Column(db.String(20), default='pending')
    applied_discount = db.Column(db.Integer, default=0)
    recurring_payment_date = db.Column(db.Integer)  # Day of month for recurring payment
    next_payment_date = db.Column(db.Date)  # Next payment due date
    is_active = db.Column(db.Boolean, default=True)
    
    package = db.relationship('ASAPool', backref='bookings')
    user = db.relationship('User', backref='asa_bookings')
    sessions = db.relationship('ASABookingSession', backref='booking')

class ASABookingSession(db.Model):
    __tablename__ = 'asa_booking_sessions'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(36), db.ForeignKey('asa_bookings.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('asa_schedules.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='scheduled')
    notes = db.Column(db.Text, nullable=True)
    
    schedule = db.relationship('ASASchedule')

class Coach(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    profile_image = db.Column(db.String(255))  # URL or path to image
    specialization = db.Column(db.String(100))
    experience_years = db.Column(db.Integer)
    bio = db.Column(db.Text)
    certifications = db.Column(db.Text)
    achievements = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)

class Pool(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    address = db.Column(db.Text, nullable=False)
    description = db.Column(db.Text)
    features = db.Column(db.Text)  # Store as comma-separated values
    main_image = db.Column(db.String(255))  # URL or path to main image
    gallery_images = db.Column(db.Text)  # Store as comma-separated URLs/paths
    opening_hours = db.Column(db.Text)  # Store as JSON string
    contact_info = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)

class KCCPool(db.Model):
    __tablename__ = 'kcc_packages'
    id = db.Column(db.Integer, primary_key=True)
    package_name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Integer, nullable=False)
    description = db.Column(db.Text, nullable=True)
    sessions_per_month = db.Column(db.Integer, default=12)
    is_trial = db.Column(db.Boolean, default=False)

class KCCSchedule(db.Model):
    __tablename__ = 'kcc_schedules'
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(db.Integer, db.ForeignKey('kcc_packages.id'), nullable=False)
    day_name = db.Column(db.String(10), nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    quota = db.Column(db.Integer, default=20)
    
    package = db.relationship('KCCPool', backref='schedules')

class KCCBooking(db.Model):
    __tablename__ = 'kcc_bookings'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey('kcc_packages.id'), nullable=False)
    booking_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_status = db.Column(db.String(20), default='pending')
    applied_discount = db.Column(db.Integer, default=0)
    recurring_payment_date = db.Column(db.Integer)
    next_payment_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)
    
    package = db.relationship('KCCPool', backref='bookings')
    user = db.relationship('User', backref='kcc_bookings')
    sessions = db.relationship('KCCBookingSession', backref='booking')

class KCCBookingSession(db.Model):
    __tablename__ = 'kcc_booking_sessions'
    id = db.Column(db.Integer, primary_key=True)
    booking_id = db.Column(db.String(36), db.ForeignKey('kcc_bookings.id'), nullable=False)
    schedule_id = db.Column(db.Integer, db.ForeignKey('kcc_schedules.id'), nullable=False)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), default='scheduled')
    notes = db.Column(db.Text, nullable=True)
    
    schedule = db.relationship('KCCSchedule')

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = User.query.get(session['user_id'])
        if not user or not user.is_admin:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.before_request
def before_request():
    g.user = None
    if 'user_id' in session:
        g.user = User.query.get(session['user_id'])
        
        # Calculate payment notifications count
        if g.user:
            today = datetime.now().date()
            notifications_count = 0
            
            # Count ASA notifications
            asa_notifications = ASABooking.query.filter(
                ASABooking.user_id == g.user.id,
                ASABooking.is_active == True,
                ASABooking.next_payment_date != None,
                ASABooking.next_payment_date <= (today + timedelta(days=3))
            ).count()
            
            # Count KCC notifications
            kcc_notifications = KCCBooking.query.filter(
                KCCBooking.user_id == g.user.id,
                KCCBooking.is_active == True,
                KCCBooking.next_payment_date != None,
                KCCBooking.next_payment_date <= (today + timedelta(days=3))
            ).count()
            
            g.payment_notifications_count = asa_notifications + kcc_notifications

@app.context_processor
def utility_processor():
    def get_payment_notifications_count():
        return getattr(g, 'payment_notifications_count', 0)
    
    def get_current_booking():
        if 'user_id' not in session:
            return None
        # Get the most recent active booking for the current user
        current_booking = ASABooking.query.filter_by(
            user_id=session['user_id'],
            is_active=True
        ).order_by(ASABooking.booking_date.desc()).first()
        return current_booking
    
    def get_current_bookings():
        if 'user_id' not in session:
            return None, None
        
        # Get the most recent active bookings for the current user
        current_asa = ASABooking.query.filter_by(
            user_id=session['user_id'],
            is_active=True
        ).order_by(ASABooking.booking_date.desc()).first()
        
        current_kcc = KCCBooking.query.filter_by(
            user_id=session['user_id'],
            is_active=True
        ).order_by(KCCBooking.booking_date.desc()).first()
        
        return current_asa, current_kcc
    
    current_asa, current_kcc = get_current_bookings()
    return {
        'payment_notifications_count': get_payment_notifications_count(),
        'current_booking': get_current_booking(),
        'current_asa_booking': current_asa,
        'current_kcc_booking': current_kcc
    }

@app.route('/')
def index():
    locations = Location.query.all()
    
    # Get regular package schedules
    regular_package = ASAPool.query.filter_by(package_name='Reguler').first()
    asa_regular_schedules = []
    if regular_package:
        asa_regular_schedules = ASASchedule.query.filter_by(package_id=regular_package.id).all()
    asa_regular_schedules = [
    {field.name: getattr(schedule, field.name).title() if isinstance(getattr(schedule, field.name), str) else getattr(schedule, field.name) 
     for field in ASASchedule.__table__.columns} 
    for schedule in asa_regular_schedules
    ]

    regular_package = KCCPool.query.filter_by(package_name='Reguler').first()

    kcc_regular_schedules = []
    if regular_package:
        kcc_regular_schedules = KCCSchedule.query.filter_by(package_id=regular_package.id).all()
    kcc_regular_schedules = [
    {field.name: getattr(schedule, field.name).title() if isinstance(getattr(schedule, field.name), str) else getattr(schedule, field.name) 
     for field in KCCSchedule.__table__.columns} 
    for schedule in kcc_regular_schedules
    ]
    return render_template('dashboard.html', 
                         locations=locations, 
                         translate_day=translate_day,
                         asa_regular_schedules=asa_regular_schedules,
                         kcc_regular_schedules=kcc_regular_schedules)

@app.route('/dashboard')
@login_required
def dashboard():
    locations = Location.query.all()
    
    # Get regular package schedules
    regular_package_asa = ASAPool.query.filter_by(package_name='Reguler').first()
    asa_regular_schedules = []
    if regular_package_asa:
        asa_regular_schedules = ASASchedule.query.filter_by(package_id=regular_package_asa.id).all()

    regular_package_kcc = KCCPool.query.filter_by(package_name='Reguler').first()
    kcc_regular_schedules = []
    if regular_package_kcc:
        kcc_regular_schedules = KCCSchedule.query.filter_by(package_id=regular_package_kcc.id).all()
    return render_template('dashboard.html', 
                         locations=locations, 
                         translate_day=translate_day,
                         asa_regular_schedules=asa_regular_schedules,
                         kcc_regular_schedules=kcc_regular_schedules)

@app.route('/get_available_slots', methods=['POST'])
@login_required
def get_available_slots():
    location_id = request.form.get('location_id')
    selected_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
    day_name = calendar.day_name[selected_date.weekday()]
    print(day_name)

    # Get quotas for the selected location and day
    quotas = Quota.query.filter_by(
        location_id=location_id,
        day_name=day_name
    ).all()

    available_slots = []

    for quota in quotas:
        # Count existing bookings for the selected date and time slot
        bookings_count = Booking.query.filter_by(
            location_id=location_id,
            session_date=selected_date,
            start_time=quota.start_time,
            end_time=quota.end_time
        ).count()

        available_slots.append({
            'start_time': quota.start_time.strftime('%H:%M'),
            'end_time': quota.end_time.strftime('%H:%M'),
            'available': quota.quota - bookings_count,
            'total_quota': quota.quota
        })

    return jsonify({'available_slots': available_slots})

@app.route('/get_consecutive_dates', methods=['POST'])
@login_required
def get_consecutive_dates():
    location_id = request.form.get('location_id')
    selected_date = datetime.strptime(request.form.get('date'), '%Y-%m-%d')
    start_time = request.form.get('start_time')
    end_time = request.form.get('end_time')
    
    location = Location.query.get(location_id)
    consecutive_dates = []
    
    # Convert time strings to time objects once
    start_time_obj = datetime.strptime(start_time, '%H:%M').time()
    end_time_obj = datetime.strptime(end_time, '%H:%M').time()
    
    # Get current date and next 3 weeks
    current_date = selected_date
    for i in range(4):
        # Get day name for current date
        day_name = calendar.day_name[current_date.weekday()]
        
        # Get quota for this day
        quota_obj = Quota.query.filter_by(
            location_id=location_id,
            day_name=day_name,
            start_time=start_time_obj,
            end_time=end_time_obj
        ).first()

        if not quota_obj:
            return jsonify({
                'error': 'No quota available for selected time slot'
            }), 400

        # Count existing bookings for this specific date and time slot
        bookings_count = Booking.query.filter_by(
            location_id=location_id,
            session_date=current_date,
            start_time=start_time_obj,
            end_time=end_time_obj
        ).count()

        available_quota = quota_obj.quota - bookings_count

        date_info = {
            'date': current_date.strftime('%Y-%m-%d'),
            'formatted_date': current_date.strftime('%d %B %Y'),
            'start_time': start_time,
            'end_time': end_time,
            'available_quota': available_quota,
            'total_quota': quota_obj.quota,
            'is_available': available_quota > 0
        }
        consecutive_dates.append(date_info)
        current_date += timedelta(days=7)

    return jsonify({
        'location_name': location.name,
        'consecutive_dates': consecutive_dates
    })

@app.route('/confirm_booking', methods=['GET'])
@login_required
def confirm_booking():
    # Get parameters from URL
    location_id = request.args.get('location_id')
    selected_date = request.args.get('date')
    start_time = request.args.get('start_time')
    end_time = request.args.get('end_time')
    
    location = Location.query.get(location_id)
    
    return render_template(
        'confirm_booking.html',
        location=location,
        date=selected_date,
        start_time=start_time,
        end_time=end_time
    )

@app.route('/booking_confirmation/<string:booking_id>')
@login_required
def booking_confirmation(booking_id):
    # Get the first booking
    first_booking = Booking.query.get_or_404(booking_id)
    
    # Get all related bookings (4 consecutive weeks)
    bookings = Booking.query.filter_by(
        location_id=first_booking.location_id,
        start_time=first_booking.start_time,
        end_time=first_booking.end_time,
        user_id=session['user_id']
    ).filter(
        Booking.session_date >= first_booking.session_date
    ).order_by(Booking.session_date).limit(4).all()
    
    location = Location.query.get(first_booking.location_id)
    return render_template('booking_confirmation.html', 
                         bookings=bookings,
                         location=location)

@app.route('/book_session', methods=['POST'])
@login_required
def book_session():
    try:
        # Get form data
        location_id = request.form.get('location_id')
        date_str = request.form.get('date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        booking_type = request.form.get('booking_type')

        # Validate input
        if not all([location_id, date_str, start_time_str, end_time_str, booking_type]):
            return jsonify({
                'success': False,
                'message': 'Semua field harus diisi'
            })

        # Generate a unique group_id for regular bookings
        group_id = f"{int(datetime.now().timestamp())}_{session['user_id']}" if booking_type == 'regular' else None

        # Parse dates and times
        session_date = datetime.strptime(date_str, '%Y-%m-%d')
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()

        bookings = []
        
        if booking_type == 'regular':
            # Create bookings for 4 consecutive weeks
            current_date = session_date
            for i in range(4):
                booking = create_booking(
                    location_id, current_date, start_time, end_time,
                    session['user_id'], group_id
                )
                if not booking:
                    raise Exception(f'Kuota penuh untuk tanggal {current_date.strftime("%d %B %Y")}')
                bookings.append(booking)
                current_date += timedelta(days=7)
        else:
            # Create single booking for daily/trial
            booking = create_booking(
                location_id, session_date, start_time, end_time,
                session['user_id'], None
            )
            if not booking:
                raise Exception('Kuota penuh untuk jadwal yang dipilih')
            bookings.append(booking)

        # Add all bookings to the session
        for booking in bookings:
            db.session.add(booking)
        
        db.session.commit()

        return jsonify({
            'success': True, 
            'message': 'Booking berhasil',
            'booking_id': bookings[0].id
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': f'Terjadi kesalahan: {str(e)}'
        })

def create_booking(location_id, session_date, start_time, end_time, user_id, group_id=None):
    # Check quota availability
    day_name = calendar.day_name[session_date.weekday()]
    quota = Quota.query.filter_by(
        location_id=location_id,
        day_name=day_name,
        start_time=start_time,
        end_time=end_time
    ).first()

    if not quota:
        return None

    # Count existing bookings
    existing_bookings = Booking.query.filter_by(
        location_id=location_id,
        session_date=session_date,
        start_time=start_time,
        end_time=end_time
    ).count()

    if existing_bookings >= quota.quota:
        return None

    # Create booking
    return Booking(
        group_id=group_id,
        location_id=location_id,
        session_date=session_date,
        start_time=start_time,
        end_time=end_time,
        user_id=user_id
    )

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        # New fields
        full_name = request.form.get('full_name')
        birthdate = request.form.get('birthdate')
        parent_name = request.form.get('parent_name')
        address = request.form.get('address')
        mobile_phone = request.form.get('mobile_phone')
        school = request.form.get('school')
        gender = request.form.get('gender')

        # Add validation for empty fields
        required_fields = {
            'Username': username,
            'Email': email,
            'Password': password,
            'Full Name': full_name,
            'Birthdate': birthdate,
            'Parent Name': parent_name,
            'Address': address,
            'Mobile Phone': mobile_phone,
            'Gender': gender
        }

        # Check for empty required fields
        empty_fields = [field for field, value in required_fields.items() if not value]
        if empty_fields:
            flash(f"Required fields cannot be empty: {', '.join(empty_fields)}")
            return redirect(url_for('signup'))

        # Check if username or email already exists
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('signup'))
        
        if User.query.filter_by(email=email).first():
            flash('Email already registered')
            return redirect(url_for('signup'))

        try:
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
                registration_date=datetime.utcnow(),
                # Add new fields
                full_name=full_name,
                birthdate=datetime.strptime(birthdate, '%Y-%m-%d').date(),
                parent_name=parent_name,
                address=address,
                mobile_phone=mobile_phone,
                school=school,
                gender=gender
            )
            db.session.add(user)
            db.session.commit()

            flash('Registration successful! Please login.')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred during registration. Please try again.')
            return redirect(url_for('signup'))

    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Redirect if user is already logged in
    if 'user_id' in session:
        return redirect(url_for('index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Add validation for empty fields
        if not username or not password:
            flash('Both username and password are required')
            return redirect(url_for('login'))

        try:
            user = User.query.filter_by(username=username).first()
            
            if user and check_password_hash(user.password_hash, password):
                session['user_id'] = user.id
                session.permanent = True  # Make the session permanent
                flash('Logged in successfully!')
                return redirect(url_for('index'))
            
            flash('Invalid username or password')
            return redirect(url_for('login'))
        except Exception as e:
            flash('An error occurred during login. Please try again.')
            return redirect(url_for('login'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    flash('You have been logged out.')
    return redirect(url_for('login'))

@app.route('/booking_schedule')
@login_required
def booking_schedule():
    locations = Location.query.all()
    return render_template('booking_schedule.html', locations=locations)

@app.route('/process_booking', methods=['POST'])
@login_required
def process_booking():
    location_id = request.form.get('location')
    date = request.form.get('date')
    time_slot = request.form.get('timeSlot')
    
    if not all([location_id, date, time_slot]):
        flash('Please fill in all required fields')
        return redirect(url_for('booking_schedule'))
    
    start_time, end_time = time_slot.split('-')
    
    # Create booking
    booking = Booking(
        location_id=location_id,
        session_date=datetime.strptime(date, '%Y-%m-%d'),
        start_time=datetime.strptime(start_time, '%H:%M').time(),
        end_time=datetime.strptime(end_time, '%H:%M').time(),
        user_id=session['user_id']
    )
    
    try:
        db.session.add(booking)
        db.session.commit()
        flash('Booking successful!')
        return redirect(url_for('booking_confirmation', booking_id=booking.id))
    except:
        db.session.rollback()
        flash('An error occurred. Please try again.')
        return redirect(url_for('booking_schedule'))

@app.route('/update_payment_status', methods=['POST'])
@login_required
def update_payment_status():
    try:
        booking_id = request.form.get('booking_id')
        coupon_code = request.form.get('coupon_code')
        gross_amount = request.form['gross_amount']
        item_name = request.form['item_name']
        
        first_booking = Booking.query.get_or_404(booking_id)
        
        # Apply coupon if provided
        discount_amount = 0
        if coupon_code:
            coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()
            if coupon and (not coupon.valid_until or coupon.valid_until >= datetime.now().date()):
                discount_amount = coupon.discount_amount
        print(discount_amount)
        # Update payment status for all bookings with the same group_id
        bookings = Booking.query.filter_by(
            group_id=first_booking.group_id,
            user_id=session['user_id']
        ).all()
        
        for booking in bookings:
            booking.payment_status = 'pending'
            booking.applied_discount = discount_amount
        
        db.session.commit()
        
        # Membuat transaksi
        transaction_details = {
            "order_id": booking_id,
            "gross_amount": int(gross_amount)  # Jumlah total transaksi
        }

        # Detail item
        items = [
            {
                "id": item_name,
                "price": int(gross_amount),
                "quantity": 1,
                "name": "Kupon "+item_name
            }
        ]

        # Detil pembayaran
        customer_details = {
            "first_name": "Wali",
            "last_name": "Data",
            "email": "waliyudin7@gmail.com",
            "phone": "+628123456789"
        }

        # Data transaksi yang akan dikirim ke Midtrans
        transaction = {
            "transaction_details": transaction_details,
            "item_details": items,
            "customer_details": customer_details
        }

        # Buat transaksi menggunakan Snap API
        payment_token = snap.create_transaction(transaction)
        # Kembalikan token yang bisa digunakan untuk transaksi di sisi klien
        return jsonify({'token': payment_token['token']})
        # return jsonify({'success': True, 'message': 'Payment status updated successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})
    
@app.route('/notification', methods=['POST'])
def notification():
    try:
        # Ambil data notifikasi yang dikirimkan oleh Midtrans
        notification = request.get_json()
        
        # Cek status pembayaran
        status_code = notification['transaction_status']
        order_id = notification['order_id']
        print(status_code)
        if status_code == 'settlement':
            # Transaksi berhasil dan terkonfirmasi
            first_booking = Booking.query.get_or_404(order_id)
            bookings = Booking.query.filter_by(
                group_id=first_booking.group_id,
            ).all()
            
            for booking in bookings:
                booking.payment_status = 'paid'
            
            db.session.commit()
            print(f"Transaction {order_id} captured successfully!")
        elif status_code == 'pending':
            # Transaksi sedang menunggu konfirmasi
            first_booking = Booking.query.get_or_404(order_id)
            bookings = Booking.query.filter_by(
                group_id=first_booking.group_id,
            ).all()
            
            for booking in bookings:
                booking.payment_status = 'pending'
            
            db.session.commit()
            print(f"Transaction {order_id} is pending.")
        elif status_code == 'deny':
            # Pembayaran ditolak
            first_booking = Booking.query.get_or_404(order_id)
            bookings = Booking.query.filter_by(
                group_id=first_booking.group_id,
            ).all()
            
            for booking in bookings:
                booking.payment_status = 'failed'
            
            db.session.commit()
            print(f"Transaction {order_id} denied.")
        else:
            print(f"Unknown transaction status for {order_id}: {status_code}")

        return jsonify({'status': 'received'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
        
@app.route('/confirmed_bookings', methods=['POST'])
@login_required
def confirmed_bookings():
    try:
        booking_id = request.form.get('booking_id')
        first_booking = Booking.query.get_or_404(booking_id)
        
        # Delete all bookings with the same group_id
        bookings = Booking.query.filter_by(
            group_id=first_booking.group_id,
            user_id=session['user_id']
        ).all()
        
        for booking in bookings:
            booking.payment_status = 'paid'
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Bookings cancelled successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/cancel_bookings', methods=['POST'])
@login_required
def cancel_bookings():
    try:
        booking_id = request.form.get('booking_id')
        first_booking = Booking.query.get_or_404(booking_id)
        
        # Delete all bookings with the same group_id
        bookings = Booking.query.filter_by(
            group_id=first_booking.group_id,
            user_id=session['user_id']
        ).all()
        
        for booking in bookings:
            db.session.delete(booking)
        
        db.session.commit()
        return jsonify({'success': True, 'message': 'Bookings cancelled successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/apply_coupon', methods=['POST'])
@login_required
def apply_coupon():
    coupon_code = request.form.get('coupon_code')
    
   # coupon = Coupon.query.filter_by(code=coupon_code, is_active=True).first()

    # Query for either user-specific coupon or general coupon
    coupon = Coupon.query.filter(
        Coupon.code == coupon_code,
        Coupon.is_active == True,
        db.or_(
            Coupon.user_id == session['user_id'],  # User-specific coupon
            Coupon.user_id == None  # General coupon
        )
    ).first()
    
        
    if not coupon:
        return jsonify({
            'success': False,
            'message': 'Kode kupon tidak valid'
        })
    
    if coupon.valid_until and coupon.valid_until < datetime.now().date():
        return jsonify({
            'success': False,
            'message': 'Kode kupon sudah kadaluarsa'
        })
    
    return jsonify({
        'success': True,
        'discount_amount': coupon.discount_amount,
        'message': f'Kupon berhasil diterapkan! Diskon Rp {coupon.discount_amount:,}'
    })

@app.route('/my_schedules')
@login_required
def my_schedules():
    # Get all bookings for the current user, ordered by date
    bookings = Booking.query.filter_by(
        user_id=session['user_id']
    ).order_by(
        Booking.session_date.desc(),
        Booking.start_time
    ).all()
    
    # Group bookings by group_id for package bookings
    grouped_bookings = {}
    single_bookings = []
    
    for booking in bookings:
        if booking.group_id:
            if booking.group_id not in grouped_bookings:
                grouped_bookings[booking.group_id] = []
            grouped_bookings[booking.group_id].append(booking)
        else:
            single_bookings.append(booking)
    
    return render_template(
        'my_schedules.html',
        grouped_bookings=grouped_bookings,
        single_bookings=single_bookings
    )

# Routes for ASA pool
@app.route('/asa')
def asa_packages():
    packages = ASAPool.query.all()
    return render_template('asa/packages.html', packages=packages)

@app.route('/asa/schedule/<int:package_id>')
@login_required
def asa_schedule(package_id):
    package = ASAPool.query.get_or_404(package_id)
    schedules = ASASchedule.query.filter_by(package_id=package_id).all()
    return render_template('asa/schedule.html', package=package, schedules=schedules)

@app.route('/asa/book/<int:package_id>', methods=['POST'])
@login_required
def asa_book(package_id):
    package = ASAPool.query.get_or_404(package_id)
    
    booking = ASABooking(
        user_id=session['user_id'],
        package_id=package_id,
        payment_status='pending',
        is_active=True  # Set active immediately
    )
    
    # Calculate next payment date
    today = datetime.now().date()
    if today.day > 10:
        next_month = today.replace(day=1) + timedelta(days=32)
        booking.next_payment_date = next_month.replace(day=1)
    else:
        next_month = today.replace(day=1) + timedelta(days=32)
        booking.next_payment_date = next_month.replace(day=1)
    
    booking.recurring_payment_date = 1
    
    db.session.add(booking)
    
    try:
        db.session.commit()  # Commit booking first to get booking_id
        
        # Create booking sessions immediately
        # Calculate start and end dates
        start_date = today
        if today.day > 10:  # If after 10th, start from next month
            start_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        else:  # If before 10th, start from current month
            start_date = today.replace(day=1)
        
        # End date is the last day of the month
        end_date = (start_date.replace(day=1) + timedelta(days=32)).replace(day=1)
        
        # Day name translation dictionary
        day_translations = {
            'MONDAY': 'SENIN',
            'TUESDAY': 'SELASA',
            'WEDNESDAY': 'RABU',
            'THURSDAY': 'KAMIS',
            'FRIDAY': 'JUMAT',
            'SATURDAY': 'SABTU',
            'SUNDAY': 'MINGGU'
        }
        
        # Get all schedules for this package
        schedules = ASASchedule.query.filter_by(package_id=booking.package_id).all()
        
        # Create sessions for each day until end of month
        current_date = start_date
        while current_date < end_date:
            english_day = current_date.strftime('%A').upper()
            indo_day = day_translations[english_day]
            
            # Find matching schedule for this day
            for schedule in schedules:
                if schedule.day_name == indo_day:
                    booking_session = ASABookingSession(  # Changed variable name to avoid conflict
                        booking_id=booking.id,
                        schedule_id=schedule.id,
                        session_date=current_date,
                        start_time=schedule.start_time,
                        end_time=schedule.end_time,
                        status='scheduled'
                    )
                    db.session.add(booking_session)
            current_date += timedelta(days=1)
        
        db.session.commit()
        return redirect(url_for('asa_booking_confirmation', booking_id=booking.id))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while processing your booking. Please try again.', 'error')
        return redirect(url_for('asa_packages'))

@app.route('/asa/booking_confirmation/<string:booking_id>')
@login_required
def asa_booking_confirmation(booking_id):
    booking = ASABooking.query.get_or_404(booking_id)
    package = ASAPool.query.get(booking.package_id)
    
    # Check if registration is after the 10th
    today = datetime.now().date()
    is_prorated = today.day > 10
    
    return render_template('asa/payment_transfer.html', 
                         booking=booking,
                         package=package,
                         is_prorated=is_prorated,
                         now=datetime.now())

@app.route('/update_asa_payment_status', methods=['POST'])
@login_required
def update_asa_payment_status():
    try:
        booking_id = request.form.get('booking_id')
        applied_discount = int(request.form.get('applied_discount', 0))
        
        booking = ASABooking.query.get_or_404(booking_id)
        
        # Update booking payment status to 'paid'
        booking.payment_status = 'paid'
        booking.applied_discount = applied_discount
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Payment status updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/asa/my_schedule/<string:booking_id>')
@login_required
def asa_my_schedule(booking_id):
    booking = ASABooking.query.get_or_404(booking_id)
    package = ASAPool.query.get(booking.package_id)
    
    # Get all sessions ordered by date
    sessions = ASABookingSession.query\
        .join(ASASchedule)\
        .filter(ASABookingSession.booking_id == booking_id)\
        .order_by(ASABookingSession.session_date)\
        .all()
    
    return render_template('asa/my_schedule.html', 
                         booking=booking,
                         package=package,
                         sessions=sessions)

@app.route('/asa/payment', methods=['POST'])
@login_required
def asa_payment():
    package_id = request.form.get('package_id')
    payment_method = request.form.get('payment_method')
    
    package = ASAPool.query.get_or_404(package_id)
    
    # Create booking
    booking = ASABooking(
        user_id=session['user_id'],
        package_id=package_id
    )
    db.session.add(booking)
    
    try:
        db.session.commit()
        
        # If payment method is transfer, show transfer instructions
        if payment_method == 'transfer':
            return render_template('asa/payment_transfer.html', 
                                booking=booking,
                                package=package)
        # If payment method is QRIS, show QR code
        else:
            return render_template('asa/payment_qris.html',
                                booking=booking,
                                package=package)
                                
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while processing your booking. Please try again.', 'error')
        return redirect(url_for('asa_packages'))

@app.route('/apply_asa_coupon', methods=['POST'])
@login_required
def apply_asa_coupon():
    coupon_code = request.form.get('coupon_code')
    package_price = request.form.get('package_price', type=int)
    
    # Query for either user-specific coupon or general coupon
    coupon = Coupon.query.filter(
        Coupon.code == coupon_code,
        Coupon.is_active == True,
        db.or_(
            Coupon.user_id == session['user_id'],  # User-specific coupon
            Coupon.user_id == None  # General coupon
        )
    ).first()
    
    if not coupon:
        return jsonify({
            'success': False,
            'message': 'Kode kupon tidak valid'
        })
    
    if coupon.valid_until and coupon.valid_until < datetime.now().date():
        return jsonify({
            'success': False,
            'message': 'Kupon sudah kadaluarsa'
        })

    if coupon.discount_amount > package_price:
        return jsonify({
            'success': False,
            'message': 'Nilai kupon melebihi harga paket'
        })

    return jsonify({
        'success': True,
        'discount_amount': coupon.discount_amount,
        'message': f'Kupon berhasil diterapkan! Diskon Rp {coupon.discount_amount:,}'
    })

# Function to initialize ASA packages and schedules
def initialize_asa_data():
    # Create packages
    regular_package = ASAPool(
        package_name='Reguler',
        price=350000,
        description='3x per minggu (Selasa, Kamis, Sabtu sore)',
        is_morning_available=False,
        sessions_per_month=12
    )

    morning_package = ASAPool(
        package_name='Reguler + Pagi',
        price=400000,
        description='6x per minggu (Senin, Rabu, Jumat pagi & Selasa, Kamis, Sabtu sore)',
        is_morning_available=True,
        sessions_per_month=12
    )

    trial_package = ASAPool(
        package_name='Trial',
        price=90000,
        description='1x Trial Session',
        is_morning_available=False,
        sessions_per_month=1,
        is_trial=True
    )

    db.session.add_all([regular_package, morning_package, trial_package])
    db.session.flush()

    # Create schedules
    schedules = []
    
    # Regular package schedules (afternoon only)
    regular_schedules = [
        ('SELASA', '16:00', '17:30'),
        ('KAMIS', '16:00', '17:30'),
        ('SABTU', '16:00', '17:30')
    ]

    for day, start, end in regular_schedules:
        schedules.append(ASASchedule(
            package_id=regular_package.id,
            day_name=day,
            start_time=datetime.strptime(start, '%H:%M').time(),
            end_time=datetime.strptime(end, '%H:%M').time()
        ))

    # Regular + Morning package schedules (morning and afternoon)
    morning_schedules = [
        ('SENIN', '05:00', '06:30'),
        ('SELASA', '16:00', '17:30'),
        ('RABU', '05:00', '06:30'),
        ('KAMIS', '16:00', '17:30'),
        ('JUMAT', '05:00', '06:30'),
        ('SABTU', '16:00', '17:30')
    ]

    for day, start, end in morning_schedules:
        schedules.append(ASASchedule(
            package_id=morning_package.id,
            day_name=day,
            start_time=datetime.strptime(start, '%H:%M').time(),
            end_time=datetime.strptime(end, '%H:%M').time()
        ))

    # Trial package schedules (same as regular afternoon schedule)
    trial_schedules = [
        ('SELASA', '16:00', '17:30'),
        ('KAMIS', '16:00', '17:30'),
        ('SABTU', '16:00', '17:30')
    ]

    for day, start, end in trial_schedules:
        schedules.append(ASASchedule(
            package_id=trial_package.id,
            day_name=day,
            start_time=datetime.strptime(start, '%H:%M').time(),
            end_time=datetime.strptime(end, '%H:%M').time()
        ))

    db.session.add_all(schedules)
    db.session.commit()

@app.route('/home')
@login_required
def home():
    today = datetime.now().date()
    
    # Get ASA bookings
    asa_bookings = ASABooking.query.filter_by(
        user_id=session['user_id']
    ).order_by(ASABooking.booking_date.desc()).all()
    
    # Get KCC bookings
    kcc_bookings = KCCBooking.query.filter_by(
        user_id=session['user_id']
    ).order_by(KCCBooking.booking_date.desc()).all()
    
    # Get regular swimming school bookings
    all_bookings = Booking.query.filter_by(
        user_id=session['user_id']
    ).order_by(Booking.session_date.desc()).all()

    # Separate bookings into grouped and single
    grouped_bookings = {}
    single_bookings = []

    for booking in all_bookings:
        if booking.group_id:
            if booking.group_id not in grouped_bookings:
                grouped_bookings[booking.group_id] = []
            grouped_bookings[booking.group_id].append(booking)
        else:
            single_bookings.append(booking)

    return render_template('home.html',
                         asa_bookings=asa_bookings,
                         kcc_bookings=kcc_bookings,
                         grouped_bookings=grouped_bookings,
                         single_bookings=single_bookings,
                         today=today)

@app.route('/admin')
@admin_required
def admin_dashboard():
    # Get filters from query params
    selected_date = request.args.get('date')
    selected_location = request.args.get('location', type=int)
    selected_time = request.args.get('time')

    if selected_date:
        selected_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
    else:
        selected_date = datetime.now().date()

    # Get KCC bookings for today
    kcc_sessions = KCCBookingSession.query\
        .filter(KCCBookingSession.session_date == selected_date)\
        .order_by(KCCBookingSession.start_time)\
        .all()

    # Get all unique times from quotas
    available_times = db.session.query(distinct(Quota.start_time)).all()
    available_times = [time[0].strftime('%H:%M') for time in available_times]

    # Calculate bookings count per location and time slot
    bookings_count = {}
    for location in Location.query.all():
        for quota in location.quotas:
            if quota.day_name == selected_date.strftime('%A'):
                time_str = quota.start_time.strftime('%H:%M')
                count = Booking.query.filter(
                    Booking.location_id == location.id,
                    Booking.session_date == selected_date,
                    Booking.start_time == quota.start_time
                ).count()
                bookings_count[(location.id, time_str)] = count

    # Get daily bookings
    bookings_query = Booking.query.filter(Booking.session_date == selected_date)
    if selected_location:
        bookings_query = bookings_query.filter(Booking.location_id == selected_location)
    if selected_time:
        time_obj = datetime.strptime(selected_time, '%H:%M').time()
        bookings_query = bookings_query.filter(Booking.start_time == time_obj)
    
    daily_bookings = bookings_query.all()

    # Get ASA schedules and bookings for the Swimming Club tab
    asa_schedules = ASASchedule.query.all()
    asa_bookings = ASABooking.query.order_by(ASABooking.booking_date.desc()).limit(10).all()

    return render_template(
        'admin/dashboard.html',
        selected_date=selected_date,
        selected_location=selected_location,
        selected_time=selected_time,
        kcc_sessions=kcc_sessions,
        locations=Location.query.all(),
        available_times=available_times,
        bookings_count=bookings_count,
        daily_bookings=daily_bookings,
        asa_schedules=asa_schedules,
        asa_bookings=asa_bookings
    )

@app.route('/update_presence_batch', methods=['POST'])
@admin_required
def update_presence_batch():
    data = request.get_json()
    updates = data.get('updates', [])
    
    try:
        for update in updates:
            booking = Booking.query.get(update['booking_id'])
            if booking:
                booking.presence_status = update['presence_status']
                booking.notes = update['notes']
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.cli.command("create-admin")
def create_admin():
    """Create an admin user."""
    username = input("Enter admin username: ")
    email = input("Enter admin email: ")
    password = input("Enter admin password: ")
    
    try:
        admin = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            is_admin=True
        )
        db.session.add(admin)
        db.session.commit()
        print("Admin user created successfully!")
    except Exception as e:
        db.session.rollback()
        print(f"Error creating admin user: {str(e)}")

@app.route('/admin/schedule_changes')
@admin_required
def admin_schedule_changes():
    # Get username filter from query parameters
    username_filter = request.args.get('username', '').strip()
    
    # Base query for all swimming school bookings
    bookings_query = Booking.query
    
    # Apply username filter if provided
    if username_filter:
        bookings_query = bookings_query.join(User).filter(
            User.username.ilike(f'%{username_filter}%')
        )
    else:
        # If no filter, don't show any bookings
        return render_template(
            'admin/schedule_changes.html',
            grouped_bookings={},
            single_bookings=[],
            locations=Location.query.all(),
            username_filter=''
        )
    
    # Get all bookings ordered by date
    bookings = bookings_query.order_by(
        Booking.session_date.desc(),
        Booking.start_time
    ).all()
    
    # Group bookings by group_id for package bookings
    grouped_bookings = {}
    single_bookings = []
    
    for booking in bookings:
        if booking.group_id:
            if booking.group_id not in grouped_bookings:
                grouped_bookings[booking.group_id] = []
            grouped_bookings[booking.group_id].append(booking)
        else:
            single_bookings.append(booking)
    
    return render_template(
        'admin/schedule_changes.html',
        grouped_bookings=grouped_bookings,
        single_bookings=single_bookings,
        locations=Location.query.all(),
        username_filter=username_filter
    )

@app.route('/admin/update_schedule', methods=['POST'])
@admin_required
def update_schedule():
    try:
        booking_id = request.form.get('booking_id')  # Now expecting a UUID string
        new_date = request.form.get('new_date')
        new_time = request.form.get('new_time')
        
        if not all([booking_id, new_date, new_time]):
            return jsonify({
                'success': False,
                'message': 'Missing required information'
            })

        # Get the booking using UUID string
        booking = Booking.query.get_or_404(booking_id)
        
        # Parse the new time slot (format: "HH:MM - HH:MM")
        start_time_str, end_time_str = new_time.split(' - ')
        new_start_time = datetime.strptime(start_time_str, '%H:%M').time()
        new_end_time = datetime.strptime(end_time_str, '%H:%M').time()
        
        # Update the booking with new date and time
        booking.session_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        booking.start_time = new_start_time
        booking.end_time = new_end_time

        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Schedule updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating schedule: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error updating schedule: {str(e)}'
        })

@app.route('/check_quota_availability', methods=['POST'])
@admin_required
def check_quota_availability():
    try:
        booking_id = request.form.get('booking_id')  # Now expecting a UUID string
        new_date = request.form.get('new_date')
        new_time = request.form.get('new_time')
        location_id = request.form.get('location_id')
        
        if not all([booking_id, new_date, new_time]):
            return jsonify({
                'available': False,
                'message': 'Missing required information'
            })

        # Get the booking using UUID string
        booking = Booking.query.get_or_404(booking_id)
        
        # If no new location selected, use current location
        if not location_id:
            location_id = booking.location_id
        
        # Convert date string to datetime
        selected_date = datetime.strptime(new_date, '%Y-%m-%d').date()
        day_name = selected_date.strftime('%A')
        
        # Get time slot details
        time_parts = new_time.split('-')
        start_time = datetime.strptime(time_parts[0].strip(), '%H:%M').time()
        end_time = datetime.strptime(time_parts[1].strip(), '%H:%M').time()
        
        # Get quota for the selected location, day and time slot
        quota = Quota.query.filter_by(
            location_id=location_id,
            day_name=day_name,
            start_time=start_time,
            end_time=end_time
        ).first()
        
        if not quota:
            return jsonify({
                'available': False,
                'message': f'No schedule available for this time slot at the selected location'
            })
        
        # Count existing bookings, excluding current booking using UUID
        existing_bookings = Booking.query.filter(
            Booking.location_id == location_id,
            Booking.session_date == selected_date,
            Booking.start_time == start_time,
            Booking.end_time == end_time,
            Booking.id != booking_id  # Using UUID string comparison
        ).count()
        
        available = existing_bookings < quota.quota
        remaining_slots = quota.quota - existing_bookings
        
        return jsonify({
            'available': available,
            'remaining_slots': remaining_slots,
            'message': f'Available slots: {remaining_slots}' if available else 'No slots available for this date and time'
        })
        
    except Exception as e:
        print(f"Error checking availability: {str(e)}")
        return jsonify({
            'available': False,
            'message': f'Error checking availability: {str(e)}'
        })

@app.route('/get_available_times', methods=['POST'])
@admin_required
def get_available_times():
    try:
        date = request.form.get('date')
        booking_id = request.form.get('booking_id')
        
        if not date or not booking_id:
            return jsonify({
                'success': False,
                'message': 'Date and booking ID are required'
            })
        
        # Get the booking to get its location
        booking = Booking.query.get_or_404(booking_id)
        location_id = booking.location_id
            
        # Convert date to day name (e.g., 'MONDAY', 'TUESDAY', etc.)
        day_name = datetime.strptime(date, '%Y-%m-%d').strftime('%A').upper()
        
        print(f"Fetching quotas for: Location={location_id}, Day={day_name}")  # Debug print
        
        # Get all quotas for this day and location
        quotas = Quota.query.filter_by(
            day_name=day_name,
            location_id=location_id
        ).all()
        
        print(f"Found {len(quotas)} quotas")  # Debug print
        
        time_slots = []
        for quota in quotas:
            time_slots.append({
                'id': quota.id,
                'time': f"{quota.start_time.strftime('%H:%M')} - {quota.end_time.strftime('%H:%M')}",
                'quota': quota.quota
            })
            print(f"Added time slot: {quota.start_time} - {quota.end_time}")  # Debug print
        
        return jsonify({
            'success': True,
            'time_slots': time_slots
        })
        
    except Exception as e:
        print(f"Error in get_available_times: {str(e)}")  # Debug print
        return jsonify({
            'success': False,
            'message': str(e)
        })

def send_payment_reminder_email(user_email, payment_date):
    # Implement your email sending logic here
    pass

@app.cli.command("send-payment-reminders")
def send_payment_reminders():
    """Send payment reminders for upcoming recurring payments"""
    today = datetime.now().date()
    reminder_date = today + timedelta(days=3)  # H-3
    
    # Find all active bookings with upcoming payments
    upcoming_payments = ASABooking.query.filter(
        ASABooking.is_active == True,
        ASABooking.next_payment_date == reminder_date
    ).all()
    
    for booking in upcoming_payments:
        send_payment_reminder_email(
            booking.user.email,
            booking.next_payment_date
        )

@app.route('/admin/asa_attendance')
@admin_required
def admin_asa_attendance():
    # Get date from query params or use today
    selected_date = request.args.get('date', datetime.now().date().strftime('%Y-%m-%d'))
    date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
    
    # Get all ASA sessions for the selected date
    sessions = ASABookingSession.query\
        .join(ASABooking)\
        .join(ASASchedule)\
        .filter(
            ASABookingSession.session_date == date_obj,
        )\
        .order_by(ASASchedule.start_time)\
        .all()

    return render_template(
        'admin/asa_attendance.html',
        sessions=sessions,
        selected_date=selected_date
    )

@app.route('/update_asa_presence_batch', methods=['POST'])
@admin_required
def update_asa_presence_batch():
    data = request.get_json()
    updates = data.get('updates', [])
    
    try:
        for update in updates:
            session = ASABookingSession.query.get(update['session_id'])
            if session:
                session.status = update['status']
                session.notes = update.get('notes', '')
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/notifications')
@login_required
def notifications():
    today = datetime.now().date()
    payment_notifications = []
    
    # Get ASA notifications
    asa_bookings = ASABooking.query.filter_by(
        user_id=session['user_id'],
        is_active=True
    ).all()
    
    # Get KCC notifications
    kcc_bookings = KCCBooking.query.filter_by(
        user_id=session['user_id'],
        is_active=True
    ).all()
    
    # Process ASA bookings
    for booking in asa_bookings:
        if booking.next_payment_date:
            days_until_payment = (booking.next_payment_date - today).days
            status = 'normal'
            if days_until_payment <= 3 and days_until_payment >= 0:
                status = 'urgent'
            elif days_until_payment < 0:
                status = 'overdue'
                
            payment_notifications.append({
                'booking_id': booking.id,
                'package_name': f"ASA - {booking.package.package_name}",
                'payment_date': booking.next_payment_date,
                'amount': booking.package.price,
                'days_until_payment': days_until_payment,
                'status': status,
                'type': 'asa'
            })
    
    # Process KCC bookings
    for booking in kcc_bookings:
        if booking.next_payment_date:
            days_until_payment = (booking.next_payment_date - today).days
            status = 'normal'
            if days_until_payment <= 3 and days_until_payment >= 0:
                status = 'urgent'
            elif days_until_payment < 0:
                status = 'overdue'
                
            payment_notifications.append({
                'booking_id': booking.id,
                'package_name': f"KCC - {booking.package.package_name}",
                'payment_date': booking.next_payment_date,
                'amount': booking.package.price,
                'days_until_payment': days_until_payment,
                'status': status,
                'type': 'kcc'
            })
    
    # Sort notifications by payment date
    payment_notifications.sort(key=lambda x: x['payment_date'])
    
    return render_template('notifications.html',
                         payment_notifications=payment_notifications,
                         today=today,
                         abs=abs)  # Add this line to make abs() available in template

@app.route('/payment_history')
@login_required
def payment_history():
    today = datetime.now().date()
    payment_history = []
    
    # Get ASA payment history
    asa_bookings = ASABooking.query.filter_by(
        user_id=session['user_id']
    ).all()
    
    # Get KCC payment history
    kcc_bookings = KCCBooking.query.filter_by(
        user_id=session['user_id']
    ).all()
    
    # Process ASA bookings
    for booking in asa_bookings:
        if booking.next_payment_date:
            status = 'paid' if booking.payment_status == 'paid' else (
                'overdue' if booking.next_payment_date < today else 'pending'
            )
            
            payment_history.append({
                'booking_id': booking.id,
                'package_name': f"ASA - {booking.package.package_name}",
                'payment_date': booking.next_payment_date,
                'period': booking.next_payment_date.strftime('%B %Y'),
                'amount': booking.package.price,
                'status': status,
                'is_active': booking.is_active,
                'type': 'asa'
            })
    
    # Process KCC bookings
    for booking in kcc_bookings:
        if booking.next_payment_date:
            status = 'paid' if booking.payment_status == 'paid' else (
                'overdue' if booking.next_payment_date < today else 'pending'
            )
            
            payment_history.append({
                'booking_id': booking.id,
                'package_name': f"KCC - {booking.package.package_name}",
                'payment_date': booking.next_payment_date,
                'period': booking.next_payment_date.strftime('%B %Y'),
                'amount': booking.package.price,
                'status': status,
                'is_active': booking.is_active,
                'type': 'kcc'
            })
    
    # Sort payment history by payment date (newest first)
    payment_history.sort(key=lambda x: x['payment_date'], reverse=True)
    
    return render_template('payment_history.html',
                         payment_history=payment_history,
                         today=today)

@app.route('/admin/coupons', methods=['GET', 'POST'])
@admin_required
def admin_coupons():
    if request.method == 'POST':
        try:
            code = request.form.get('code')
            discount_amount = request.form.get('discount_amount')
            valid_until = request.form.get('valid_until')
            user_id = request.form.get('user_id') or None  # None for general coupons
            
            # Basic validation
            if not code or not discount_amount:
                flash('Code and discount amount are required', 'error')
                return redirect(url_for('admin_coupons'))
            
            # Check if coupon code already exists
            if Coupon.query.filter_by(code=code).first():
                flash('Coupon code already exists', 'error')
                return redirect(url_for('admin_coupons'))
            
            # Create new coupon
            coupon = Coupon(
                code=code,
                discount_amount=discount_amount,
                valid_until=datetime.strptime(valid_until, '%Y-%m-%d').date() if valid_until else None,
                user_id=user_id,
                is_active=True
            )
            
            db.session.add(coupon)
            db.session.commit()
            flash('Coupon created successfully', 'success')
            return redirect(url_for('admin_coupons'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating coupon: {str(e)}', 'error')
            return redirect(url_for('admin_coupons'))
    
    # GET request - show coupons list
    coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    users = User.query.order_by(User.username).all()  # For user-specific coupons
    return render_template('admin/coupons.html', coupons=coupons, users=users)

@app.route('/admin/coupons/toggle/<int:coupon_id>', methods=['POST'])
@admin_required
def toggle_coupon(coupon_id):
    try:
        coupon = Coupon.query.get_or_404(coupon_id)
        coupon.is_active = not coupon.is_active
        db.session.commit()
        return jsonify({
            'success': True,
            'is_active': coupon.is_active
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/admin/coupons/delete/<int:coupon_id>', methods=['POST'])
@admin_required
def delete_coupon(coupon_id):
    try:
        coupon = Coupon.query.get_or_404(coupon_id)
        db.session.delete(coupon)
        db.session.commit()
        flash('Coupon deleted successfully', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting coupon: {str(e)}', 'error')
    return redirect(url_for('admin_coupons'))

@app.route('/admin/users/search')
@admin_required
def search_users():
    query = request.args.get('q', '')
    page = request.args.get('page', 1, type=int)
    per_page = 10

    # If no query, return empty results (except on first page)
    if not query and page > 1:
        return jsonify({'users': [], 'has_more': False})

    # Build the query
    users_query = User.query
    if query:
        users_query = users_query.filter(
            or_(
                User.username.ilike(f'%{query}%'),
                User.email.ilike(f'%{query}%')
            ))
    # Get paginated results
    users = users_query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'users': [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'text': f"{user.username} ({user.email})"
        } for user in users.items],
        'has_more': users.has_next
    })

@app.route('/coaches')
def coaches():
    coaches_list = Coach.query.filter_by(is_active=True).all()
    return render_template('coaches.html', coaches=coaches_list)

@app.route('/coach/<int:coach_id>')
def coach_profile(coach_id):
    coach = Coach.query.get_or_404(coach_id)
    return render_template('coach_profile.html', coach=coach)

@app.route('/pools')
def pools():
    pools_list = Pool.query.filter_by(is_active=True).all()
    return render_template('pools.html', pools=pools_list)

@app.route('/pool/<int:pool_id>')
def pool_profile(pool_id):
    pool = Pool.query.get_or_404(pool_id)
    # Convert string of gallery images to list
    gallery = pool.gallery_images.split(',') if pool.gallery_images else []
    # Convert string of features to list
    features = pool.features.split(',') if pool.features else []
    # Parse opening hours from JSON string
    opening_hours = json.loads(pool.opening_hours) if pool.opening_hours else {}
    
    return render_template('pool_profile.html', 
                         pool=pool,
                         gallery=gallery,
                         features=features,
                         opening_hours=opening_hours)

# Add KCC routes
@app.route('/kcc')
def kcc_packages():
    packages = KCCPool.query.all()
    return render_template('kcc/packages.html', packages=packages)

@app.route('/kcc/book/<int:package_id>', methods=['POST'])
@login_required
def kcc_book(package_id):
    package = KCCPool.query.get_or_404(package_id)
    
    booking = KCCBooking(
        user_id=session['user_id'],
        package_id=package_id,
        payment_status='pending',
        is_active=True  # Set active immediately
    )
    
    # Calculate next payment date
    today = datetime.now().date()
    if today.day > 10:
        next_month = today.replace(day=1) + timedelta(days=32)
        booking.next_payment_date = next_month.replace(day=1)
    else:
        next_month = today.replace(day=1) + timedelta(days=32)
        booking.next_payment_date = next_month.replace(day=1)
    
    booking.recurring_payment_date = 1
    
    db.session.add(booking)
    
    try:
        db.session.commit()  # Commit booking first to get booking_id
        
        # Create booking sessions immediately
        # Calculate start and end dates
        start_date = today
        if today.day > 10:  # If after 10th, start from next month
            start_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
        else:  # If before 10th, start from current month
            start_date = today.replace(day=1)
        
        # End date is the last day of the month
        end_date = (start_date.replace(day=1) + timedelta(days=32)).replace(day=1)
        
        # Day name translation dictionary
        day_translations = {
            'MONDAY': 'SENIN',
            'TUESDAY': 'SELASA',
            'WEDNESDAY': 'RABU',
            'THURSDAY': 'KAMIS',
            'FRIDAY': 'JUMAT',
            'SATURDAY': 'SABTU',
            'SUNDAY': 'MINGGU'
        }
        
        # Get all schedules for this package
        schedules = KCCSchedule.query.filter_by(package_id=booking.package_id).all()
        
        # Create sessions for each day until end of month
        current_date = start_date
        while current_date < end_date:
            english_day = current_date.strftime('%A').upper()
            indo_day = day_translations[english_day]
            
            # Find matching schedule for this day
            for schedule in schedules:
                if schedule.day_name == indo_day:
                    booking_session = KCCBookingSession(  # Changed variable name from 'session' to 'booking_session'
                        booking_id=booking.id,
                        schedule_id=schedule.id,
                        session_date=current_date,
                        start_time=schedule.start_time,
                        end_time=schedule.end_time,
                        status='scheduled'
                    )
                    db.session.add(booking_session)  # Using the new variable name
            current_date += timedelta(days=1)
        
        db.session.commit()
        return redirect(url_for('kcc_payment_transfer', booking_id=booking.id))
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while processing your booking. Please try again.', 'error')
        return redirect(url_for('kcc_packages'))

@app.route('/kcc/payment/transfer/<string:booking_id>')
@login_required
def kcc_payment_transfer(booking_id):
    booking = KCCBooking.query.get_or_404(booking_id)
    package = KCCPool.query.get(booking.package_id)
    
    # Check if registration is after the 10th
    today = datetime.now().date()
    is_prorated = today.day > 10
    
    return render_template(
        'kcc/payment_transfer.html',
        booking=booking,
        package=package,
        is_prorated=is_prorated
    )

@app.route('/apply_kcc_coupon', methods=['POST'])
@login_required
def apply_kcc_coupon():
    coupon_code = request.form.get('coupon_code')
    package_price = request.form.get('package_price', type=int)
    
    # Query for either user-specific coupon or general coupon
    coupon = Coupon.query.filter(
        Coupon.code == coupon_code,
        Coupon.is_active == True,
        db.or_(
            Coupon.user_id == session['user_id'],  # User-specific coupon
            Coupon.user_id == None  # General coupon
        )
    ).first()
    
    if not coupon:
        return jsonify({
            'success': False,
            'message': 'Kode kupon tidak valid'
        })
    
    if coupon.valid_until and coupon.valid_until < datetime.now().date():
        return jsonify({
            'success': False,
            'message': 'Kupon sudah kadaluarsa'
        })

    if coupon.discount_amount > package_price:
        return jsonify({
            'success': False,
            'message': 'Nilai kupon melebihi harga paket'
        })
    
    return jsonify({
        'success': True,
        'discount_amount': coupon.discount_amount,
        'message': f'Kupon berhasil diterapkan! Diskon Rp {coupon.discount_amount:,}'
    })

@app.route('/update_kcc_payment_status', methods=['POST'])
@login_required
def update_kcc_payment_status():
    try:
        booking_id = request.form.get('booking_id')
        applied_discount = int(request.form.get('applied_discount', 0))
        
        booking = KCCBooking.query.get_or_404(booking_id)
        
        # Update booking payment status to 'paid'
        booking.payment_status = 'paid'
        booking.applied_discount = applied_discount
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Payment status updated successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        })

@app.route('/admin/kcc_attendance')
@admin_required
def admin_kcc_attendance():
    # Get date from query params or use today
    selected_date = request.args.get('date', datetime.now().date().strftime('%Y-%m-%d'))
    date_obj = datetime.strptime(selected_date, '%Y-%m-%d').date()
    
    # Get all KCC sessions for the selected date
    sessions = KCCBookingSession.query\
        .join(KCCBooking)\
        .join(KCCSchedule)\
        .filter(
            KCCBookingSession.session_date == date_obj,
        )\
        .order_by(KCCSchedule.start_time)\
        .all()
    
    return render_template(
        'admin/kcc_attendance.html',
        sessions=sessions,
        selected_date=selected_date
    )

@app.route('/update_kcc_presence_batch', methods=['POST'])
@admin_required
def update_kcc_presence_batch():
    data = request.get_json()
    updates = data.get('updates', [])
    
    try:
        for update in updates:
            session = KCCBookingSession.query.get(update['session_id'])
            if session:
                session.status = update['status']
                session.notes = update.get('notes', '')
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/membership_management/<string:booking_id>')  # Changed from int to string
@login_required
def membership_management(booking_id):
    booking = ASABooking.query.get_or_404(booking_id)
    
    # Ensure user owns this booking
    if booking.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('index'))
    
    # Get upcoming sessions
    today = datetime.now().date()
    upcoming_sessions = ASABookingSession.query.filter(
        ASABookingSession.booking_id == booking_id,
        ASABookingSession.session_date >= today
    ).order_by(ASABookingSession.session_date).all()
    
    return render_template(
        'membership_management.html',
        booking=booking,
        upcoming_sessions=upcoming_sessions,
        today=today
    )

# Initialize scheduler
scheduler = BackgroundScheduler()

def create_monthly_sessions(booking_id, target_date):
    """Create sessions for a specific month"""
    booking = ASABooking.query.get(booking_id)
    if not booking:
        return
    
    # Calculate start and end dates for the month
    start_date = target_date.replace(day=1)
    next_month = (start_date + timedelta(days=32)).replace(day=1)
    
    # Day name translation dictionary
    day_translations = {
        'MONDAY': 'SENIN',
        'TUESDAY': 'SELASA',
        'WEDNESDAY': 'RABU',
        'THURSDAY': 'KAMIS',
        'FRIDAY': 'JUMAT',
        'SATURDAY': 'SABTU',
        'SUNDAY': 'MINGGU'
    }
    
    # Get all schedules for this package
    schedules = ASASchedule.query.filter_by(package_id=booking.package_id).all()
    
    # Create sessions for the month
    current_date = start_date
    while current_date < next_month:
        english_day = current_date.strftime('%A').upper()
        indo_day = day_translations[english_day]
        
        for schedule in schedules:
            if schedule.day_name == indo_day:
                # Check if session already exists
                existing_session = ASABookingSession.query.filter_by(
                    booking_id=booking_id,
                    session_date=current_date,
                    schedule_id=schedule.id
                ).first()
                
                if not existing_session:
                    booking_session = ASABookingSession(
                        booking_id=booking_id,
                        schedule_id=schedule.id,
                        session_date=current_date,
                        start_time=schedule.start_time,
                        end_time=schedule.end_time,
                        status='scheduled'
                    )
                    db.session.add(booking_session)
        
        current_date += timedelta(days=1)
    
    db.session.commit()

def create_monthly_kcc_sessions(booking_id, target_date):
    """Create KCC sessions for a specific month"""
    booking = KCCBooking.query.get(booking_id)
    if not booking:
        return
    
    # Similar logic as create_monthly_sessions but for KCC
    # ... (implement similar to ASA sessions)
    pass

def generate_next_month_sessions():
    """Generate sessions for next month for all active bookings"""
    try:
        # Calculate next month's date
        next_month = (datetime.now().date() + timedelta(days=32)).replace(day=1)
        
        # Generate ASA sessions
        active_asa_bookings = ASABooking.query.filter_by(is_active=True).all()
        for booking in active_asa_bookings:
            create_monthly_sessions(booking.id, next_month)
            
        # Generate KCC sessions
        active_kcc_bookings = KCCBooking.query.filter_by(is_active=True).all()
        for booking in active_kcc_bookings:
            create_monthly_kcc_sessions(booking.id, next_month)
            
        print(f"Successfully generated sessions for {next_month.strftime('%B %Y')}")
        
    except Exception as e:
        print(f"Error generating monthly sessions: {str(e)}")

def init_scheduler(app):
    with app.app_context():
        # Schedule the task to run on the 25th of every month at 00:01
        scheduler.add_job(
            func=generate_next_month_sessions,
            trigger=CronTrigger(day='25', hour='0', minute='1'),
            id='generate_monthly_sessions',
            name='Generate next month sessions',
            replace_existing=True
        )
        
        # Start the scheduler
        scheduler.start()

# Add this to your create_app or after app initialization
init_scheduler(app)

# Make sure to add graceful shutdown
@atexit.register
def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()

@app.route('/asa/pause_membership', methods=['POST'])
@login_required
def pause_membership():
    booking_id = request.form.get('booking_id')  # Already a string, no need to change
    pause_date = datetime.strptime(request.form.get('pause_date'), '%Y-%m').date()
    
    booking = ASABooking.query.get_or_404(booking_id)
    # ... rest of the function ...

@app.route('/asa/cancel_membership', methods=['POST'])
@login_required
def cancel_membership():
    booking_id = request.form.get('booking_id')  # Already a string, no need to change
    booking = ASABooking.query.get_or_404(booking_id)
    # ... rest of the function ...

@app.route('/kcc_membership_management/<string:booking_id>')
@login_required
def kcc_membership_management(booking_id):
    booking = KCCBooking.query.get_or_404(booking_id)
    
    # Ensure user owns this booking
    if booking.user_id != session['user_id']:
        flash('Unauthorized access', 'error')
        return redirect(url_for('index'))
    
    # Get upcoming sessions
    today = datetime.now().date()
    upcoming_sessions = KCCBookingSession.query.filter(
        KCCBookingSession.booking_id == booking_id,
        KCCBookingSession.session_date >= today
    ).order_by(KCCBookingSession.session_date).all()
    
    return render_template(
        'kcc/membership_management.html',
        booking=booking,
        upcoming_sessions=upcoming_sessions,
        today=today
    )

@app.route('/kcc/pause_membership', methods=['POST'])
@login_required
def kcc_pause_membership():
    booking_id = request.form.get('booking_id')
    pause_date = datetime.strptime(request.form.get('pause_date'), '%Y-%m').date()
    
    booking = KCCBooking.query.get_or_404(booking_id)
    
    if booking.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        # Mark all sessions in the pause month as 'paused'
        sessions = KCCBookingSession.query.filter(
            KCCBookingSession.booking_id == booking_id,
            extract('year', KCCBookingSession.session_date) == pause_date.year,
            extract('month', KCCBookingSession.session_date) == pause_date.month
        ).all()
        
        for session in sessions:
            session.status = 'paused'
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/kcc/cancel_membership', methods=['POST'])
@login_required
def kcc_cancel_membership():
    booking_id = request.form.get('booking_id')
    booking = KCCBooking.query.get_or_404(booking_id)
    
    if booking.user_id != session['user_id']:
        return jsonify({'success': False, 'message': 'Unauthorized'})
    
    try:
        # Mark booking as inactive
        booking.is_active = False
        
        # Mark all future sessions as cancelled
        today = datetime.now().date()
        future_sessions = KCCBookingSession.query.filter(
            KCCBookingSession.booking_id == booking_id,
            KCCBookingSession.session_date > today
        ).all()
        
        for session in future_sessions:
            session.status = 'cancelled'
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)})

@app.route('/change_password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        user = User.query.get(session['user_id'])
        
        if not check_password_hash(user.password_hash, current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('change_password'))
            
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('change_password'))
            
        user.password_hash = generate_password_hash(new_password)
        db.session.commit()
        flash('Password updated successfully', 'success')
        return redirect(url_for('index'))
        
    return render_template('change_password.html')

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()
        
        if user:
            try:
                # Generate reset token
                reset_token = token_urlsafe(32)
                user.reset_token = reset_token
                user.reset_token_expiry = datetime.utcnow() + timedelta(hours=24)
                db.session.commit()
                
                # Create reset link
                reset_link = url_for('reset_password', token=reset_token, _external=True)
                
                # Create email message
                msg = Message(
                    'Password Reset Request',
                    recipients=[user.email]
                )
                
                # Email content
                msg.html = render_template(
                    'email/reset_password.html',
                    user=user,
                    reset_link=reset_link
                )
                
                # Send email
                mail.send(msg)
                
                return jsonify({
                    'success': True,
                    'message': 'Password reset instructions have been sent to your email'
                })
                
            except Exception as e:
                print(f"Error sending email: {str(e)}")
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'message': 'An error occurred while sending the reset email. Please try again.'
                })
                
        # For security, don't reveal if email exists or not
        return jsonify({
            'success': True,
            'message': 'If an account exists with this email, you will receive reset instructions.'
        })
        
    return render_template('forgot_password.html')

@app.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    user = User.query.filter_by(reset_token=token).first()
    
    if not user or not user.reset_token_expiry or user.reset_token_expiry < datetime.utcnow():
        flash('Invalid or expired reset token. Please request a new password reset.', 'error')
        return redirect(url_for('forgot_password'))
        
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        
        if new_password != confirm_password:
            flash('Passwords do not match', 'error')
            return redirect(url_for('reset_password', token=token))
            
        user.password_hash = generate_password_hash(new_password)
        user.reset_token = None
        user.reset_token_expiry = None
        db.session.commit()
        
        # Send confirmation email
        try:
            msg = Message(
                'Password Reset Successful',
                recipients=[user.email]
            )
            msg.html = render_template(
                'email/reset_confirmation.html',
                user=user
            )
            mail.send(msg)
        except Exception as e:
            print(f"Error sending confirmation email: {str(e)}")
        
        flash('Your password has been reset successfully. You can now login with your new password.', 'success')
        return redirect(url_for('login'))
        
    return render_template('reset_password.html')

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    
    if request.method == 'POST':
        try:
            # Update user information
            user.full_name = request.form.get('full_name')
            user.birthdate = datetime.strptime(request.form.get('birthdate'), '%Y-%m-%d').date() if request.form.get('birthdate') else None
            user.parent_name = request.form.get('parent_name')
            user.address = request.form.get('address')
            user.mobile_phone = request.form.get('mobile_phone')
            user.school = request.form.get('school')
            user.gender = request.form.get('gender')
            
            db.session.commit()
            flash('Profile updated successfully!', 'success')
            return redirect(url_for('profile'))
            
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating your profile.', 'error')
            return redirect(url_for('profile'))
    
    return render_template('profile.html', user=user)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
