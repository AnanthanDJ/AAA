import os
import json
import textwrap
import google.generativeai as genai
from datetime import datetime
from flask import Flask, jsonify, render_template, request, redirect, url_for, flash, abort, session
from flask_cors import CORS
from dotenv import load_dotenv
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, UserMixin, login_user, logout_user, current_user, login_required
from wtforms import StringField, PasswordField, SubmitField, TextAreaField, FileField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Email
from werkzeug.utils import secure_filename
from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.chains import ConversationChain
from langchain.memory import ConversationBufferMemory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, HumanMessagePromptTemplate, SystemMessagePromptTemplate

load_dotenv()



# --- App Initialization ---

# Read the Gemini API key from the environment
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
if not GEMINI_API_KEY:
    print("Warning: GEMINI_API_KEY environment variable not set. AI features will not work.")
else:
    genai.configure(api_key=GEMINI_API_KEY)

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_secret_key')
instance_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'instance')
os.makedirs(instance_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'database.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy()
db.init_app(app)

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'uploads')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'
CORS(app)

# --- Database Models ---
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)
    projects = db.relationship('Project', backref='author', lazy=True)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    script_file_name = db.Column(db.String(200), nullable=False)
    analysis_json = db.Column(db.Text, nullable=True)
    genre = db.Column(db.String(50), nullable=True) # New column
    logline = db.Column(db.Text, nullable=True) # New column for AI-generated logline
    forecasted_budget = db.Column(db.Float, nullable=True, default=0.0) # New column for forecasted budget
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Schedule(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    task_description = db.Column(db.String(500), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    assigned_to = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(50), nullable=False, default='Pending')
    project = db.relationship('Project', backref='schedules', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Token Generation and Email Sending ---
@app.template_filter('from_json')
@app.template_filter('from_json')
def from_json_filter(value):
    if value is None:
        return None
    return json.loads(value)


# --- Forms ---
class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password = PasswordField('Confirm Password', validators=[DataRequired(), EqualTo('password')])
    submit = SubmitField('Sign Up')

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user:
            raise ValidationError('That email is taken. Please choose a different one.')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class ProjectForm(FlaskForm):
    name = StringField('Project Name', validators=[DataRequired()])
    script_file = FileField('Script File', validators=[FileRequired()])
    submit = SubmitField('Create Project')


# --- Database Initialization ---
@app.cli.command('init-db')
def init_db_command():
    """Creates the database tables."""
    db.create_all()
    print('Initialized the database.')


# --- Routes for the Frontend ---
@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('list_projects'))
    return render_template('index.html')

@app.route('/script_analysis')
@login_required
def script_analysis():
    project_id = request.args.get('project_id', type=int)
    project = None
    if project_id:
        project = Project.query.get_or_404(project_id)
        if project.author != current_user:
            abort(403) # Forbidden
    return render_template('script_analysis.html', project=project)



@app.route("/projects", methods=['GET'])
@login_required
def list_projects():
    projects = Project.query.filter_by(author=current_user).all()
    return render_template('projects.html', projects=projects)

@app.route("/projects/new", methods=['GET', 'POST'])
@login_required
def create_project():
    form = ProjectForm()
    if form.validate_on_submit():
        if form.script_file.data:
            filename = secure_filename(form.script_file.data.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            form.script_file.data.save(filepath)
            
            with open(filepath, 'r') as f:
                script_content = f.read()

            project = Project(name=form.name.data, script_file_name=filename, author=current_user)
            db.session.add(project)
            db.session.commit()
            flash('Your project has been created!', 'success')
            return redirect(url_for('list_projects'))
    return render_template('create_project.html', title='New Project', form=form)

@app.route("/projects/<int:project_id>")
@login_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden
    return render_template('project_detail.html', project=project)

# --- Authentication Routes ---
@app.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user = User(email=form.email.data, password=hashed_password)
        db.session.add(user)
        db.session.commit()

        flash('Your account has been created! You can now log in.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('index'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', title='Login', form=form)


@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('index'))


# --- Mock API Endpoints ---

@app.route('/api/script/analyze', methods=['POST'])
@login_required
def analyze_script():
    """
    Endpoint to perform AI script analysis using the Gemini API.
    """
    if not GEMINI_API_KEY:
        return jsonify({"error": "GEMINI_API_KEY not configured on the server."}), 500

    project_id = request.get_json().get('project_id')
    script_text = request.get_json().get('script')

    if not project_id:
        return jsonify({"error": "Project ID is required for script analysis."}), 400

    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if not script_text or not isinstance(script_text, str) or len(script_text.strip()) < 50:
        return jsonify({"error": "Invalid or insufficient script text provided."}), 400

    try:
        model = genai.GenerativeModel('gemini-2.5-pro')
        
        prompt = textwrap.dedent("""
            You are a professional script breakdown assistant for film production.
            Analyze the following script text and return a JSON object with the following structure:
            {{"genre": "FILM_GENRE",
            "characters": [{{"name": "CHARACTER_NAME", "dialogue_lines": COUNT}}],
            "locations": [{{"name": "LOCATION_NAME", "scenes": COUNT}}],
            "props": ["PROP_NAME_1", "PROP_NAME_2"],
            "estimated_scenes": TOTAL_SCENE_COUNT}}
            The "genre" should be one of the following: "Action", "Comedy", "Drama", "Horror", "Sci-Fi", "Thriller", "Romance", "Adventure", "Musical", "Indie".
            Only return the raw JSON object, with no surrounding text, comments, or markdown.
            Ensure the JSON is valid.
            Script: {script}
        """).format(script=script_text)

        response = model.generate_content(prompt)

        # Check if the response was blocked
        if response.prompt_feedback.block_reason:
            return jsonify({
                "error": "The AI request was blocked by the content filter.",
                "reason": response.prompt_feedback.block_reason.name,
            }), 500

        full_response_text = response.candidates[0].content.parts[0].text
        cleaned_response = full_response_text.strip().replace('```json', '').replace('```', '').strip()
        try:
            analysis_result = json.loads(cleaned_response)
            project.analysis_json = json.dumps(analysis_result) # Save analysis to project
            project.genre = analysis_result.get('genre') # Save the genre
            db.session.commit()
            return jsonify(analysis_result)
        except json.JSONDecodeError:
            # The AI didn't return valid JSON, log the bad response for debugging
            print("--- DEBUG: AI response was not valid JSON ---")
            print(cleaned_response)
            print("---------------------------------------------")
            return jsonify({"error": "Failed to parse the analysis from the AI response. The AI did not return valid JSON.", "raw_response_for_debugging": cleaned_response}), 500

    except Exception as e:
        # Catch other potential errors from the API call itself
        print(f"--- DEBUG: An unexpected error occurred: {e} ---")
        return jsonify({"error": f"An unexpected error occurred during the AI API call: {str(e)}"}), 500

@app.route('/api/project/<int:project_id>/script_content', methods=['GET'])
@login_required
def get_script_content(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if not project.script_file_name:
        return jsonify({"error": "No script file associated with this project."}), 404

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], project.script_file_name)
    if not os.path.exists(filepath):
        return jsonify({"error": "Script file not found on server."}), 404

    try:
        with open(filepath, 'r') as f:
            script_content = f.read()
        return jsonify({"script_content": script_content})
    except Exception as e:
        return jsonify({"error": f"Error reading script file: {str(e)}"}), 500


@app.route('/schedule/<int:project_id>')
@login_required
def schedule(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    script_analysis_results = session.get('script_analysis_results', {})
    characters = script_analysis_results.get('characters', [])
    locations = script_analysis_results.get('locations', [])
    props = script_analysis_results.get('props', [])

    schedule_items = Schedule.query.filter_by(project_id=project.id).order_by(Schedule.start_date).all()

    return render_template('schedule.html', project=project, schedule_items=schedule_items, characters=characters, locations=locations, props=props)

@app.route('/api/schedule/<int:project_id>', methods=['GET', 'POST'])
@login_required
def handle_schedule_items(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    if request.method == 'POST':
        data = request.get_json()
        new_schedule_item = Schedule(
            project_id=project.id,
            task_description=data['task_description'],
            start_date=datetime.strptime(data['start_date'], '%Y-%m-%d').date(),
            end_date=datetime.strptime(data['end_date'], '%Y-%m-%d').date(),
            assigned_to=data.get('assigned_to'),
            status=data.get('status', 'Pending')
        )
        db.session.add(new_schedule_item)
        db.session.commit()
        return jsonify({
            "id": new_schedule_item.id,
            "task_description": new_schedule_item.task_description,
            "start_date": new_schedule_item.start_date.isoformat(),
            "end_date": new_schedule_item.end_date.isoformat(),
            "assigned_to": new_schedule_item.assigned_to,
            "status": new_schedule_item.status
        }), 201
    else: # GET request
        schedule_items = Schedule.query.filter_by(project_id=project.id).order_by(Schedule.start_date).all()
        return jsonify([{
            "id": item.id,
            "task_description": item.task_description,
            "start_date": item.start_date.isoformat(),
            "end_date": item.end_date.isoformat(),
            "assigned_to": item.assigned_to,
            "status": item.status
        } for item in schedule_items])

@app.route('/api/schedule/item/<int:item_id>', methods=['PUT', 'DELETE'])
@login_required
def handle_single_schedule_item(item_id):
    schedule_item = Schedule.query.get_or_404(item_id)
    if schedule_item.project.author != current_user:
        abort(403) # Forbidden

    if request.method == 'PUT':
        data = request.get_json()
        schedule_item.task_description = data.get('task_description', schedule_item.task_description)
        schedule_item.start_date = datetime.strptime(data['start_date'], '%Y-%m-%d').date() if data.get('start_date') else schedule_item.start_date
        schedule_item.end_date = datetime.strptime(data['end_date'], '%Y-%m-%d').date() if data.get('end_date') else schedule_item.end_date
        schedule_item.assigned_to = data.get('assigned_to', schedule_item.assigned_to)
        schedule_item.status = data.get('status', schedule_item.status)
        db.session.commit()
        return jsonify({"message": "Schedule item updated."}), 200
    elif request.method == 'DELETE':
        db.session.delete(schedule_item)
        db.session.commit()
        return jsonify({"message": "Schedule item deleted."}), 200

@app.route('/api/project/<int:project_id>/update_budget', methods=['POST'])
@login_required
def update_project_budget(project_id):
    project = Project.query.get_or_404(project_id)
    if project.author != current_user:
        abort(403) # Forbidden

    data = request.get_json()
    new_budget = data.get('forecasted_budget')

    if new_budget is None or not isinstance(new_budget, (int, float)) or new_budget < 0:
        return jsonify({"error": "Invalid budget value provided."}), 400

    project.forecasted_budget = new_budget
    db.session.commit()
    return jsonify({"message": "Project budget updated successfully."}), 200


if __name__ == '__main__':
    app.run(debug=True, port=5000)
