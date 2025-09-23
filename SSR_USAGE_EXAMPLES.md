# SSR Usage Examples for Enhanced SDK

Your SDK now supports **Server-Side Rendering (SSR)** like Supabase, allowing seamless authentication between client and server contexts using cookie-based session management.

## Installation

Your SDK is already set up. No additional packages needed.

## Basic Usage

### Client-Side (Browser)

```javascript
const { createClient } = require('./sdk');

// Create client for browser usage
const supabase = createClient(
    'http://localhost:8000',
    'your-api-key' // optional
);

// Standard authentication
const { data, error } = await supabase.auth.signInWithPassword({
    email: 'user@example.com',
    password: 'password'
});

// Session is automatically stored in cookies
console.log(data.user, data.session);
```

### Server-Side (Node.js/SSR)

```javascript
const { createServerClient } = require('./sdk');

// Create server client for SSR usage (similar to Supabase pattern)
const supabase = createServerClient(
    'http://localhost:8000',
    'your-api-key', // optional
    {
        cookies: {
            getAll() {
                // Get cookies from your request context
                return request.cookies.getAll(); // Next.js example
            },
            setAll(cookiesToSet) {
                // Set cookies in your response
                cookiesToSet.forEach(({ name, value, options }) => {
                    response.cookies.set(name, value, options);
                });
            }
        }
    }
);

// Authentication works the same way
const { data, error } = await supabase.auth.getUser();
```

## Next.js Examples

### 1. Middleware (Server-Side)

```javascript
// middleware.js
import { createServerClient } from './sdk';
import { NextResponse } from 'next/server';

export async function middleware(request) {
    let response = NextResponse.next({
        request,
    });

    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_BACKEND_URL,
        process.env.NEXT_PUBLIC_API_KEY,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll();
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        request.cookies.set(name, value);
                    });
                    response = NextResponse.next({
                        request,
                    });
                    cookiesToSet.forEach(({ name, value, options }) =>
                        response.cookies.set(name, value, options)
                    );
                },
            },
        }
    );

    // Check authentication
    const { data: { user } } = await supabase.auth.getUser();

    if (!user && request.nextUrl.pathname.startsWith('/dashboard')) {
        return NextResponse.redirect(new URL('/login', request.url));
    }

    return response;
}

export const config = {
    matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

### 2. Server Component

```javascript
// app/dashboard/page.js
import { createServerClient } from '@/lib/supabase/server';
import { cookies } from 'next/headers';

export default async function DashboardPage() {
    const cookieStore = cookies();
    
    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_BACKEND_URL,
        process.env.NEXT_PUBLIC_API_KEY,
        {
            cookies: {
                getAll() {
                    return cookieStore.getAll();
                },
                setAll(cookiesToSet) {
                    // In server components, cookies are read-only
                    // Use server actions or route handlers for mutations
                },
            },
        }
    );

    // Get user data server-side
    const { data: { user } } = await supabase.auth.getUser();
    
    // Fetch user-specific data
    const { data: users } = await supabase.from('users').select('*');

    return (
        <div>
            <h1>Welcome, {user?.user_metadata?.full_name || user?.email}</h1>
            <UsersList users={users} />
        </div>
    );
}
```

### 3. Client Component

```javascript
// components/LoginForm.js
'use client';
import { createClient } from '@/lib/supabase/client';
import { useState } from 'react';

const supabase = createClient(
    process.env.NEXT_PUBLIC_BACKEND_URL,
    process.env.NEXT_PUBLIC_API_KEY
);

export default function LoginForm() {
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    
    const handleLogin = async (e) => {
        e.preventDefault();
        
        const { data, error } = await supabase.auth.signInWithPassword({
            email,
            password
        });
        
        if (!error) {
            // Cookies are automatically set
            window.location.href = '/dashboard';
        }
    };

    return (
        <form onSubmit={handleLogin}>
            <input 
                type="email" 
                value={email} 
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email"
            />
            <input 
                type="password" 
                value={password} 
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password"
            />
            <button type="submit">Login</button>
        </form>
    );
}
```

### 4. Server Action

```javascript
// app/auth/actions.js
'use server';
import { createServerClient } from '@/lib/supabase/server';
import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';

export async function signOut() {
    const cookieStore = cookies();
    
    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_BACKEND_URL,
        process.env.NEXT_PUBLIC_API_KEY,
        {
            cookies: {
                getAll() {
                    return cookieStore.getAll();
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        cookieStore.set(name, value, options);
                    });
                },
            },
        }
    );

    await supabase.auth.signOut();
    redirect('/login');
}
```

### 5. Route Handler

```javascript
// app/api/auth/callback/route.js
import { createServerClient } from '@/lib/supabase/server';
import { NextRequest, NextResponse } from 'next/server';

export async function POST(request) {
    const requestUrl = new URL(request.url);
    const formData = await request.formData();
    const email = String(formData.get('email'));
    const password = String(formData.get('password'));

    const supabase = createServerClient(
        process.env.NEXT_PUBLIC_BACKEND_URL,
        process.env.NEXT_PUBLIC_API_KEY,
        {
            cookies: {
                getAll() {
                    return request.cookies.getAll();
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        request.cookies.set(name, value);
                    });
                },
            },
        }
    );

    const { data, error } = await supabase.auth.signInWithPassword({
        email,
        password
    });

    if (error) {
        return NextResponse.redirect(
            `${requestUrl.origin}/login?error=${error.message}`,
            { status: 301 }
        );
    }

    return NextResponse.redirect(`${requestUrl.origin}/dashboard`, {
        status: 301,
    });
}
```

## Express.js Example

```javascript
// server.js
const express = require('express');
const cookieParser = require('cookie-parser');
const { createServerClient } = require('./sdk');

const app = express();
app.use(cookieParser());

// Authentication middleware
const authenticateUser = async (req, res, next) => {
    const supabase = createServerClient(
        process.env.BACKEND_URL,
        process.env.API_KEY,
        {
            cookies: {
                getAll() {
                    return Object.entries(req.cookies).map(([name, value]) => ({ name, value }));
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        res.cookie(name, value, options);
                    });
                },
            },
        }
    );

    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
        return res.status(401).json({ error: 'Unauthorized' });
    }
    
    req.user = user;
    req.supabase = supabase;
    next();
};

// Protected route
app.get('/api/profile', authenticateUser, async (req, res) => {
    const { data: userProfile } = await req.supabase
        .from('users')
        .select('*')
        .eq('id', req.user.id)
        .single();
    
    res.json({ user: req.user, profile: userProfile });
});

app.listen(3000);
```

## Authentication Flow Examples

### Complete Login Flow

```javascript
// Client-side login
const handleLogin = async () => {
    const { data, error } = await supabase.auth.signInWithPassword({
        email: 'user@example.com',
        password: 'password123'
    });
    
    if (!error) {
        // Session automatically stored in cookies
        // User can now navigate to protected pages
        router.push('/dashboard');
    }
};

// Server-side session check
const getServerSideProps = async (context) => {
    const supabase = createServerClient(
        process.env.BACKEND_URL,
        process.env.API_KEY,
        {
            cookies: {
                getAll() {
                    return context.req.cookies;
                },
                setAll(cookiesToSet) {
                    cookiesToSet.forEach(({ name, value, options }) => {
                        context.res.setHeader('Set-Cookie', 
                            `${name}=${value}; Path=/; ${options.secure ? 'Secure;' : ''}`
                        );
                    });
                },
            },
        }
    );

    const { data: { user } } = await supabase.auth.getUser();
    
    if (!user) {
        return {
            redirect: {
                destination: '/login',
                permanent: false,
            },
        };
    }

    return {
        props: {
            user,
        },
    };
};
```

## Key Features

1. **Automatic Cookie Management**: Sessions are automatically stored in secure HTTP-only cookies
2. **SSR Compatible**: Works seamlessly in server-side rendering environments
3. **Hybrid Authentication**: Supports both header-based and cookie-based authentication
4. **Supabase-like API**: Familiar API patterns for easy migration from Supabase
5. **Framework Agnostic**: Works with Next.js, Express.js, or any Node.js environment

## Security Features

- **HTTP-only cookies** for server-side usage (prevents XSS)
- **Secure flag** when using HTTPS
- **SameSite=lax** for CSRF protection
- **7-day cookie expiration** by default
- **Automatic token cleanup** on logout

## Migration from Standard SDK

If you were using the old SDK, migration is simple:

```javascript
// Old way (client-only)
const supabase = createClient('http://localhost:8000', 'api-key');

// New way (client-side - same API)
const supabase = createClient('http://localhost:8000', 'api-key');

// New way (server-side)
const supabase = createServerClient('http://localhost:8000', 'api-key', {
    cookies: {
        getAll() { return request.cookies.getAll(); },
        setAll(cookies) { /* set cookies in response */ }
    }
});
```

Your enhanced SDK now provides the same SSR capabilities as Supabase's latest version!