# Installation Guide

This guide will walk you through the process of setting up the API Monetization Platform for local development.

## Prerequisites

Before you begin, make sure you have the following installed on your local machine:

*   **Docker:** [https://www.docker.com/get-started](https://www.docker.com/get-started)
*   **Docker Compose:** [https://docs.docker.com/compose/install/](https://docs.docker.com/compose/install/)
*   **Python 3.11+:** [https://www.python.org/downloads/](https://www.python.org/downloads/)
*   **pip:** [https://pip.pypa.io/en/stable/installation/](https://pip.pypa.io/en/stable/installation/)

## 1. Clone the Repository

```bash
git clone https://github.com/your-username/monetizeit.git
cd monetizeit/backend
```

## 2. Set Up the Environment

### Virtual Environment

It is highly recommended to use a virtual environment to manage the project's dependencies. To create and activate a virtual environment, run the following commands:

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Dependencies

Each service has its own `requirements.txt` file. You will need to install the dependencies for each service.

**Root Dependencies:**

```bash
pip install -r requirements.txt
```

**Management API Dependencies:**

```bash
pip install -r management-api/requirements.txt
```

**Billing Worker Dependencies:**

```bash
pip install -r billing-worker/requirements.txt
```

**Gateway Dependencies:**

```bash
pip install -r gateway/requirements.txt
```

### Environment Variables

Create a `.env` file in the `management-api` directory and add the following environment variable:

```
DATABASE_URL=postgresql://postgres:example@postgres:5432/postgres
```

## 3. Run the Application

Once you have set up the environment, you can run the application using Docker Compose:

```bash
docker-compose up -d
```

This command will start all the services in the background. To view the logs for a specific service, you can use the following command:

```bash
docker-compose logs -f <service-name>
```

For example, to view the logs for the `management-api` service, you would run:

```bash
docker-compose logs -f management-api
```

## 4. Accessing the Services

Once the application is running, you can access the services at the following URLs:

*   **Management API:** [http://localhost:8000](http://localhost:8000)
*   **API Gateway:** [http://localhost:8080](http://localhost:8080)

## 5. Running Tests

To run the tests for each service, navigate to the service's directory and run `pytest`:

```bash
cd management-api
pytest
```

Repeat this process for the other services.
