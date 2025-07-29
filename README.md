# ClearNebel Agent Builder

A modular, extensible framework for building sophisticated, multi-user AI applications. This project features a concurrent multi-agent backend, a persistent web-based chat interface with role-based user management, and a complete, human-in-the-loop data pipeline for continuously improving models with Direct Preference Optimization (DPO).

## Core Architecture & Features

The system is architected as a set of decoupled services for scalability and robustness:

*   **Django Web Application (`web`):** A user-facing web interface that handles user accounts, chat history, and an admin panel. It places user requests onto a job queue.
*   **AI Worker Pool (`agent/worker.py`):** A separate, long-running Python process that manages a pool of concurrent AI workers. Each worker loads a Gemma model instance and processes jobs from the queue.
*   **Redis Server:** A high-performance message broker that acts as the communication layer between the web app and the AI workers.
*   **Admin CLI (`agent/manage_agent.py`):** A comprehensive command-line tool for all backend administration, including creating, configuring, and training agents.
*   **Human-in-the-Loop Data Curation:** The web admin panel includes a "Feedback Curation" dashboard where administrators can review user-rejected messages, correct routing errors, and write ideal responses. This curated data is used to improve the AI models.
*   **SFT & DPO Training Pipeline:** The system includes scripts and commands for both initial Supervised Fine-Tuning (SFT) and subsequent preference-based tuning using Direct Preference Optimization (DPO), creating a full data flywheel.

## Project Structure

```
your_main_project_folder/
├── agent/                  # The backend AI system
│   ├── app/                # Core logic for the agent interaction loop
│   ├── configs/            # All configuration files (agents, prompts)
│   ├── data/               # Training data and RAG knowledge base
│   ├── models/             # Fine-tuned model adapters and RAG index
│   ├── rag/                # RAG system logic
│   ├── tools/              # Custom agent tools
│   ├── training/           # Fine-tuning scripts
│   └── manage_agent.py     # The main administrative CLI tool
│   └── worker.py           # The worker script
│
└── web/                    # The Django web application
    ├── accounts/           # User registration and login
    ├── admin_panel/        # Custom admin UI for permissions
    ├── chat/               # The main chat interface
    └── llm_frontend/       # Django project settings
    └── main/               # The Main app for global settings
```

## Local Python Setup Guide

This guide will walk you through setting up and running the entire application natively on your machine.

### Step 1: Prerequisites
*   **Python 3.11+** and `pip`.
*   **Git** for cloning the repository.
*   **A running Redis Server.** Redis must be installed and running on `localhost:6379`.
    *   On Debian/Ubuntu: `sudo apt update && sudo apt install redis-server`
    *   On macOS: `brew install redis && brew services start redis`
    *   On Windows: Use WSL2 to install and run the Linux version of Redis.
*   Tested on Debian 12 (Bookworm) and an NVIDIA Graphics Card.

### Step 2: Create Virtual Environment & Install Dependencies
It is highly recommended to use a single Python virtual environment for the entire project.

```bash
# From the project's root directory (your_main_project_folder/)
# Create the virtual environment
python -m venv .venv

# Activate it
# On Linux/macOS:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate

# Install all required packages from both applications
pip install -r requirements.txt
```

### Step 3: Hugging Face Authentication
The backend needs to download the Gemma model. You must be logged in with an account that has been granted access.

```bash
huggingface-cli login
# Paste your Hugging Face access token when prompted.
```

### Step 4: Initial Application Setup (Database & RAG)
These commands set up the Django database and build the search index for the RAG system.

```bash
# First, navigate into the frontend directory
cd web

# Apply database migrations to create user, chat, and permission tables
python manage.py migrate

# Create your superuser/admin account for the web UI and Django admin
python manage.py createsuperuser

# Navigate back and into the backend directory
cd ../agent

# Make sure to populate data/knowledge_base.txt with your documents first
python -m rag.build_index
```

## Running the Application

To run the full application, you will need **two separate terminals** running concurrently. A third terminal is needed for administrative tasks. Make sure your virtual environment is activated in each terminal.

### Terminal 1: Start the AI Workers
This process is the AI backend. It will load the models and listen for jobs from Redis.

```bash
# Setup Redis Instace
docker run -d --name redis -p 6379:6379 -e REDIS_PASSWORD=your_strong_redis_password_here redis:latest redis-server --requirepass your_strong_redis_password_here

# Start Redis Instance
sudo docker start my-redis-instance
```

Project Backend:

```bash
# Navigate to the backend directory
cd /path/to/your_main_project_folder/agent

# Run the worker script
python worker.py
```
> You should see output indicating the orchestrator has started and is listening for jobs. The models will be loaded into memory by the worker processes it spawns.

### Terminal 2: Start the Django Web Server
This process runs the user-facing web application.

```bash
# Navigate to the frontend directory
cd /path/to/your_main_project_folder/web

# Run the Django development server
python manage.py runserver
```
> The Django server will start quickly as it does not load the heavy LLM models. Open your browser to `http://127.0.0.1:8000/`.

## Model Improvement: The Data Curation & Training Loop

This system is designed to improve over time using real user feedback.

### The Curation & Re-Training Workflow

1.  **Collect Feedback:** Users provide "thumbs up" or "thumbs down" feedback on agent responses in the chat UI.
2.  **Admin Curation:** An administrator logs into the web app and navigates to the **"Feedback Curation"** panel. Here, they can review all rejected messages, correct routing errors (by selecting the agent that *should* have been used), and write ideal responses.
3.  **Export Training Data:** After curating the feedback, the admin uses Django management commands to export the data into training files. **Run these commands from the `web/` directory.**

    *   **Export Router Data:** Creates `agent/data/router_sft_data_from_feedback.jsonl` to fix routing mistakes.
        ```bash
        python manage.py export_router_data
        ```
    *   **Export Agent Preference Data:** Creates `agent/data/<agent_name>_dpo_data.jsonl` for improving generation quality.
        ```bash
        python manage.py export_feedback_data programmer --format dpo
        ```

4.  **Re-train Models:** The admin uses the CLI in the `agent/` directory to fine-tune the models with the new data.

    *   **Re-train the Router (SFT):**
        ```bash
        python manage_agent.py train run router --dataset_path data/router_sft_data_from_feedback.jsonl
        ```
    *   **Refine an Agent (DPO):**
        ```bash
        python manage_agent.py train dpo programmer
        ```

5.  **Update Configuration:** After DPO training, a new model adapter is saved (e.g., `models/programmer_agent_dpo`). The admin updates `agent/configs/config.yaml` to point the agent's `model_path` to this new directory to activate the improved model.

## Backend Administration CLI (`manage_agent.py`)

All backend management tasks are handled by this tool. **Run these commands from the `agent/` directory.**

### System Configuration
```bash
# View the current config.yaml
python manage.py config show

# Set a new base model for the system (requires re-training adapters)
python manage_agent.py config set-base-model "google/gemma-3-4b-it"
```

### Agent Management
```bash
# Workflow: Create agent scaffolding first...
python manage_agent.py agents create "new_agent_name"

# ...then generate its prompt with AI assistance.
python manage_agent.py agents create-prompt "new_agent_name"

# Other commands
python manage_agent.py agents list
python manage_agent.py agents delete "agent_to_delete"
```

### Training Management
```bash
# Initial Supervised Fine-Tuning (SFT)
python manage_agent.py train run programmer

# Direct Preference Optimization (DPO) after collecting and exporting feedback
python manage_agent.py train dpo programmer
```
