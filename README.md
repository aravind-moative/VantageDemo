# Vantage Demo

A FastAPI application that provides an interactive interface for exploring clinical trial data using Neo4j and Gemini AI.

## Features

- Interactive visualization of clinical trial data
- Dynamic AE selection and plotting
- AI-powered insights using Gemini
- Real-time data exploration
- Responsive design

## Prerequisites

- Docker and Docker Compose
- Python 3.8+
- Neo4j 3.5.0
- Google Cloud account with Gemini API access

## Environment Variables

Create a `.env` file in the root directory with the following variables:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password
GEMINI_API_KEY=your_gemini_api_key
```

## Local Development

1. Clone the repository:
```bash
git clone <repository-url>
cd vantage-demo
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Start Neo4j:
```bash
docker-compose up neo4j -d
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

The application will be available at `http://localhost:8000`

## Deployment

### Using Docker Compose

1. Build and start the containers:
```bash
docker-compose up --build
```

The application will be available at `http://localhost:8000`

### Using Docker

1. Build the Docker image:
```bash
docker build -t vantage-demo .
```

2. Run the container:
```bash
docker run -p 8000:8000 \
  -e NEO4J_URI=bolt://host.docker.internal:7687 \
  -e NEO4J_USER=neo4j \
  -e NEO4J_PASSWORD=your_password \
  -e GEMINI_API_KEY=your_gemini_api_key \
  vantage-demo
```

### Cloud Deployment

#### AWS Elastic Beanstalk

1. Install the EB CLI:
```bash
pip install awsebcli
```

2. Initialize EB application:
```bash
eb init
```

3. Create environment:
```bash
eb create
```

4. Deploy:
```bash
eb deploy
```

#### Google Cloud Run

1. Install Google Cloud SDK
2. Build and push the container:
```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/vantage-demo
```

3. Deploy to Cloud Run:
```bash
gcloud run deploy vantage-demo \
  --image gcr.io/PROJECT_ID/vantage-demo \
  --platform managed \
  --allow-unauthenticated
```

## Project Structure

```
vantage-demo/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── data.py
│   │   └── insights.py
│   └── static/
│       ├── css/
│       │   └── styles.css
│       └── js/
│           └── main.js
├── templates/
│   └── index.html
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── .env
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.
