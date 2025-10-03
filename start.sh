#!/bin/bash

# Exit on any error
set -e

# Run the database initialization


# Start the Gunicorn server
gunicorn app:app
