# Admin User Credentials

**Created**: 2026-01-22
**Environment**: Development (localhost)

## 🔑 Your Admin Account

```
Email:    admin@example.com
Password: Admin123!
```

**User ID**: `4378d4a1-8883-496b-9a30-2d01619147ba`
**Privileges**: ✅ Admin
**Status**: ✅ Active

## 🌐 Login URLs

- **Web App**: http://localhost:8080
- **API Docs**: http://localhost:8000/docs (use "Authorize" button)

## 🔐 Using Admin Credentials

### Web App Login

1. Open http://localhost:8080
2. Click "Login" or "Sign In"
3. Enter:
   - Email: `admin@example.com`
   - Password: `Admin123!`
4. Click "Login"

### API Login (via cURL)

```bash
# Get access token
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "Admin123!"
  }'

# Response includes:
# - access_token (JWT)
# - token_type (bearer)
# - expires_in (minutes)
```

### Using the Access Token

```bash
# Save token to variable
TOKEN=$(curl -s -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"Admin123!"}' \
  | jq -r '.access_token')

# Get current user info
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer $TOKEN"

# Access admin endpoints
curl http://localhost:8000/auth/admin/codes \
  -H "Authorization: Bearer $TOKEN"

curl http://localhost:8000/auth/admin/waitlist \
  -H "Authorization: Bearer $TOKEN"
```

## 🛡️ Admin Features

As an admin user, you have access to:

### 1. **Registration Code Management**

Generate and manage invitation codes:

```bash
# View all codes
GET /auth/admin/codes

# Generate new codes
POST /auth/admin/codes/generate
{
  "count": 10,
  "expires_days": 30
}

# Distribute code to user
POST /auth/admin/codes/distribute
{
  "code": "CODE123",
  "email": "user@example.com"
}
```

### 2. **Waitlist Management**

Manage users waiting for access:

```bash
# View waitlist
GET /auth/admin/waitlist

# Invite from waitlist (generates code + sends email)
POST /auth/admin/waitlist/invite
{
  "email": "waitlist-user@example.com"
}
```

### 3. **User Management**

Access all user data and management features:

- View all users in the system
- Modify user permissions
- Deactivate/activate accounts
- View user activity and health data

### 4. **System Monitoring**

Access to monitoring and analytics:

- View system metrics at `/metrics`
- Access detailed health checks
- Monitor database performance
- View API usage statistics

## 📝 API Documentation

Interactive API documentation with admin endpoints:

1. Open http://localhost:8000/docs
2. Click "Authorize" button (top right)
3. Enter your token (get from login)
4. Click "Authorize"
5. Now you can test all admin endpoints directly

## 🔒 Security Notes

### Development Environment

- This is a **development** account
- Password is simple for testing
- SSL/TLS not enabled (http://)
- Database is local SQLite

### Production Environment

For production deployment:

1. **Change the password** to a strong, unique password
2. **Enable HTTPS** (SSL/TLS)
3. **Use PostgreSQL** instead of SQLite
4. **Enable rate limiting** on auth endpoints
5. **Rotate secrets** regularly (JWT secret, database password)
6. **Enable 2FA** if available
7. **Monitor admin actions** with audit logging

### Password Change

To change your password:

```bash
# Via API (requires current token)
curl -X PUT http://localhost:8000/auth/change-password \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "current_password": "Admin123!",
    "new_password": "NewSecurePassword123!"
  }'
```

Or update directly in database:

```python
from core.auth_service import get_password_hash

new_password = "YourNewPassword"
hashed = get_password_hash(new_password)

# Update in database
UPDATE users
SET hashed_password = 'hashed_value_here'
WHERE email = 'admin@example.com'
```

## 🧪 Testing Admin Features

### 1. Generate Registration Codes

```bash
TOKEN="your_token_here"

curl -X POST http://localhost:8000/auth/admin/codes/generate \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "count": 5,
    "expires_days": 30,
    "distributed_by_user_id": "4378d4a1-8883-496b-9a30-2d01619147ba"
  }'
```

### 2. View All Codes

```bash
curl http://localhost:8000/auth/admin/codes \
  -H "Authorization: Bearer $TOKEN"
```

### 3. Invite from Waitlist

```bash
# First, add someone to waitlist
curl -X POST http://localhost:8000/waitlist \
  -H "Content-Type: application/json" \
  -d '{"email": "newuser@example.com"}'

# Then invite them as admin
curl -X POST http://localhost:8000/auth/admin/waitlist/invite \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email": "newuser@example.com"}'
```

## 📊 Database Access

You can also query the database directly:

```bash
# View your user record
sqlite3 fitness_dev.db "SELECT * FROM users WHERE email='admin@example.com'"

# Check admin status
sqlite3 fitness_dev.db "SELECT email, is_admin, is_active FROM users"

# View all registration codes
sqlite3 fitness_dev.db "SELECT * FROM registration_codes"

# View waitlist
sqlite3 fitness_dev.db "SELECT * FROM waitlist"
```

## 🔄 Create Additional Admin Users

```python
from core.database import get_db, get_cursor
from core.auth_service import get_password_hash
import uuid

user_id = str(uuid.uuid4())
email = "another-admin@example.com"
password = "SecurePass123!"
hashed_password = get_password_hash(password)

with get_db() as conn:
    cur = get_cursor(conn)
    cur.execute("""
        INSERT INTO users (id, email, hashed_password, full_name, is_active, is_admin)
        VALUES (?, ?, ?, ?, 1, 1)
    """, (user_id, email, hashed_password, "Another Admin"))
    conn.commit()
```

## 💡 Tips

1. **Save your token**: Store the access token in a variable when testing
2. **Use the API docs**: The Swagger UI at `/docs` is the easiest way to test
3. **Check logs**: Watch `/tmp/workout-planner.log` for authentication events
4. **Refresh tokens**: Tokens expire - use the refresh endpoint when needed

## 📚 Related Documentation

- **Backend API**: http://localhost:8000/docs
- **Production Readiness**: `PRODUCTION_READINESS_REPORT.md`
- **Security Report**: `docs/SECURITY_REPORT.md`
- **Running Locally**: `QUICK_START.md`

---

**Remember**: Keep these credentials secure and change them before any production deployment!
