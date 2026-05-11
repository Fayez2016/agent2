import os
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'hitl-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://hermes:hermes123@db:5432/hitl')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

# Models
class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.Text, nullable=False)

class HITLRequest(db.Model):
    __tablename__ = 'hitl_requests'
    id = db.Column(db.Integer, primary_key=True)
    action_summary = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default='PENDING')
    requested_at = db.Column(db.DateTime, default=datetime.utcnow)
    resolved_at = db.Column(db.DateTime)
    resolved_by = db.Column(db.Integer, db.ForeignKey('users.id'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Routes
@app.route('/')
@login_required
def index():
    pending_requests = HITLRequest.query.filter_by(status='PENDING').order_by(HITLRequest.requested_at.desc()).all()
    return render_template('dashboard.html', requests=pending_requests)

@app.route('/history')
@login_required
def history():
    resolved_requests = HITLRequest.query.filter(HITLRequest.status.in_(['GRANTED', 'DENIED'])).order_by(HITLRequest.resolved_at.desc()).all()
    return render_template('history.html', requests=resolved_requests)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/resolve/<int:request_id>', methods=['POST'])
@login_required
def resolve(request_id):
    decision = request.form.get('decision')
    hitl_req = HITLRequest.query.get_or_404(request_id)
    
    if decision in ['GRANTED', 'DENIED']:
        hitl_req.status = decision
        hitl_req.resolved_at = datetime.utcnow()
        hitl_req.resolved_by = current_user.id
        db.session.commit()
        flash(f'Request {request_id} {decision.lower()} successfully.')
    
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
