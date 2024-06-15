# Stacks Node Map Backend

This is the backend for the Stacks Node Map project. It's built with Flask and provides an API for the frontend.

## Installation

1. Clone the repository.
2. Create a virtual environment: `python3 -m venv .venv`
3. Activate the virtual environment: `source .venv/bin/activate`
4. Install the required packages: `pip install -r requirements.txt`
5. Copy the example environment file: `cp env.sh.example env.sh`
6. Open `env.sh` and modify the environment variables if needed.

## Usage

1. Start the Flask server: `python run.py api`
2. The server will start on `localhost:8089`.

## API Endpoints

- `/`: Returns a greeting message.
- `/nodes`: Returns the network and nodes data.

## Scripts

- `api`: Starts the Flask server.
- `discoverer`: Runs the discoverer script.

## Contributing

Please feel free to submit issues and pull requests.

