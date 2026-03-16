# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Skyght Enterprise is a full-stack OCR SaaS application built with Express.js backend and vanilla JavaScript frontend.

## Commands

```bash
# Start the server
npm start

# Run with environment variables
PORT=3000 node src/server.js
```

Note: No test, lint, or build commands are currently configured.

## Architecture

### Backend (src/)
- **server.js** - Express entry point with middleware stack (Helmet, CORS, rate limiting, JSON parsing)
- **routes/** - API route handlers (auth.js, teams.js, admin.js)
- **middleware/auth.js** - JWT authentication and role-based access control

### Frontend (public/)
- Vanilla HTML/CSS/JavaScript served as static files
- Uses Fetch API for HTTP calls to backend

### Database
PostgreSQL with two tables:
- `users` - UUID primary key, email, password (bcrypt), role (user/admin)
- `teams` - UUID primary key, name, owner_id (FK to users)

Schema located in `migrations/schema.sql`.

## API Routes

- `POST /api/auth/register` - User registration (public)
- `POST /api/auth/login` - User login, returns JWT (public)
- `GET /api/teams` - List user's teams (authenticated)
- `POST /api/teams` - Create team (authenticated)
- `GET /api/admin/users` - List all users (admin only)
- `GET /api/health` - Health check (public)

## Environment Variables

Copy `.env.example` to `.env` and configure:
- `PORT` - Server port (default: 3000)
- `DATABASE_URL` - PostgreSQL connection string
- `JWT_SECRET` - Secret for signing JWT tokens

## Authentication

JWT-based with 1-hour expiration. Protected routes require `Authorization: Bearer <token>` header. The auth middleware in `src/middleware/auth.js` validates tokens and attaches user info to `req.user`.
