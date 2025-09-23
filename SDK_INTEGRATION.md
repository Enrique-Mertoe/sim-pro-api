# SDK Integration Guide

## Overview

Your Django backend now provides **two complementary API interfaces**:

1. **Supabase-Compatible API** (for your SDK) - `/api/*`
2. **Django REST Framework API** (for admin/advanced usage) - `/api/v1/*`

## 🎯 SDK Usage (Primary Interface)

Your existing `solobase-js` SDK works seamlessly with the Django backend using the Supabase-compatible endpoints.

### Quick Start

```javascript
const { createClient } = require('./sdk/index.js');

// Point your SDK to the Django backend
const solobase = createClient('http://localhost:8000', 'your-api-key');
```

### Available SDK Operations

#### 🔐 Authentication
```javascript
// Sign up
const { data, error } = await solobase.auth.signUp({
  email: 'user@example.com',
  password: 'password123',
  options: {
    data: {
      full_name: 'John Doe',
      id_number: '123456789',
      id_front_url: 'https://example.com/front.jpg',
      id_back_url: 'https://example.com/back.jpg',
      role: 'staff'
    }
  }
});

// Sign in
const { data, error } = await solobase.auth.signInWithPassword({
  email: 'user@example.com',
  password: 'password123'
});

// Get current user
const { data, error } = await solobase.auth.getUser();

// Sign out
await solobase.auth.signOut();
```

#### 🗄️ Database Operations
```javascript
// Insert data
const { data, error } = await solobase.from('users').insert({
  full_name: 'Jane Doe',
  email: 'jane@example.com',
  role: 'staff'
});

// Select with filters
const { data, error } = await solobase.from('sim_cards').select({
  status: 'PENDING',
  team_id: 'team-uuid-here'
});

// Update records
const { data, error } = await solobase.from('teams').update(
  { territory: 'New Territory' },
  { id: 'team-uuid' }
);

// Delete records
const { data, error } = await solobase.from('sim_cards').delete({
  status: 'CANCELLED'
});
```

#### 📁 Storage Operations
```javascript
// Upload file
const { data, error } = await solobase.storage.upload(file);

// Get public URL
const { data } = solobase.storage.getPublicUrl('filename.jpg');

// Download file
const { data, error } = await solobase.storage.download('filename.jpg');
```

### SSM-Specific Tables Available

Your SDK can interact with all SSM tables:

| Table Name | Description |
|------------|-------------|
| `users` | User profiles and authentication |
| `teams` | Team management and hierarchy |
| `sim_cards` | SIM card inventory and lifecycle |
| `batch_metadata` | SIM card batch information |
| `onboarding_requests` | User onboarding workflow |
| `sim_card_transfers` | Inter-team SIM transfers |
| `activity_logs` | System activity tracking |
| `forum_topics` | Discussion forum topics |
| `forum_posts` | Forum post content |
| `notifications` | User notifications |
| `payment_requests` | Payment processing |
| `subscriptions` | User subscriptions |
| `config` | System configuration |

### Example: Complete SIM Management Workflow

```javascript
// 1. Create a team
const { data: team } = await solobase.from('teams').insert({
  name: 'Sales Team Alpha',
  region: 'North Region',
  territory: 'Downtown',
  is_active: true
});

// 2. Create batch metadata
const { data: batch } = await solobase.from('batch_metadata').insert({
  batch_id: 'BATCH-2024-001',
  order_number: 'ORD-001',
  company_name: 'SIM Corp',
  quantity: 1000,
  item_description: 'Standard SIM Cards'
});

// 3. Add SIM cards to batch
const simCards = [];
for (let i = 1; i <= 10; i++) {
  simCards.push({
    serial_number: `SIM${String(i).padStart(6, '0')}`,
    batch_id: 'BATCH-2024-001',
    team_id: team[0].id,
    status: 'PENDING',
    quality: 'QUALITY',
    match: 'Y'
  });
}

const { data: sims } = await solobase.from('sim_cards').insert(simCards);

// 4. Query team performance
const { data: teamSims } = await solobase.from('sim_cards').select({
  team_id: team[0].id,
  status: 'REGISTERED'
});

// 5. Create activity log
await solobase.from('activity_logs').insert({
  user_id: currentUser.id,
  action_type: 'BATCH_CREATED',
  details: {
    batch_id: 'BATCH-2024-001',
    sim_count: 10
  }
});
```

## 🔧 API Endpoint Mapping

### Your SDK calls these endpoints automatically:

| SDK Method | HTTP Endpoint | Description |
|------------|---------------|-------------|
| `auth.signUp()` | `POST /api/auth/signup` | User registration |
| `auth.signInWithPassword()` | `POST /api/auth/login` | User login |
| `auth.getUser()` | `GET /api/auth/me` | Get current user |
| `auth.signOut()` | `POST /api/auth/logout` | User logout |
| `from(table).select()` | `POST /api/db/select` | Query records |
| `from(table).insert()` | `POST /api/db/insert` | Create records |
| `from(table).update()` | `POST /api/db/update` | Update records |
| `from(table).delete()` | `POST /api/db/delete` | Delete records |
| `storage.upload()` | `POST /api/storage/upload` | Upload files |
| `storage.download()` | `GET /api/storage/{filename}` | Download files |

## 🎛️ Advanced API (Django REST Framework)

For advanced operations, admin interfaces, or custom integrations, use the REST endpoints:

```
GET /api/v1/users/                    # List users with pagination
POST /api/v1/users/{id}/toggle_active/ # Custom user actions
GET /api/v1/teams/{id}/performance/   # Team performance metrics
POST /api/v1/sim-cards/bulk_update_status/ # Bulk operations
POST /api/v1/onboarding-requests/{id}/approve/ # Workflow actions
```

## 🚀 Getting Started

1. **Start the Django server**:
   ```bash
   python manage.py runserver
   ```

2. **Initialize your SDK**:
   ```javascript
   const solobase = createClient('http://localhost:8000', 'your-api-key');
   ```

3. **Use it exactly like Supabase**:
   ```javascript
   // Your existing Supabase code works unchanged!
   const { data, error } = await solobase.from('users').select();
   ```

## 🔒 Authentication

The SDK handles authentication automatically:
- Signup/login returns access tokens
- Tokens are automatically included in subsequent requests
- Django validates tokens and provides user context
- All database operations respect user permissions

## 📝 Error Handling

The API returns Supabase-compatible error responses:

```javascript
const { data, error } = await solobase.from('users').select();

if (error) {
  console.error('Error:', error.message);
} else {
  console.log('Data:', data);
}
```

## 🔄 Migration from Direct Database Access

If you were previously connecting directly to the database, simply:

1. Replace database connection with SDK initialization
2. Replace SQL queries with SDK methods
3. Keep your existing business logic unchanged

**Before:**
```javascript
// Direct database query
const result = await db.query('SELECT * FROM sim_cards WHERE status = ?', ['PENDING']);
```

**After:**
```javascript
// SDK query
const { data } = await solobase.from('sim_cards').select({ status: 'PENDING' });
```

## 🎉 Benefits

✅ **Drop-in Replacement**: Works exactly like Supabase  
✅ **Type Safety**: Your existing TypeScript types work  
✅ **Error Handling**: Consistent error responses  
✅ **Authentication**: Built-in user management  
✅ **Real-time Ready**: WebSocket support for live updates  
✅ **File Storage**: Complete file upload/download system  
✅ **Admin Interface**: Django admin for data management  
✅ **Scalability**: Django's robust backend architecture  

Your SDK integration is now complete and ready for production use!