# 🚀 Google Conversational Agent Deployment Automation
**Standardize and accelerate your Dialogflow CX release cycle.**

This repository contains a Python script to automate:
- Flow versioning
- Playbook versioning
- Custom tool versioning
- Environment creation / updates

for a Dialogflow CX/Conversational agent.

---

## Prerequisites

- Python 3.10+
- Google Cloud SDK
- Access to the target GCP project
- Dialogflow CX permissions

---

## Authentication (Required)

This script uses **Application Default Credentials (ADC)**.

Run once per machine:


gcloud auth application-default login

## If you encounter quota or permission issues, set the quota project:
gcloud auth application-default set-quota-project <PROJECT_ID>


## Setup

Clone the repo

Create a virtual environment (recommended)

Install dependencies:

pip install -r requirements.txt


Copy environment variables:

cp .env.example .env


Edit .env with your values

Run Deployment
python deploy_agent.py


You will be prompted to confirm before deployment.