#!/bin/bash

# Exit on any error
set -e

# Run the database initialization
python create_tables.py

# Start the Gunicorn server
gunicorn --timeout 300 app:app
