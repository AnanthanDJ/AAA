#!/bin/bash

# Exit on any error
set -e

# Run the database initialization
python src/create_tables.py

# Start the Gunicorn server
gunicorn --timeout 300 src/app:app
