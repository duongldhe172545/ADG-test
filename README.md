# ADG Knowledge Management System

Enterprise Knowledge Management System powered by NotebookLM.

## Features

- 🤖 **AI-Powered Chat** - Query documents using NotebookLM
- 📤 **Document Upload** - Upload files to Google Drive with OAuth
- 📁 **Folder Management** - Organize documents in structured folders
- 🔐 **Secure Authentication** - Google OAuth2 for user access
- ⏰ **Auto Session Refresh** - Background scheduler keeps sessions alive

## Project Structure

```
adg-knowledge-management/
├── backend/                    # Python backend
│   ├── api/                    # API routes
│   │   ├── v1/                 # Versioned API endpoints
│   │   │   ├── auth.py         # OAuth authentication
│   │   │   ├── chat.py         # NotebookLM chat
│   │   │   ├── documents.py    # File upload/management
│   │   │   └── health.py       # Health checks
│   │   └── router.py           # Main API router
│   ├── core/                   # Core modules
│   │   └── auth/               # Authentication
│   │       └── oauth.py        # OAuth2 service
│   ├── services/               # Business logic
│   │   ├── gdrive_service.py   # Google Drive operations
│   │   ├── notebooklm_service.py  # NotebookLM integration
│   │   └── scheduler_service.py   # Background jobs
│   ├── models/                 # Pydantic models
│   │   ├── requests.py         # Request schemas
│   │   └── responses.py        # Response schemas
│   ├── config.py               # Centralized configuration
│   └── main.py                 # Application entry point
├── frontend/                   # Frontend assets
│   ├── static/                 # CSS, JS, images
│   └── templates/              # HTML templates
├── tests/                      # Test suite
├── docs/                       # Documentation
└── scripts/                    # Utility scripts
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your credentials
```

### 3. Authenticate NotebookLM

```bash
notebooklm-mcp-auth
```

### 4. Run the Server

```bash
# Development
python -m backend.main

# Or with uvicorn directly
uvicorn backend.main:app --reload --port 8080
```

### 5. Access the Application

- Chat UI: http://localhost:8080/
- Upload UI: http://localhost:8080/upload
- API Docs: http://localhost:8080/docs (debug mode only)

## API Endpoints

### Authentication
- `GET /api/v1/auth/login` - Start OAuth login
- `GET /api/v1/auth/callback` - OAuth callback
- `GET /api/v1/auth/status` - Check auth status
- `POST /api/v1/auth/logout` - Logout

### Chat
- `POST /api/v1/chat` - Sync chat
- `POST /api/v1/chat/stream` - SSE streaming chat
- `GET /api/v1/chat/notebooks` - List notebooks
- `GET /api/v1/chat/sources/{notebook_id}` - Get sources

### Documents
- `GET /api/v1/documents/folders` - List folder tree
- `POST /api/v1/documents/upload` - Upload file
- `GET /api/v1/documents/files/{folder_id}` - List files

### Health
- `GET /api/v1/health` - System health check
- `GET /api/v1/health/ping` - Simple ping

## Configuration

All configuration is done via environment variables. See `.env.example` for all options.

### Required Variables

| Variable | Description |
|----------|-------------|
| `OAUTH_CLIENT_ID` | Google OAuth Client ID |
| `OAUTH_CLIENT_SECRET` | Google OAuth Client Secret |
| `GDRIVE_ROOT_FOLDER_ID` | Root folder for document storage |
| `NOTEBOOK_ID` | Default NotebookLM notebook ID |

## Development

### Running Tests

```bash
pytest
```

### Code Structure

- **config.py** - Centralized Pydantic settings
- **services/** - Business logic (testable, reusable)
- **api/** - HTTP routes only (thin layer)
- **models/** - Request/response schemas

## License

Proprietary - ADG Internal Use Only
