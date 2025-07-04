# Compiler Explorer Authentication Design

Compiler Explorer has been happily anonymous for years. Some users have been asking for features that would be much easier to build if we knew who they were, like the ability to see and administrate their own short links. Additionally we can consider reducing our default WAF per-ip limits for anonymous users, and then allow the higher limit for our authenticated users, on the basis that we could at least contact serial abusers rather than tar everyone with the same brush.

This would all be optional: If people want to keep using CE exactly as they do today, nothing changes (unless they were relying on our super high rate limits). But if you want to sign in (likely with their GitHub account), they'll get some nice perks like higher rate limits and eventually things like saved preferences.

Here's what I'm aiming for, to start with at least:

- Anonymous users see zero change in behavior
- Simple design: I don't want to build an identity provider from scratch (so: AWS Cognito)
- No auth secrets in the web server, proper token validation, but let's not go overboard
- GitHub, Google and Apple logins as well as Cognito-stored username/password
- Higher rate limits for authenticated users via WAF rules
- Opening the door for more things down the road; probably short link attribution to start with.

## How it all fits together

The architecture is pretty straightforward - I've tried to keep it as simple as possible while still being secure. Here's the basic flow:

```mermaid
graph TB
    subgraph "User Experience"
        Browser[User Browser<br/>Frontend with Optional Auth Token]
    end

    subgraph "Authentication Layer"
        AuthLambda[Auth Lambda Service<br/>/auth/login<br/>/auth/callback<br/>Token Exchange]
        Cognito[AWS Cognito<br/>User Pool<br/>GitHub OIDC<br/>Google OAuth<br/>Apple OAuth]
    end

    subgraph "Application Layer"
        WebServer[Compiler Web Server<br/>Token Validation<br/>No Secrets]
        CloudFront[CloudFront<br/>Rate Limiting<br/>Based on Auth Status]
        WAF[WAF Rules<br/>Authenticated: 1000/5min<br/>Anonymous: 100/5min]
    end

    %% Authentication Flow
    Browser -->|1. Sign In Request| AuthLambda
    AuthLambda -->|2. OAuth Redirect| Cognito
    Cognito -->|3. Auth Callback| AuthLambda
    AuthLambda -->|4. Return Tokens| Browser

    %% API Request Flow
    Browser -->|5. API Requests<br/>Bearer Token (optional)| CloudFront
    CloudFront -->|6. Rate Limit Check| WAF
    WAF -->|7. Allowed Request| WebServer
    WebServer -->|8. Token Validation<br/>(if present)| WebServer

    %% Styling
    classDef authService fill:#e1f5fe
    classDef appService fill:#f3e5f5
    classDef userService fill:#e8f5e8

    class AuthLambda,Cognito authService
    class WebServer,CloudFront,WAF appService
    class Browser userService
```

When someone wants to sign in, they click a button and get redirected to GitHub (or Google/Apple). The OAuth dance happens with AWS Cognito handling the heavy lifting, and we get back some JWT tokens. The important bit is that all the OAuth secrets live in a separate Lambda function - the main CE web server never sees them.

For API requests, if you're authenticated, you send a Bearer token. The WAF looks at whether you have a token and applies different rate limits accordingly (NB it does not and cannot validate it). The web server validates the token (using public keys, no secrets needed) and either processes your request as an authenticated user (erroring if the token is invalid), or treats it normally if unauthenticated. There isn't currently any need to treat the request differently in the main code: other than checking the validity.

The beauty of this setup is that it's additive - anonymous users keep working exactly as before.

## Security considerations

If someone compromises the main CE web server, I don't want them getting access to OAuth secrets. That's why all the secrets live in a separate Lambda function that the web server never talks to directly.

XSS attacks are always a concern when storing access tokens in localStorage. We mitigate this by:

- Using httpOnly cookies for refresh tokens (XSS can't steal these)
- Short 30-minute access token lifetime (limits damage from localStorage theft)
- Strong CSP headers and input sanitization
- Refresh tokens can only be used by server-side code, not JavaScript

This hybrid approach gives us the security benefits of httpOnly cookies while still allowing JavaScript access to short-lived access tokens for Bearer headers.

Rate limit bypass is probably the most likely attack vector - someone trying to use fake or stolen tokens to get higher limits. The WAF checks for the presence of a Bearer token first, then the web server validates it properly. If validation fails, it will pass the WAF filter, but the server will send back an error.

Account takeover via OAuth provider compromise is mostly out of our hands, but we can limit the damage by not storing sensitive data and making it easy for users to sign out everywhere.

OAuth secrets never leave the Lambda auth service. The main web server only knows how to validate JWTs using public keys. WAF rules handle rate limiting at the CloudFront level. We'll be strict about CORS and input validation.

## Token handling

JWT tokens are pretty straightforward - they're just signed JSON that tells us who you are. We use a two-token approach for better security:

**Access tokens** (30 minutes): Stored in localStorage so JavaScript can include them in Bearer headers for API calls. Short lifetime limits damage if stolen.

**Refresh tokens** (30 days): Stored in httpOnly cookies that JavaScript can't access. This protects against XSS attacks stealing long-lived tokens. The browser automatically sends these cookies to our refresh endpoint.

We track access token expiry client-side to avoid unnecessary server round-trips, but the server is authoritative on token validity.

Here's the token storage approach:

```typescript
// Access token storage in localStorage (needed for Bearer headers)
localStorage.setItem('ce_access_token', accessToken);
localStorage.setItem('ce_token_expiry', (Date.now() + expiresIn * 1000).toString());

// Refresh tokens are set as httpOnly cookies by the server
// No client-side storage or management needed

// Automatic cleanup on page load
const tokenExpiry = localStorage.getItem('ce_token_expiry');
if (tokenExpiry && Date.now() > parseInt(tokenExpiry)) {
    localStorage.removeItem('ce_access_token');
    localStorage.removeItem('ce_token_expiry');
    // Refresh token cleanup handled by server cookie expiry
}
```

For XSS protection, we need to be more specific than "just good hygiene". Here's what we're actually doing:

- **Content Security Policy (CSP) headers**: These tell the browser exactly which scripts can run and where they can come from. We'll be strict about this.
- **Input sanitization and output encoding**: Every piece of user input gets cleaned before we display it anywhere.
- **X-XSS-Protection and X-Content-Type-Options headers**: These are the standard browser security headers that help prevent common XSS vectors.
- **Regular security audits and dependency updates**: We'll keep our JavaScript dependencies current and run security scans.

The localStorage approach still makes some security folks nervous, but the alternatives (httpOnly cookies, server-side sessions) would complicate the stateless nature of CE significantly. The short token lifetime and automatic cleanup help mitigate the risk.

## Implementation details

### Backend integration

The backend changes are pretty minimal, which is exactly what I wanted. We're adding a single middleware function that checks for auth tokens and validates them if present. No tokens? You're anonymous and everything works exactly like before.

#### Express.js middleware for the CE server

Here's the core middleware code. The nice thing about this approach is that it's completely opt-in - if auth isn't configured, it just marks everyone as anonymous:

```typescript
import { CognitoJwtVerifier } from 'aws-jwt-verify';
import { PropertyGetter } from '../properties.interfaces.js';

// Create auth middleware factory function
export function createAuthMiddleware(awsProps: PropertyGetter) {
    // Config from CE properties system (no secrets in code)
    const cognitoUserPoolId = awsProps('cognitoUserPoolId', '');
    const cognitoClientId = awsProps('cognitoClientId', '');

    if (!cognitoUserPoolId || !cognitoClientId) {
        // Auth disabled - return middleware that only handles anonymous users
        return (req, res, next) => {
            req.user = { tier: 'anonymous' };
            next();
        };
    }

    const verifier = CognitoJwtVerifier.create({
        userPoolId: cognitoUserPoolId,
        tokenUse: 'access',
        clientId: cognitoClientId
    });

    // Return the actual auth middleware
    return async (req, res, next) => {
        const authHeader = req.headers.authorization;
        let userId: string | null = null;
        let userTier: string = 'anonymous';

        if (authHeader?.startsWith('Bearer ')) {
            try {
                const token = authHeader.split(' ')[1];
                const payload = await verifier.verify(token);
                userId = payload.sub;
                userTier = 'authenticated';

                req.user = {
                    id: userId,
                    tier: userTier,
                    email: payload.email,
                    username: payload.username
                };
            } catch (error) {
                // Invalid token - reject to prevent rate limit bypass
                res.status(401).json({
                    error: 'Invalid authentication token',
                    message: 'Please sign in again'
                });
                return;
            }
        } else {
            req.user = { tier: 'anonymous' };
        }

        next();
    };
}
```

The important thing here is that we're using AWS's `aws-jwt-verify` library, which handles all the JWT validation complexity for us. It automatically fetches and caches the public keys from Cognito, so we don't need to store any secrets in the main application.

Using it in the main application is straightforward:

```typescript
// Usage in main application setup:
const authMiddleware = createAuthMiddleware(awsProps);
app.use('/api/*', authMiddleware);

// Example: Enhanced compilation endpoint
app.post('/api/compile', async (req, res) => {
    const { code, language, options } = req.body;

    // Validate inputs
    if (!code || !language) {
        return res.status(400).json({ error: 'Missing required fields' });
    }

    const result = await runCompilation(code, language, options);

    // Optional authenticated features
    if (req.user?.id) {
        // Higher rate limits already enforced by WAF
        result.user_tier = 'authenticated';
        result.rate_limit_tier = 'high';
    }

    res.json(result);
});
```

Notice that the compilation logic itself doesn't change at all - we just add some optional metadata for authenticated users. The WAF handles the actual rate limiting, so by the time a request reaches the web server, it's already been through the rate limit checks.
```

#### Token refresh: keeping users logged in

Token refresh is handled securely using httpOnly cookies. The refresh token is stored as an httpOnly cookie that gets sent automatically with requests to the `/auth/refresh` endpoint. This prevents XSS attacks from stealing long-lived refresh tokens.

The frontend calls the auth service directly for refresh:

```typescript
// Frontend calls auth service with httpOnly cookie automatically included
const response = await fetch('/auth/refresh', {
    method: 'POST',
    credentials: 'include', // Include httpOnly cookies
    headers: { 'Content-Type': 'application/json' }
});
```

The Lambda service handles refresh token validation and rotation:

**Option 2: Proxy through the main server** (if needed for routing)
If you want all API calls to go through the main CE server:

```typescript
export function createTokenRefreshEndpoint(awsProps: PropertyGetter) {
    const authServiceUrl = awsProps('authServiceUrl', 'https://api.compiler-explorer.com');

    return async (req, res) => {
        try {
            // Proxy to Lambda auth service with cookies forwarded
            const response = await fetch(`${authServiceUrl}/auth/refresh`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Cookie': req.headers.cookie || '' // Forward cookies
                }
            });

            if (!response.ok) {
                throw new Error('Token refresh failed');
            }

            const tokens = await response.json();
            res.json(tokens);

        } catch (error) {
            res.status(401).json({
                error: 'Invalid refresh token',
                message: 'Please sign in again'
            });
        }
    };
}
```

### Frontend integration

#### Adding auth to the navigation bar

The UI changes are pretty straightforward - we're adding a sign-in dropdown and a user menu. When you're not logged in, you see the sign-in options. When you are logged in, you see your username and some basic account options.

Here's the Pug template code for the navbar:

```pug
// views/index.pug - Add to navbar
ul.navbar-nav.ms-auto.mb-2.mb-md-0
  // ... existing items ...

  // Authentication section
  li.nav-item.dropdown#auth-dropdown.d-none
    button.btn.btn-light.nav-link.dropdown-toggle#auth-user(role="button" data-bs-toggle="dropdown" aria-expanded="false")
      span.dropdown-icon.fas.fa-user
      span#auth-username Loading...
    div.dropdown-menu.dropdown-menu-end(aria-labelledby="auth-user")
      div.dropdown-header
        span#auth-user-email
      div.dropdown-divider
      a.dropdown-item#auth-preferences(href="#")
        span.dropdown-icon.fas.fa-cog
        | Preferences
      a.dropdown-item#auth-history(href="#")
        span.dropdown-icon.fas.fa-history
        | History
      div.dropdown-divider
      button.dropdown-item#auth-sign-out
        span.dropdown-icon.fas.fa-sign-out-alt
        | Sign Out

  li.nav-item.dropdown#auth-sign-in
    button.btn.btn-light.nav-link.dropdown-toggle#auth-sign-in-btn(role="button" data-bs-toggle="dropdown" aria-expanded="false")
      span.dropdown-icon.fas.fa-sign-in-alt
      | Sign In
    div.dropdown-menu.dropdown-menu-end(aria-labelledby="auth-sign-in-btn")
      div.dropdown-header Sign in for higher rate limits
      button.dropdown-item.auth-provider(data-provider="GitHub")
        span.dropdown-icon.fab.fa-github
        | GitHub
      button.dropdown-item.auth-provider(data-provider="Google")
        span.dropdown-icon.fab.fa-google
        | Google
      button.dropdown-item.auth-provider(data-provider="SignInWithApple")
        span.dropdown-icon.fab.fa-apple
        | Apple
```

Nothing too fancy here - just standard Bootstrap dropdown components. The user dropdown starts hidden and shows up when you're authenticated, while the sign-in dropdown does the opposite.

#### The TypeScript client: handling auth in the browser

This is where most of the client-side logic lives. The `AuthClient` class handles OAuth redirects, token storage, and automatic refresh. It's designed to be pretty bulletproof - if something goes wrong, it just falls back to anonymous mode.

Here's the core of the client-side auth handling:

```typescript
// static/auth/auth-client.ts
export class AuthClient {
    private accessToken: string | null = null;
    private tokenExpiry: number = 0;

    async initialize(): Promise<void> {
        // Check for tokens in URL fragment (from auth redirect)
        const fragment = window.location.hash.substring(1);
        const params = new URLSearchParams(fragment);

        if (params.has('access_token')) {
            this.accessToken = params.get('access_token');
            const expiresIn = parseInt(params.get('expires_in') || '1800');

            // Store access token in localStorage
            localStorage.setItem('ce_access_token', this.accessToken);

            // Set expiry
            this.tokenExpiry = Date.now() + (expiresIn * 1000);
            localStorage.setItem('ce_token_expiry', this.tokenExpiry.toString());

            // Refresh token is automatically set as httpOnly cookie by server
            // No client-side storage needed

            // Clean URL
            window.history.replaceState({}, document.title, window.location.pathname);

            // Update UI
            await this.updateAuthUI();
        } else {
            // Try to get existing token from localStorage
            await this.loadFromStorage();
        }
    }
```

The initialization logic handles both cases - when someone is coming back from an OAuth redirect (tokens in the URL fragment) and when they're loading the page normally (check localStorage for existing tokens).

    async signIn(provider: string): Promise<void> {
        const returnTo = encodeURIComponent(window.location.href);
        const authUrl = `https://api.compiler-explorer.com/auth/login?provider=${provider}&return_to=${returnTo}`;
        window.location.href = authUrl;
    }

    async signOut(): Promise<void> {
        // Clear all tokens and state
        this.accessToken = null;
        this.tokenExpiry = 0;

        // Clear localStorage
        localStorage.removeItem('ce_access_token');
        localStorage.removeItem('ce_token_expiry');

        // Clear refresh token cookie by calling logout endpoint
        fetch('/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {
            // Ignore errors - user is logging out anyway
        });

        // Update UI
        this.updateAuthUI();
    }
```

Sign-in is just a redirect to the auth service with the current page URL so we can come back to the right place. Sign-out is even simpler - just clear everything and update the UI.

    async getValidToken(): Promise<string | null> {
        if (this.accessToken && Date.now() < this.tokenExpiry) {
            return this.accessToken;
        }

        return await this.refreshTokenIfNeeded();
    }
```

This is the method that other parts of the app call when they need a token. It automatically handles refresh if the current token is expired.

    private async loadFromStorage(): Promise<void> {
        const accessToken = localStorage.getItem('ce_access_token');
        const tokenExpiry = localStorage.getItem('ce_token_expiry');

        if (accessToken && tokenExpiry) {
            this.accessToken = accessToken;
            this.tokenExpiry = parseInt(tokenExpiry);

            // Check if token is expired
            if (Date.now() > this.tokenExpiry) {
                await this.refreshTokenIfNeeded();
            } else {
                await this.updateAuthUI();
            }
        }
    }

    private async refreshTokenIfNeeded(): Promise<string | null> {
        try {
            const response = await fetch('/auth/refresh', {
                method: 'POST',
                credentials: 'include', // Send httpOnly refresh token cookie
                headers: { 'Content-Type': 'application/json' }
            });

            if (!response.ok) {
                // Session expired or invalid - notify user and sign out
                this.handleRefreshFailure();
                return null;
            }

            const tokens = await response.json();

            // Update access token and expiry
            this.accessToken = tokens.access_token;
            this.tokenExpiry = Date.now() + (tokens.expires_in * 1000);

            // Store new access token (refresh token updated via httpOnly cookie)
            localStorage.setItem('ce_access_token', this.accessToken);
            localStorage.setItem('ce_token_expiry', this.tokenExpiry.toString());

            await this.updateAuthUI();
            return this.accessToken;

        } catch (error) {
            console.error('Token refresh failed:', error);
            this.handleRefreshFailure();
            return null;
        }
    }

    private handleRefreshFailure(): void {
        // Clear local auth state
        this.accessToken = null;
        this.tokenExpiry = 0;
        localStorage.removeItem('ce_access_token');
        localStorage.removeItem('ce_token_expiry');

        // Show notification to user
        this.showNotification('Your session has expired. Please sign in again.', 'warning');

        // Update UI to show session expired state
        this.updateAuthUI('session_expired');

        // Clear refresh token cookie
        fetch('/auth/logout', { method: 'POST', credentials: 'include' }).catch(() => {});
    }

    private showNotification(message: string, type: 'info' | 'warning' | 'error'): void {
        // Implementation depends on your notification system
        // Could be a toast, banner, or modal
        console.warn(message); // Fallback for now

        // Example with a simple banner:
        const banner = document.createElement('div');
        banner.className = `auth-notification auth-notification--${type}`;
        banner.textContent = message;
        document.body.insertBefore(banner, document.body.firstChild);

        // Auto-hide after 5 seconds
        setTimeout(() => banner.remove(), 5000);
    }
```

The refresh logic now actively notifies users when their session expires instead of silently logging them out.

    private async updateAuthUI(state?: 'session_expired'): Promise<void> {
        const signInDropdown = document.getElementById('auth-sign-in');
        const userDropdown = document.getElementById('auth-dropdown');
        const signInButton = document.getElementById('auth-sign-in-btn');

        if (this.accessToken) {
            // Get user info from token
            const payload = JSON.parse(atob(this.accessToken.split('.')[1]));

            // Update UI elements
            document.getElementById('auth-username').textContent = payload.username || 'User';
            document.getElementById('auth-user-email').textContent = payload.email || '';

            // Show user dropdown, hide sign in
            signInDropdown?.classList.add('d-none');
            userDropdown?.classList.remove('d-none');
        } else {
            // Show sign in dropdown, hide user dropdown
            signInDropdown?.classList.remove('d-none');
            userDropdown?.classList.add('d-none');

            // Update sign in button text based on state
            if (state === 'session_expired' && signInButton) {
                signInButton.textContent = 'Session Expired - Sign In Again';
                signInButton.classList.add('btn-warning');
                signInButton.classList.remove('btn-light');
            } else if (signInButton) {
                signInButton.textContent = 'Sign In';
                signInButton.classList.add('btn-light');
                signInButton.classList.remove('btn-warning');
            }
        }
    }
}
```

The UI update logic just toggles between showing the sign-in dropdown and the user dropdown, and populates the user info from the JWT payload. Since JWTs are just base64-encoded JSON, we can decode them client-side without any special libraries.

#### Plugging auth into the compilation API

The compilation service changes are minimal - we just need to include the auth token in requests when we have one. The service gracefully handles both authenticated and anonymous requests.

Here's how we modify the compiler service to include auth tokens:

```typescript
// static/compiler-service.ts - Enhanced API calls
export class CompilerService {
    constructor(private authClient: AuthClient) {}

    async compile(code: string, language: string, options: any): Promise<any> {
        const token = await this.authClient.getValidToken();

        const headers: Record<string, string> = {
            'Content-Type': 'application/json'
        };

        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch('/api/compile', {
            method: 'POST',
            headers,
            body: JSON.stringify({ code, language, options })
        });

        if (response.status === 401) {
            // Token expired, try refresh
            const newToken = await this.authClient.getValidToken();
            if (newToken) {
                headers['Authorization'] = `Bearer ${newToken}`;
                return fetch('/api/compile', {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ code, language, options })
                }).then(r => r.json());
            }
        }

        if (response.status === 429) {
            throw new Error('Rate limit exceeded. Please sign in for higher limits.');
        }

        return response.json();
    }
}
```

This handles the common scenarios: include the token if we have one, retry with a fresh token if we get a 401, and give a helpful error message if we hit rate limits. The important thing is that compilation still works fine even if all the auth stuff fails.

### Auth Lambda service

This is the one place in the system that knows about OAuth client secrets. It handles the OAuth dance with GitHub/Google/Apple and exchanges authorization codes for tokens. It's intentionally simple - just login, callback, and refresh endpoints.

#### Lambda function code

Here's the Lambda function that handles OAuth:

```python
import json
import urllib.parse
import base64
import requests
import os
from typing import Dict, Any

# Environment variables from SSM
COGNITO_DOMAIN = os.environ['COGNITO_DOMAIN']
CLIENT_ID = os.environ['COGNITO_CLIENT_ID']
CLIENT_SECRET = os.environ['COGNITO_CLIENT_SECRET']
CALLBACK_URL = "https://api.compiler-explorer.com/auth/callback"

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler for auth requests"""
    path = event.get('path', '')

    if path == '/auth/login':
        return handle_auth_login(event, context)
    elif path == '/auth/callback':
        return handle_auth_callback(event, context)
    elif path == '/auth/refresh':
        return handle_auth_refresh(event, context)
    elif path == '/auth/logout':
        return handle_auth_logout(event, context)
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not found'})
        }
```

Pretty straightforward - it's just a router that delegates to specific handlers based on the path.

def handle_auth_login(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Initiate OAuth flow"""
    try:
        params = event.get('queryStringParameters', {}) or {}
        provider = params.get('provider')
        return_to = params.get('return_to')

        if not provider or not return_to:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing required parameters'})
            }

        # Validate return_to is a CE domain
        if not is_valid_ce_domain(return_to):
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid return URL'})
            }

        # Build Cognito OAuth URL
        cognito_url = f"https://{COGNITO_DOMAIN}/oauth2/authorize"
        state = json.dumps({'return_to': return_to})

        redirect_params = {
            'client_id': CLIENT_ID,
            'response_type': 'code',
            'scope': 'openid email profile',
            'redirect_uri': CALLBACK_URL,
            'identity_provider': provider,
            'state': state
        }

        redirect_url = f"{cognito_url}?{urllib.parse.urlencode(redirect_params)}"

        return {
            'statusCode': 302,
            'headers': {
                'Location': redirect_url,
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Login initiation failed: {str(e)}'})
        }

def handle_auth_callback(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle Cognito callback and redirect back to CE"""
    try:
        params = event.get('queryStringParameters', {}) or {}
        code = params.get('code')
        state = params.get('state')

        if not code or not state:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Missing callback parameters'})
            }

        # Parse state
        state_data = json.loads(urllib.parse.unquote(state))
        return_to = state_data['return_to']

        # Exchange code for tokens
        tokens = exchange_code_for_tokens(code)

        # Set refresh token as httpOnly cookie
        refresh_cookie = f"ce_refresh_token={tokens['refresh_token']}; HttpOnly; Secure; SameSite=Strict; Max-Age={30 * 24 * 60 * 60}; Path=/auth"

        # Redirect back with access token only in URL fragment
        redirect_url = f"{return_to}#access_token={tokens['access_token']}&expires_in={tokens['expires_in']}"

        return {
            'statusCode': 302,
            'headers': {
                'Location': redirect_url,
                'Set-Cookie': refresh_cookie,
                'Cache-Control': 'no-cache, no-store, must-revalidate'
            }
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Callback handling failed: {str(e)}'})
        }

def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """Exchange authorization code for access/refresh tokens"""
    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"

    # Basic auth header
    client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    auth_header = base64.b64encode(client_credentials.encode()).decode()

    headers = {
        'Content-Type': 'application/x-www-form-urlencoded',
        'Authorization': f'Basic {auth_header}'
    }

    data = {
        'grant_type': 'authorization_code',
        'client_id': CLIENT_ID,
        'code': code,
        'redirect_uri': CALLBACK_URL
    }

    response = requests.post(
        token_url,
        headers=headers,
        data=urllib.parse.urlencode(data),
        timeout=10
    )

    if response.status_code != 200:
        raise Exception(f"Token exchange failed: {response.text}")

    return response.json()

def handle_auth_refresh(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle refresh token requests"""
    try:
        # Get refresh token from httpOnly cookie
        cookies = event.get('headers', {}).get('cookie', '')
        refresh_token = None

        for cookie in cookies.split(';'):
            cookie = cookie.strip()
            if cookie.startswith('ce_refresh_token='):
                refresh_token = cookie.split('=', 1)[1]
                break

        if not refresh_token:
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'No refresh token provided'})
            }

        # Exchange refresh token for new access token
        token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
        client_credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
        auth_header = base64.b64encode(client_credentials.encode()).decode()

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {auth_header}'
        }

        data = {
            'grant_type': 'refresh_token',
            'client_id': CLIENT_ID,
            'refresh_token': refresh_token
        }

        response = requests.post(
            token_url,
            headers=headers,
            data=urllib.parse.urlencode(data),
            timeout=10
        )

        if response.status_code != 200:
            return {
                'statusCode': 401,
                'body': json.dumps({'error': 'Refresh token invalid or expired'})
            }

        tokens = response.json()

        # Set new refresh token as httpOnly cookie (token rotation)
        new_refresh_cookie = f"ce_refresh_token={tokens['refresh_token']}; HttpOnly; Secure; SameSite=Strict; Max-Age={30 * 24 * 60 * 60}; Path=/auth"

        return {
            'statusCode': 200,
            'headers': {
                'Set-Cookie': new_refresh_cookie,
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'access_token': tokens['access_token'],
                'expires_in': tokens['expires_in']
            })
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Refresh failed: {str(e)}'})
        }

def handle_auth_logout(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Handle logout requests - clear refresh token cookie"""
    # Clear refresh token cookie
    clear_cookie = "ce_refresh_token=; HttpOnly; Secure; SameSite=Strict; Max-Age=0; Path=/auth"

    return {
        'statusCode': 200,
        'headers': {
            'Set-Cookie': clear_cookie,
            'Content-Type': 'application/json'
        },
        'body': json.dumps({'message': 'Logged out successfully'})
    }

def is_valid_ce_domain(url: str) -> bool:
    """Validate return URL is a CE domain"""
    allowed_domains = [
        'godbolt.org',
        'compiler-explorer.com',
        'localhost:10240'  # Development only
    ]

    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # Check exact match or subdomain
        return any(
            domain == allowed or domain.endswith(f'.{allowed}')
            for allowed in allowed_domains
        )
    except Exception:
        return False
```

### WAF configuration

This is where the rate limiting actually happens. The WAF sits in front of CloudFront and looks at incoming requests. If you have a Bearer token in your Authorization header, you get the high rate limit. If not, you get the standard anonymous limit.

#### The WAF rules

The rule order matters here - we check for authenticated users first (higher limits), then fall back to anonymous limits for everyone else:

```terraform
# WAF rules for authenticated vs anonymous users
resource "aws_wafv2_web_acl" "compiler_explorer_enhanced" {
  name  = "compiler-explorer-enhanced"
  scope = "CLOUDFRONT"

  default_action {
    allow {}
  }

  # Rule 1: Authenticated users get higher limits (checked first)
  rule {
    name     = "AuthenticatedRateLimit"
    priority = 1

    statement {
      rate_based_statement {
        limit              = 1000  # 1000 requests per 5-minute window
        aggregate_key_type = "IP"

        # Only apply to requests WITH Authorization header
        scope_down_statement {
          byte_match_statement {
            search_string = "Bearer "
            field_to_match {
              single_header {
                name = "authorization"
              }
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
            positional_constraint = "STARTS_WITH"
          }
        }
      }
    }

    action {
      block {}
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name               = "AuthenticatedRateLimit"
      sampled_requests_enabled  = true
    }
  }

  # Rule 2: Anonymous users get lower limits (checked second)
  rule {
    name     = "AnonymousRateLimit"
    priority = 2

    statement {
      rate_based_statement {
        limit              = 100  # 100 requests per 5-minute window
        aggregate_key_type = "IP"

        # Only apply to requests WITHOUT Authorization header
        scope_down_statement {
          not_statement {
            statement {
              byte_match_statement {
                search_string = "Bearer "
                field_to_match {
                  single_header {
                    name = "authorization"
                  }
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
                positional_constraint = "STARTS_WITH"
              }
            }
          }
        }
      }
    }

    action {
      block {}
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name               = "AnonymousRateLimit"
      sampled_requests_enabled  = true
    }
  }

  # Rule 3: Block malformed auth headers
  rule {
    name     = "BlockMalformedAuth"
    priority = 3

    statement {
      and_statement {
        statement {
          byte_match_statement {
            search_string = "Bearer"
            field_to_match {
              single_header {
                name = "authorization"
              }
            }
            text_transformation {
              priority = 0
              type     = "NONE"
            }
            positional_constraint = "CONTAINS"
          }
        }
        statement {
          not_statement {
            statement {
              regex_pattern_set_reference_statement {
                arn = aws_wafv2_regex_pattern_set.valid_jwt_pattern.arn
                field_to_match {
                  single_header {
                    name = "authorization"
                  }
                }
                text_transformation {
                  priority = 0
                  type     = "NONE"
                }
              }
            }
          }
        }
      }
    }

    action {
      block {}
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name               = "BlockMalformedAuth"
      sampled_requests_enabled  = true
    }
  }
}

# Regex pattern for valid JWT format
resource "aws_wafv2_regex_pattern_set" "valid_jwt_pattern" {
  name  = "valid-jwt-pattern"
  scope = "CLOUDFRONT"

  regular_expression {
    regex_string = "^Bearer [A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$"
  }
}

# Associate WAF with CloudFront
resource "aws_wafv2_web_acl_association" "compiler_explorer_cloudfront" {
  resource_arn = aws_cloudfront_distribution.compiler_explorer.arn
  web_acl_arn  = aws_wafv2_web_acl.compiler_explorer_enhanced.arn
}
```

## AWS Infrastructure

### Setting up Cognito

Cognito is AWS's identity service, and while it's not the most exciting thing in the world, it handles all the OAuth complexity for us. We need a user pool (where user accounts live) and identity providers for GitHub, Google, and Apple.

Here's the Terraform for the Cognito user pool:

```terraform
# Main User Pool
resource "aws_cognito_user_pool" "compiler_explorer" {
  name = "compiler-explorer-users"

  # Email-based account linking
  alias_attributes    = ["email"]
  username_attributes = ["email"]

  # Strong password policy
  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }
```

The important bit here is the email-based account linking - this means if you sign in with GitHub using the same email address as your Google account, Cognito will treat them as the same user. Pretty neat.

  # Required attributes
  schema {
    attribute_data_type = "String"
    name               = "email"
    required           = true
    mutable            = true
  }

  schema {
    attribute_data_type = "String"
    name               = "preferred_username"
    required           = false
    mutable            = true
  }

  # Account recovery
  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  # Prevent user enumeration
  user_pool_add_ons {
    advanced_security_mode = "ENFORCED"
  }

  # Supported identity providers
  supported_identity_providers = ["COGNITO", "GitHub", "Google", "SignInWithApple"]
}

# User Pool Client
resource "aws_cognito_user_pool_client" "compiler_explorer_client" {
  name         = "compiler-explorer-web"
  user_pool_id = aws_cognito_user_pool.compiler_explorer.id

  # Callback URLs for auth flow
  callback_urls = [
    "https://api.compiler-explorer.com/auth/callback",
    "http://localhost:10240/auth/callback"  # Development
  ]

  logout_urls = [
    "https://godbolt.org/",
    "https://compiler-explorer.com/",
    "http://localhost:10240/"
  ]

  # OAuth setup
  supported_identity_providers = ["GitHub", "Google", "SignInWithApple"]
  oauth_flows                 = ["code"]
  oauth_scopes               = ["email", "openid", "profile"]

  # Attributes
  read_attributes  = ["email", "email_verified", "identities", "preferred_username"]
  write_attributes = ["email", "preferred_username"]

  # Token lifetimes
  access_token_validity  = 30    # 30 minutes
  refresh_token_validity = 30    # 30 days

  token_validity_units {
    access_token  = "minutes"
    refresh_token = "days"
  }

  # Security settings
  prevent_user_existence_errors = "ENABLED"
  explicit_auth_flows = ["ALLOW_REFRESH_TOKEN_AUTH"]
}

# User Pool Domain
resource "aws_cognito_user_pool_domain" "compiler_explorer" {
  domain       = "auth-ce-${random_string.domain_suffix.result}"
  user_pool_id = aws_cognito_user_pool.compiler_explorer.id
}

resource "random_string" "domain_suffix" {
  length  = 8
  special = false
  upper   = false
}
```

### Setting up the identity providers

#### GitHub Provider (via OIDC Wrapper)

```terraform
# GitHub OAuth App credentials (stored in SSM)
resource "aws_ssm_parameter" "github_client_id" {
  name  = "/ce/auth/github/client_id"
  type  = "String"
  value = var.github_oauth_client_id
}

resource "aws_ssm_parameter" "github_client_secret" {
  name  = "/ce/auth/github/client_secret"
  type  = "SecureString"
  value = var.github_oauth_client_secret
}

# GitHub OIDC wrapper (battle-tested community solution)
resource "aws_cloudformation_stack" "github_oidc_wrapper" {
  name         = "github-oidc-wrapper"
  template_url = "https://github.com/TimothyJones/github-cognito-openid-wrapper/releases/latest/download/template.yaml"

  parameters = {
    GitHubClientId     = var.github_oauth_client_id
    GitHubClientSecret = var.github_oauth_client_secret
    CognitoDomain      = aws_cognito_user_pool_domain.compiler_explorer.domain
  }

  capabilities = ["CAPABILITY_IAM"]
}

# GitHub Identity Provider
resource "aws_cognito_identity_provider" "github_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "GitHub"
  provider_type = "OIDC"

  provider_details = {
    client_id     = var.github_oauth_client_id
    client_secret = var.github_oauth_client_secret

    # OIDC endpoints from wrapper
    oidc_issuer      = aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]
    authorize_scopes = "openid email profile"

    # GitHub-specific URLs
    authorize_url    = "https://github.com/login/oauth/authorize"
    token_url        = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/token"
    attributes_url   = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/userinfo"
    jwks_uri         = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/.well-known/jwks.json"
  }

  # Attribute mapping for account linking
  attribute_mapping = {
    email              = "email"
    username           = "login"
    preferred_username = "login"
    name               = "name"
    email_verified     = "email_verified"
  }
}
```

#### Google Provider

```terraform
# Google OAuth credentials
resource "aws_ssm_parameter" "google_client_id" {
  name  = "/ce/auth/google/client_id"
  type  = "String"
  value = var.google_oauth_client_id
}

resource "aws_ssm_parameter" "google_client_secret" {
  name  = "/ce/auth/google/client_secret"
  type  = "SecureString"
  value = var.google_oauth_client_secret
}

# Google Identity Provider (native Cognito support)
resource "aws_cognito_identity_provider" "google_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id        = var.google_oauth_client_id
    client_secret    = var.google_oauth_client_secret
    authorize_scopes = "email openid profile"
  }

  # Account linking via email
  attribute_mapping = {
    email          = "email"
    username       = "sub"
    name           = "name"
    email_verified = "email_verified"
  }
}
```

#### Apple Provider

```terraform
# Apple Sign-In credentials
resource "aws_ssm_parameter" "apple_service_id" {
  name  = "/ce/auth/apple/service_id"
  type  = "String"
  value = var.apple_service_id
}

resource "aws_ssm_parameter" "apple_private_key" {
  name  = "/ce/auth/apple/private_key"
  type  = "SecureString"
  value = var.apple_private_key
}

# Apple Identity Provider
resource "aws_cognito_identity_provider" "apple_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "SignInWithApple"
  provider_type = "SignInWithApple"

  provider_details = {
    client_id       = var.apple_service_id
    team_id         = var.apple_team_id
    key_id          = var.apple_key_id
    private_key     = var.apple_private_key
    authorize_scopes = "email name"
  }

  # Apple-specific attribute mapping
  attribute_mapping = {
    email    = "email"
    username = "sub"
    name     = "name"
  }
}
```

### Lambda Auth Service Infrastructure

```terraform
# Lambda function for auth service
resource "aws_lambda_function" "auth_service" {
  filename         = "auth_service.zip"
  function_name    = "ce-auth-service"
  role            = aws_iam_role.auth_service_role.arn
  handler         = "lambda_function.lambda_handler"
  runtime         = "python3.9"
  timeout         = 30

  environment {
    variables = {
      COGNITO_DOMAIN        = aws_cognito_user_pool_domain.compiler_explorer.domain
      COGNITO_CLIENT_ID     = aws_cognito_user_pool_client.compiler_explorer_client.id
      COGNITO_CLIENT_SECRET = aws_cognito_user_pool_client.compiler_explorer_client.client_secret
    }
  }
}

# IAM role for Lambda
resource "aws_iam_role" "auth_service_role" {
  name = "ce-auth-service-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })
}

# Lambda execution policy
resource "aws_iam_role_policy_attachment" "auth_service_execution" {
  role       = aws_iam_role.auth_service_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# API Gateway for Lambda
resource "aws_apigatewayv2_api" "auth_service" {
  name          = "ce-auth-service"
  protocol_type = "HTTP"

  cors_configuration {
    allow_origins = [
      "https://godbolt.org",
      "https://*.godbolt.org",
      "https://compiler-explorer.com",
      "https://*.compiler-explorer.com"
    ]
    allow_methods = ["GET", "POST", "OPTIONS"]
    allow_headers = ["Content-Type", "Authorization"]
    max_age       = 86400
  }
}

# API Gateway integration
resource "aws_apigatewayv2_integration" "auth_service" {
  api_id           = aws_apigatewayv2_api.auth_service.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.auth_service.invoke_arn
}

# API Gateway routes
resource "aws_apigatewayv2_route" "auth_login" {
  api_id    = aws_apigatewayv2_api.auth_service.id
  route_key = "GET /auth/login"
  target    = "integrations/${aws_apigatewayv2_integration.auth_service.id}"
}

resource "aws_apigatewayv2_route" "auth_callback" {
  api_id    = aws_apigatewayv2_api.auth_service.id
  route_key = "GET /auth/callback"
  target    = "integrations/${aws_apigatewayv2_integration.auth_service.id}"
}

resource "aws_apigatewayv2_route" "auth_refresh" {
  api_id    = aws_apigatewayv2_api.auth_service.id
  route_key = "POST /auth/refresh"
  target    = "integrations/${aws_apigatewayv2_integration.auth_service.id}"
}

resource "aws_apigatewayv2_route" "auth_logout" {
  api_id    = aws_apigatewayv2_api.auth_service.id
  route_key = "POST /auth/logout"
  target    = "integrations/${aws_apigatewayv2_integration.auth_service.id}"
}

# Lambda permission for API Gateway
resource "aws_lambda_permission" "auth_service_apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_service.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.auth_service.execution_arn}/*/*"
}
```

## Rolling this out: a step-by-step deployment plan

Deploying auth is always a bit nerve-wracking because if you mess it up, you can break things for everyone. Here's how I'd approach it - cautiously, with lots of testing, and with easy rollback options.

### Get the infrastructure ready

First, we need to set up all the OAuth applications and AWS resources. This can be done without affecting the running system at all.

#### Create the OAuth applications

You'll need to create OAuth apps with each provider:

- GitHub: Go to https://github.com/settings/applications/new and create a new app
- Google: Head to https://console.developers.google.com/ and set up OAuth 2.0 credentials
- Apple: Use https://developer.apple.com/account/resources/identifiers/list/serviceId for Sign in with Apple

Make sure the callback URLs point to your Cognito domain (you'll get this after deploying the infrastructure).

#### Deploy the infrastructure

```bash
cd terraform/

# Set your OAuth credentials
export TF_VAR_github_oauth_client_id="your_github_client_id"
export TF_VAR_github_oauth_client_secret="your_github_client_secret"
export TF_VAR_google_oauth_client_id="your_google_client_id"
export TF_VAR_google_oauth_client_secret="your_google_client_secret"

# Deploy everything
terraform init
terraform plan
terraform apply
```

#### Set up DNS

Add a CNAME record pointing auth.compiler-explorer.com to your API Gateway URL (Terraform will output this).

### Wire up the backend

#### Update the environment variables

Add the Cognito details to your server environment:

```bash
export COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
export COGNITO_CLIENT_ID="your_client_id"
export COGNITO_DOMAIN="auth-ce-12345678.auth.us-east-1.amazoncognito.com"
```

#### Install the JWT verification library

```bash
npm install aws-jwt-verify
```

#### Deploy and test the backend changes

```bash
# Test everything locally first
npm run test
npm run lint

# Deploy to staging
./deploy.sh staging

# Make sure the auth endpoints respond
curl -X POST https://staging.godbolt.org/api/auth/refresh
```

### Frontend integration

#### Add the TypeScript auth client

Copy the `AuthClient` code into `static/auth/auth-client.ts` and update your main application JavaScript to initialize it on page load.

#### Update the Pug templates

Add the authentication dropdown menus to `views/index.pug`. Test that everything renders properly before moving on.

#### Test the whole flow

```bash
npm run dev
```

Then manually test the authentication flow:
- Click "Sign In with GitHub"
- Complete the OAuth dance
- Verify tokens are stored in localStorage
- Make API calls and confirm the Bearer token is included
- Test token refresh by waiting for expiration
- Test sign out clears everything

### Enable the WAF rules

#### Deploy the rate limiting rules

```bash
cd terraform/
terraform apply -target=aws_wafv2_web_acl.compiler_explorer_enhanced
```

#### Test that rate limiting works

```bash
# Test anonymous rate limiting (should get blocked after 100 requests)
for i in {1..110}; do curl -s https://godbolt.org/api/compile; done

# Test authenticated rate limiting (should allow 1000+ requests)
for i in {1..1010}; do curl -s -H "Authorization: Bearer $TOKEN" https://godbolt.org/api/compile; done
```

### Production deployment

#### Deploy to beta first

```bash
# Deploy to beta environment
./deploy.sh beta

# Monitor for 24 hours
# Check CloudWatch metrics
# Verify no increase in error rates

# If everything looks good, deploy to production
./deploy.sh production
```

#### Verify everything works in production

Once it's live, test all the auth flows manually, check that rate limiting is working as expected, and keep an eye on the CloudWatch dashboards. Have a rollback plan ready just in case.

## Testing strategy

### Unit tests for the backend

We need to test the auth middleware thoroughly since it's the core piece that decides whether requests are authenticated or not.
Here are the key tests for the auth middleware:

```typescript
// test/auth.test.ts
describe('Authentication Middleware', () => {
    it('should allow anonymous requests', async () => {
        const req = mockRequest();
        const res = mockResponse();
        const next = jest.fn();

        await authMiddleware(req, res, next);

        expect(req.user).toEqual({ tier: 'anonymous' });
        expect(next).toHaveBeenCalled();
    });

    it('should validate valid JWT tokens', async () => {
        const validToken = createValidJWT();
        const req = mockRequest({
            headers: { authorization: `Bearer ${validToken}` }
        });
        const res = mockResponse();
        const next = jest.fn();

        await authMiddleware(req, res, next);

        expect(req.user.tier).toBe('authenticated');
        expect(req.user.id).toBeTruthy();
        expect(next).toHaveBeenCalled();
    });

    it('should reject invalid tokens', async () => {
        const invalidToken = 'invalid.token.here';
        const req = mockRequest({
            headers: { authorization: `Bearer ${invalidToken}` }
        });
        const res = mockResponse();
        const next = jest.fn();

        await authMiddleware(req, res, next);

        expect(res.status).toHaveBeenCalledWith(401);
        expect(next).not.toHaveBeenCalled();
    });
});
```

The important thing here is testing all three scenarios: no token (anonymous), valid token (authenticated), and invalid token (rejected).

### Frontend tests
The frontend auth client needs testing too, especially the token handling logic:

```typescript
// test/auth-client.test.ts
describe('AuthClient', () => {
    let authClient: AuthClient;

    beforeEach(() => {
        authClient = new AuthClient();
        // Mock localStorage and fetch
    });

    it('should initialize without tokens', async () => {
        await authClient.initialize();
        expect(authClient.getValidToken()).resolves.toBeNull();
    });

    it('should handle OAuth redirect', async () => {
        // Mock URL with auth tokens
        Object.defineProperty(window, 'location', {
            value: { hash: '#access_token=test&refresh_token=refresh&expires_in=1800' }
        });

        await authClient.initialize();

        expect(authClient.getValidToken()).resolves.toBe('test');
    });

    it('should refresh expired tokens', async () => {
        // Mock expired token scenario
        // Test refresh flow
    });
});
```

Testing frontend auth is a bit tricky because you need to mock localStorage and fetch, but it's worth doing to catch bugs in the token refresh logic.

### Integration tests

These are the tests that actually exercise the whole auth flow from start to finish.
```typescript
// test/integration/auth-flow.test.ts
describe('End-to-End Auth Flow', () => {
    it('should complete GitHub OAuth flow', async () => {
        // Start auth flow
        const authUrl = await startAuthFlow('GitHub');
        expect(authUrl).toContain('github.com/login/oauth/authorize');

        // Mock OAuth callback
        const tokens = await mockOAuthCallback();
        expect(tokens.access_token).toBeTruthy();
        expect(tokens.refresh_token).toBeTruthy();

        // Use token for API call
        const response = await makeAuthenticatedRequest(tokens.access_token);
        expect(response.status).toBe(200);
    });

    it('should handle token refresh', async () => {
        // Test token refresh flow
    });

    it('should handle sign out', async () => {
        // Test sign out flow
    });
});
```

### Rate limiting tests

We definitely need to verify that the WAF rules work as expected:
```typescript
// test/integration/rate-limiting.test.ts
describe('Rate Limiting', () => {
    it('should enforce anonymous rate limits', async () => {
        // Make 101 requests without auth
        const responses = await Promise.all(
            Array(101).fill(null).map(() =>
                fetch('/api/compile', { method: 'POST' })
            )
        );

        // First 100 should succeed, 101st should be rate limited
        expect(responses.slice(0, 100).every(r => r.status === 200)).toBe(true);
        expect(responses[100].status).toBe(429);
    });

    it('should allow higher limits for authenticated users', async () => {
        const token = await getValidToken();

        // Make 101 requests with auth (should all succeed)
        const responses = await Promise.all(
            Array(101).fill(null).map(() =>
                fetch('/api/compile', {
                    method: 'POST',
                    headers: { 'Authorization': `Bearer ${token}` }
                })
            )
        );

        expect(responses.every(r => r.status === 200)).toBe(true);
    });
});
```

### Load testing

Once everything is working, we should load test the auth endpoints to make sure they can handle realistic traffic:

```bash
# Load test auth endpoints
artillery run auth-load-test.yml

# Test compilation API with auth
artillery run compile-auth-load-test.yml
```

## Security considerations

### A few things to remember about tokens

A few things to remember about how we're handling tokens:

- **30-minute access token lifetime** strikes a good balance between security and usability
- **localStorage protection** relies on CSP headers and XSS prevention - if someone can run arbitrary JS in your browser, you have bigger problems
- **JWT validation** happens using public keys, so no secrets needed in the main app
- **Token rotation** - refresh tokens get rotated on each use for better security
- **Automatic cleanup** - expired tokens are automatically removed from localStorage

### Protecting against XSS attacks

```typescript
// Security headers for localStorage protection
export function createSecurityHeaders(awsProps: PropertyGetter) {
    const isProduction = awsProps('environment', 'development') === 'production';

    return {
        // Strong Content Security Policy
        'Content-Security-Policy': [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline'", // Monaco editor requires unsafe-inline
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: https:",
            "connect-src 'self' https://api.compiler-explorer.com https://auth.compiler-explorer.com",
            "font-src 'self' data:",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'"
        ].join('; '),

        // XSS protection
        'X-XSS-Protection': '1; mode=block',
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'DENY',

        // HTTPS enforcement
        'Strict-Transport-Security': isProduction
            ? 'max-age=31536000; includeSubDomains; preload'
            : 'max-age=86400',

        // Referrer policy
        'Referrer-Policy': 'strict-origin-when-cross-origin'
    };
}
```

### CORS setup

```typescript
// CORS setup for the main app
const corsOptions = {
    origin: function (origin, callback) {
        const allowedOrigins = [
            'https://godbolt.org',
            'https://compiler-explorer.com',
            /^https:\/\/[\w-]+\.godbolt\.org$/,
            /^https:\/\/[\w-]+\.compiler-explorer\.com$/
        ];

        if (!origin || allowedOrigins.some(allowed =>
            typeof allowed === 'string' ? allowed === origin : allowed.test(origin)
        )) {
            callback(null, true);
        } else {
            callback(new Error('Not allowed by CORS'));
        }
    },
    credentials: true,
    optionsSuccessStatus: 200,
    maxAge: 86400
};
```

### Content Security Policy

```typescript
// CSP headers for auth pages
const cspDirectives = {
    defaultSrc: ["'self'"],
    scriptSrc: ["'self'", "'unsafe-inline'"],
    styleSrc: ["'self'", "'unsafe-inline'"],
    imgSrc: ["'self'", "data:", "https:"],
    connectSrc: [
        "'self'",
        "https://api.compiler-explorer.com",
        "https://auth.compiler-explorer.com",
        "https://cognito-idp.us-east-1.amazonaws.com"
    ],
    formAction: ["'self'", "https://github.com", "https://accounts.google.com"],
    frameAncestors: ["'none'"],
    upgradeInsecureRequests: []
};
```

### Input Validation

```typescript
// Request validation middleware
const validateAuthRequest = (req: Request, res: Response, next: NextFunction) => {
    const authHeader = req.headers.authorization;

    if (authHeader) {
        // Validate JWT format
        const tokenRegex = /^Bearer [A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/;
        if (!tokenRegex.test(authHeader)) {
            return res.status(400).json({ error: 'Invalid token format' });
        }

        // Validate token length (prevent DoS)
        if (authHeader.length > 2048) {
            return res.status(400).json({ error: 'Token too long' });
        }
    }

    next();
};
```

## Monitoring and alerts

### CloudWatch metrics to track

We'll want to keep track of authentication events and spot any suspicious activity:

Here are the metrics I'd track:

```typescript
// Custom metrics for auth system
const authMetrics = {
    // Authentication events
    'CE/Auth/SignIn': { provider: string, success: boolean },
    'CE/Auth/TokenRefresh': { success: boolean },
    'CE/Auth/SignOut': { success: boolean },

    // Rate limiting
    'CE/Auth/RateLimitHit': { tier: 'anonymous' | 'authenticated' },
    'CE/Auth/RequestsWithAuth': { count: number },
    'CE/Auth/RequestsWithoutAuth': { count: number },

    // Security events
    'CE/Auth/InvalidToken': { count: number },
    'CE/Auth/MalformedToken': { count: number },
    'CE/Auth/SuspiciousActivity': { ip: string, reason: string }
};
```

These metrics will help us understand how auth is being used and spot any problems early.

### CloudWatch Dashboard

```json
{
    "widgets": [
        {
            "type": "metric",
            "properties": {
                "metrics": [
                    ["AWS/WAF", "AllowedRequests", "WebACL", "compiler-explorer-enhanced"],
                    ["AWS/WAF", "BlockedRequests", "WebACL", "compiler-explorer-enhanced"]
                ],
                "period": 300,
                "stat": "Sum",
                "region": "us-east-1",
                "title": "WAF Requests"
            }
        },
        {
            "type": "metric",
            "properties": {
                "metrics": [
                    ["CE/Auth", "SignIn", "Provider", "GitHub"],
                    ["CE/Auth", "SignIn", "Provider", "Google"],
                    ["CE/Auth", "SignIn", "Provider", "Apple"]
                ],
                "period": 300,
                "stat": "Sum",
                "title": "Sign-ins by Provider"
            }
        }
    ]
}
```

### Alerts

A couple of key alerts to set up:

```terraform
# High rate of auth failures
resource "aws_cloudwatch_metric_alarm" "auth_failure_rate" {
  alarm_name          = "ce-auth-high-failure-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "InvalidToken"
  namespace           = "CE/Auth"
  period              = "300"
  statistic           = "Sum"
  threshold           = "100"
  alarm_description   = "High rate of authentication failures"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}

# WAF blocking too many requests
resource "aws_cloudwatch_metric_alarm" "waf_block_rate" {
  alarm_name          = "ce-waf-high-block-rate"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = "2"
  metric_name         = "BlockedRequests"
  namespace           = "AWS/WAF"
  period              = "300"
  statistic           = "Sum"
  threshold           = "1000"
  alarm_description   = "WAF blocking high number of requests"
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

## GDPR and privacy: what data we collect

### What we're actually collecting

Let's be clear about what data we collect and what we don't:

#### What we collect
- Email address (for linking accounts across providers)
- Username (from your OAuth provider)
- When you sign in and out
- Which provider you used (GitHub, Google, Apple)
- Auth tokens (stored in your browser's localStorage)

#### What we DON'T collect
- Your compilation code (that stays anonymous)
- IP addresses (beyond AWS's standard logging)
- Browsing history or tracking data
- Personal preferences (unless you explicitly save them later)

#### About token storage
Short-lived access tokens (30 minutes) are stored in localStorage for use in API calls. Long-lived refresh tokens (30 days) are stored as secure httpOnly cookies that JavaScript cannot access, protecting them from XSS attacks. You can clear all authentication data by clearing your browser data or signing out.

### User Rights Implementation

#### Data Export
```typescript
// API endpoint for data export
app.get('/api/user/export', requireAuth, async (req, res) => {
    const userId = req.user.id;

    try {
        // Get user profile from Cognito
        const userProfile = await cognitoClient.adminGetUser({
            UserPoolId: process.env.COGNITO_USER_POOL_ID,
            Username: userId
        }).promise();

        // Compile export data
        const exportData = {
            profile: {
                userId,
                email: userProfile.UserAttributes?.find(attr => attr.Name === 'email')?.Value,
                createdAt: userProfile.UserCreateDate,
                lastModified: userProfile.UserLastModifiedDate,
                providers: userProfile.UserAttributes?.find(attr => attr.Name === 'identities')?.Value
            },
            // Note: CE doesn't store compilation history, so no data to export
            exportDate: new Date().toISOString(),
            format: 'json'
        };

        res.json(exportData);

    } catch (error) {
        res.status(500).json({ error: 'Export failed' });
    }
});
```

#### Data Deletion
```typescript
// API endpoint for account deletion
app.delete('/api/user/account', requireAuth, async (req, res) => {
    const userId = req.user.id;

    try {
        // Delete user from Cognito
        await cognitoClient.adminDeleteUser({
            UserPoolId: process.env.COGNITO_USER_POOL_ID,
            Username: userId
        }).promise();

        // Note: No additional data to delete since CE doesn't store user data
        // In future, CE would need to think about user links, configuration etc

        res.json({ message: 'Account deleted successfully' });

    } catch (error) {
        res.status(500).json({ error: 'Deletion failed' });
    }
});
```

### Privacy Policy Updates

#### Required additions
1. **Optional Authentication**: Clearly state that authentication is optional and anonymous usage continues unchanged
2. **Data Collection**: Describe what data is collected for authenticated users (email, username, auth timestamps)
3. **Data Usage**: Explain how data is used (account linking, rate limiting, user identification)
4. **Token Storage**: Mention that short-lived access tokens are stored in browser localStorage, and long-lived refresh tokens are stored as secure httpOnly cookies
5. **Cookie Usage**: Update cookie policy to include authentication cookies - these are essential for login functionality and cannot be disabled
6. **Data Retention**: 30-day refresh token lifetime, automatic cleanup of expired tokens
7. **User Rights**: Data export and account deletion capabilities
8. **Third-party Providers**: OAuth integration with GitHub, Google, and Apple
9. **No Tracking**: Emphasize that compilation code remains anonymous and no additional tracking is introduced


## Performance considerations

### Latency impact

JWT verification happens on every authenticated request, but the `aws-jwt-verify` library caches the public keys and updates them every 5 minutes, so the overhead should be minimal. We'll need to measure the actual impact in the CE environment, but I don't expect it to be noticeable.

WAF evaluation adds less than 1ms per request and doesn't affect compilation performance at all.

### Throughput impact

For anonymous users, nothing changes - same limits, same performance.

For authenticated users, they get 10x higher rate limits with no additional server load (since the WAF handles the limiting).


## Future enhancements

### Potential features

Once we have authentication working, there are lots of interesting features we could add:

**User preferences storage** - Save your favorite theme, compiler defaults, and layout preferences across devices.

**Compilation history** - Optionally keep a history of your compilations with search and filtering. Could be really useful for tracking down that one example you wrote last month.

**Link ownership** - Associate short links with user accounts so you can manage and analyze your shared code snippets.

**Advanced rate limiting** - Per-user limits, supporter tier benefits, usage analytics. Could be interesting for understanding how CE is being used.

### Technical improvements

**Security enhancements** - We could rotate JWT signing keys periodically, implement PKCE for OAuth (more secure than the basic flow), or add 2FA support for power users.

**Performance optimizations** - JWT token caching could help if we see high CPU usage from token validation, but it would require Redis and adds complexity around cache invalidation. CDN for auth assets might also help.

**Operational stuff** - More automated testing, enhanced monitoring, maybe some chaos engineering to test failure scenarios.

## Wrapping up

This authentication system gives us what we need:

- **Simple integration** with minimal changes to existing code
- **Security without secrets** in the main web application
- **Optional usage** - anonymous users keep working exactly as before
- **Developer-focused** providers (GitHub, Google, Apple)
- **Scalable rate limiting** handled by WAF
- **Account linking** across providers via email
- **GDPR compliance** with data export and deletion
- **Good monitoring** with metrics and alerts
- **Clear path forward** for both repositories

We can roll this out incrementally - set up the infrastructure, integrate the backend, add the frontend pieces, then harden and test everything. The design keeps things as simple as possible while meeting CE's security and scalability needs.

Most importantly, if something goes wrong with auth, anonymous users keep working. That's the safety net that makes this whole thing viable.
