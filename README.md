# CineHack.AI — AI-powered dashboard for film production

Team Members: CineHack.AI Team (Developers)

## Elevator Pitch
CineHack.AI is an AI-powered dashboard designed to unify the film production lifecycle, offering AI script analysis and intelligent budget oversight to streamline pre-production and financial management.

## Live Demo
- URL / IP: `http://127.0.0.1:5000`
- Endpoints: see `deployment/ENDPOINTS.md`

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
6. Open `http://127.0.0.1:5000` (or your configured port)

## Tests
```bash
pytest tests/
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

## Attributions
*   **Google Gemini Pro API:** For AI Script Analysis and the AI Copilot features.
*   **Flask:** Python web framework used for the backend API.
*   **scikit-learn:** Machine learning library for the predictive analytics engine.
*   **Numpy:** Numerical computing library, often used in conjunction with scikit-learn.
*   **LangChain:** Framework for integrating Large Language Models.
*   **Rich:** Python library for rich text and beautiful formatting in the terminal (if used in the application itself).
*   **SQLite:** Serverless, file-based database.
*   **Dark-themed HTML/CSS Template:** (If applicable, specify source if known, e.g., "Template adapted from [Source Name/URL]").
*   **GitHub Copilot Pro:** (Optional, if you want to acknowledge its assistance in code generation).

## Consent for Local Network Access
By submitting this project, we consent to event organizers and judges accessing the listed local endpoints while connected to the event Wi‑Fi for evaluation purposes. We understand that organizers will not access private customer data and will only use provided credentials.