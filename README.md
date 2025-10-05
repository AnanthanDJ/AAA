# CineHack.AI — AI-powered dashboard for film production
Team Members: [Your Name] (Developer), [Team Member 2] (Role)

## Elevator Pitch
CineHack.AI is an AI-powered dashboard designed to unify the film production lifecycle, offering AI script analysis and intelligent budget oversight to streamline pre-production and financial management.

## Live Demo
- URL / IP: `http://[YOUR_IP_OR_DOMAIN]:[PORT]`
- Endpoints: see `deployment/ENDPOINTS.MD`

## Quick Start (Local)
1. Clone repo
```bash
git clone https://github.com/your-org/your-repo.git
cd your-repo
```
2. Create `.env` from `.env.example` and set required variables.
3. Install dependencies:
```bash
pip install -r src/requirements.txt
```
4. Run database migrations:
```bash
python src/create_tables.py
```
5. Start the application:
```bash
bash scripts/start.sh
```
6. Open `http://localhost:5000` (or your configured port)

## Tests
```bash
# Add your test commands here
# For example: pytest tests/
```

## Environment Variables
*   `FLASK_APP` — The name of your Flask application entry point (e.g., `src/app.py`)
*   `FLASK_ENV` — The Flask environment (e.g., `development`, `production`)
*   `SECRET_KEY` — A secret key for session management
*   `DATABASE_URL` — DB connection string (e.g., `sqlite:///instance/database.db`)
*   `GEMINI_API_KEY` — Your Google Gemini API Key

## Known Limitations
*   Initial version, some features may be incomplete or have limited functionality.
*   Performance may vary based on script size and API response times.

## License
MIT

## Consent for Local Network Access
By submitting this project, we consent to event organizers and judges accessing the listed local endpoints while connected to the event Wi‑Fi for evaluation purposes. We understand that organizers will not access private customer data and will only use provided credentials.
