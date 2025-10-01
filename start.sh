#!/bin/bash

# Exit on any error
set -e

# Run the database initialization
flask init-db

# Start the Gunicorn server
gunicorn app:app
