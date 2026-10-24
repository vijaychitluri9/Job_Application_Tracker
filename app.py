from datetime import date, datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config["SECRET_KEY"] = "replace-with-a-long-random-secret-before-deployment"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///jobs.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please sign in to access your tracker."
login_manager.login_message_category = "info"

STATUSES = ["Applied", "Interview", "Offer", "Rejected", "Withdrawn"]

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    applications = db.relationship("JobApplication", backref="owner", lazy=True, cascade="all, delete-orphan")
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class JobApplication(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(120), nullable=False)
    job_type = db.Column(db.String(40), default="Full-time")
    location = db.Column(db.String(120), default="")
    job_url = db.Column(db.String(500), default="")
    status = db.Column(db.String(30), default="Applied", nullable=False)
    applied_date = db.Column(db.Date, default=date.today, nullable=False)
    interview_date = db.Column(db.Date, nullable=True)
    follow_up_date = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    def __repr__(self):
        return f"<JobApplication {self.company} - {self.role}>"

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None

def form_values():
    return {
        "company": request.form.get("company", "").strip(),
        "role": request.form.get("role", "").strip(),
        "job_type": request.form.get("job_type", "Full-time"),
        "location": request.form.get("location", "").strip(),
        "job_url": request.form.get("job_url", "").strip(),
        "status": request.form.get("status", "Applied"),
        "applied_date": parse_date(request.form.get("applied_date")) or date.today(),
        "interview_date": parse_date(request.form.get("interview_date")),
        "follow_up_date": parse_date(request.form.get("follow_up_date")),
        "notes": request.form.get("notes", "").strip(),
    }

@app.context_processor
def inject_globals():
    return {"statuses": STATUSES, "today": date.today()}

@app.route("/")
def home():
    return redirect(url_for("dashboard" if current_user.is_authenticated else "login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not name or not email or not password:
            flash("Please fill in every field.", "danger")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "danger")
        elif User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "warning")
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created successfully. Welcome!", "success")
            return redirect(url_for("dashboard"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Signed in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid email or password.", "danger")
    return render_template("login.html")

@app.post("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard")
@login_required
def dashboard():
    query = JobApplication.query.filter_by(user_id=current_user.id)
    applications = query.order_by(JobApplication.applied_date.desc()).all()
    counts = {status: sum(1 for job in applications if job.status == status) for status in STATUSES}
    upcoming = JobApplication.query.filter(
        JobApplication.user_id == current_user.id,
        JobApplication.interview_date.isnot(None),
        JobApplication.interview_date >= date.today()
    ).order_by(JobApplication.interview_date.asc()).limit(5).all()
    reminders = JobApplication.query.filter(
        JobApplication.user_id == current_user.id,
        JobApplication.follow_up_date.isnot(None),
        JobApplication.follow_up_date <= date.today() + timedelta(days=7),
        JobApplication.follow_up_date >= date.today(),
        JobApplication.status.notin_(["Offer", "Rejected", "Withdrawn"])
    ).order_by(JobApplication.follow_up_date.asc()).limit(5).all()
    return render_template("dashboard.html", applications=applications[:6], total=len(applications),
                           counts=counts, upcoming=upcoming, reminders=reminders)

@app.route("/applications")
@login_required
def applications():
    search = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    query = JobApplication.query.filter_by(user_id=current_user.id)
    if search:
        like = f"%{search}%"
        query = query.filter(db.or_(JobApplication.company.ilike(like), JobApplication.role.ilike(like)))
    if status in STATUSES:
        query = query.filter_by(status=status)
    rows = query.order_by(JobApplication.applied_date.desc()).all()
    return render_template("applications.html", applications=rows, search=search, selected_status=status)

@app.route("/applications/new", methods=["GET", "POST"])
@login_required
def add_application():
    if request.method == "POST":
        values = form_values()
        if not values["company"] or not values["role"]:
            flash("Company and job title are required.", "danger")
            return render_template("application_form.html", job=None, values=request.form, page_title="Add application")
        if values["status"] not in STATUSES:
            values["status"] = "Applied"
        job = JobApplication(**values, user_id=current_user.id)
        db.session.add(job)
        db.session.commit()
        flash("Application added successfully.", "success")
        return redirect(url_for("applications"))
    return render_template("application_form.html", job=None, values={}, page_title="Add application")

@app.route("/applications/<int:job_id>/edit", methods=["GET", "POST"])
@login_required
def edit_application(job_id):
    job = JobApplication.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    if request.method == "POST":
        values = form_values()
        if not values["company"] or not values["role"]:
            flash("Company and job title are required.", "danger")
            return render_template("application_form.html", job=job, values=request.form, page_title="Edit application")
        if values["status"] not in STATUSES:
            values["status"] = "Applied"
        for key, value in values.items():
            setattr(job, key, value)
        db.session.commit()
        flash("Application updated successfully.", "success")
        return redirect(url_for("applications"))
    values = {column.name: getattr(job, column.name) for column in JobApplication.__table__.columns}
    return render_template("application_form.html", job=job, values=values, page_title="Edit application")

@app.post("/applications/<int:job_id>/delete")
@login_required
def delete_application(job_id):
    job = JobApplication.query.filter_by(id=job_id, user_id=current_user.id).first_or_404()
    db.session.delete(job)
    db.session.commit()
    flash("Application deleted.", "info")
    return redirect(request.referrer or url_for("applications"))

@app.route("/reminders")
@login_required
def reminders_page():
    rows = JobApplication.query.filter(
        JobApplication.user_id == current_user.id,
        db.or_(JobApplication.interview_date.isnot(None), JobApplication.follow_up_date.isnot(None))
    ).order_by(JobApplication.follow_up_date.asc().nullslast(), JobApplication.interview_date.asc().nullslast()).all()
    return render_template("reminders.html", applications=rows)

@app.route("/seed-demo")
@login_required
def seed_demo():
    if JobApplication.query.filter_by(user_id=current_user.id).first():
        flash("Your account already contains applications; demo data was not added.", "info")
    else:
        samples = [
            JobApplication(company="Northstar Tech", role="Python Developer Intern", location="Hyderabad",
                           status="Interview", applied_date=date.today()-timedelta(days=8),
                           interview_date=date.today()+timedelta(days=3), follow_up_date=date.today()+timedelta(days=1),
                           notes="Prepare Flask and SQL interview topics.", user_id=current_user.id),
            JobApplication(company="BluePeak Systems", role="Software Engineer Intern", location="Remote",
                           status="Applied", applied_date=date.today()-timedelta(days=5),
                           follow_up_date=date.today()+timedelta(days=4), notes="Applied through company careers page.", user_id=current_user.id),
            JobApplication(company="Orbit Analytics", role="Data Analyst Intern", location="Bengaluru",
                           status="Offer", applied_date=date.today()-timedelta(days=18),
                           notes="Review offer details and joining date.", user_id=current_user.id),
            JobApplication(company="Greenfield Labs", role="Backend Developer", location="Pune",
                           status="Rejected", applied_date=date.today()-timedelta(days=24),
                           notes="Use feedback to improve API project.", user_id=current_user.id),
        ]
        db.session.add_all(samples)
        db.session.commit()
        flash("Demo records added to your account.", "success")
    return redirect(url_for("dashboard"))

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)
