# Related News Injection

This project implements a man-in-the-middle HTTPS proxy that injects independent related news coverage directly into news website using LLM-based retrieval and synthesis.
The goal is to expose users to more diverse perspectives on major, controversial news stories.


## Running with Docker

A [Gemini API key](https://ai.google.dev/gemini-api/docs/rate-limits#free-tier) is required to run this project. It should be possible to use the free tier.
Certificates for TLS interception are read from the `proxy/proxy_ca.{crt,key}` files by default.
This CA should be trusted by any proxy consumers.

```sh
GOOGLE_API_KEY=... docker compose up
```

The proxy should then be available at `localhost:8000`.

## System Components

1. Proxy (`/proxy`): Uses [Goproxy](https://github.com/goproxy/goproxy) to perform TLS interception and inject JavaScript for frontend.
2. Frontend (`/frontend`): Uses [React](https://github.com/facebook/react) to extract page sources, calls backend via HTTP, and displays data to user.
3. Backend (`/backend`): Uses [FastAPI](https://github.com/fastapi/fastapi) to implement LLM calls (retrieval, synthesis) and feedback.

## Features

- HTTPS interception with TLS bumping
- LLM-powered article retrieval, summaries, and comparison.
- User feedback (like/dislike sources) to refine future results.
- Asynchronous retrieval to minimize user waiting time.

## Local Development

---

### 📦 Requirements

#### Go

**macOS**

```sh
brew install go
```

#### **Pipenv (Python dependency manager)**

**macOS**

```sh
brew install pipenv
```


---

### 🚀 Installation

#### 2. Backend

```sh
cd backend
pipenv install
```

#### 3. Frontend

```sh
cd frontend
npm install
```


---

### ▶️ Running the Project

#### **Run Proxy**

```sh
cd proxy
go build -o injector-proxy .
./injector-proxy -addr :8000 -cert proxy_ca.crt -key proxy_ca.key
```

#### **Run Backend**

```sh
cd backend
pipenv shell
# Return to project root so module paths work correctly:
cd ..
# Gemini API key must be set to use LLMs
GOOGLE_API_KEY=... python -m backend.main
```

#### **Run Frontend**

```sh
cd frontend
npm run build
npm run serve
```
