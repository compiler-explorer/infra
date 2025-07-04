# Compiler Explorer Authentication Design

## Overview

This document outlines the design for adding optional authentication to Compiler Explorer using AWS Cognito. The system will support GitHub, Google, and Apple login while maintaining full anonymous functionality.

### Goals
- **Optional authentication**: Anonymous users continue to work exactly as before
- **Minimal complexity**: Few moving parts, leveraging AWS native services
- **Security first**: No secrets in web server code, proper token validation
- **Developer-focused**: GitHub as primary provider, with Google and Apple support
- **Higher rate limits**: Authenticated users get improved rate limits via WAF

### Architecture Overview

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

## Security Requirements

### Threat Model

**Primary Threats:**
1. **Secrets exposure**: Web server compromise must not expose auth secrets
2. **Token theft**: XSS/CSRF attacks stealing user tokens
3. **Rate limit bypass**: Malicious users circumventing rate limits
4. **Account takeover**: Unauthorized access to user accounts
5. **Data leakage**: Unauthorized access to user data

**Security Controls:**
1. **Secret isolation**: All auth secrets confined to Lambda auth service
2. **Token validation**: JWT verification without storing secrets
3. **WAF enforcement**: Rate limiting at CloudFront level
4. **XSS protection**: Strong CSP headers and input sanitization
5. **CORS restrictions**: Strict origin validation
6. **Input validation**: All user inputs validated and sanitized

### Token Security Strategy

**Access Tokens:**
- 30-minute lifetime (balance security vs usability)
- JWT format with standard claims (sub, exp, iat)
- Validated using public keys from Cognito JWKS endpoint
- Transmitted via Authorization header: `Bearer <token>`

**Refresh Tokens:**
- 30-day lifetime for session persistence
- Stored in localStorage with automatic cleanup
- Used only for token refresh, never for API access
- Automatically rotated on refresh

**localStorage Security Strategy:**
```typescript
// Token storage in localStorage with security considerations
localStorage.setItem('ce_access_token', accessToken);
localStorage.setItem('ce_refresh_token', refreshToken);
localStorage.setItem('ce_token_expiry', (Date.now() + expiresIn * 1000).toString());

// Automatic cleanup on page load
const tokenExpiry = localStorage.getItem('ce_token_expiry');
if (tokenExpiry && Date.now() > parseInt(tokenExpiry)) {
    localStorage.removeItem('ce_access_token');
    localStorage.removeItem('ce_refresh_token');
    localStorage.removeItem('ce_token_expiry');
}
```

**XSS Protection Measures:**
- Strong Content Security Policy (CSP) headers
- Input sanitization and output encoding
- X-XSS-Protection and X-Content-Type-Options headers
- Regular security audits and dependency updates

## Implementation Details

### Backend Integration

#### Express.js Middleware (Compiler Explorer Server)

```typescript
import { CognitoJwtVerifier } from 'aws-jwt-verify';
import { PropertyGetter } from '../properties.interfaces.js';

// Create auth middleware factory function
export function createAuthMiddleware(awsProps: PropertyGetter) {
    // Configuration from CE properties system (no secrets in code)
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

// Usage in main application setup:
// const authMiddleware = createAuthMiddleware(awsProps);
// app.use('/api/*', authMiddleware);

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

#### Token Refresh Strategy

Since client secrets must remain in the Lambda auth service, token refresh can be handled in two ways:

**Option 1: Frontend-direct refresh** (Recommended)
The frontend calls the Lambda auth service directly for token refresh:

```typescript
// Frontend calls Lambda directly for refresh
const response = await fetch('https://api.compiler-explorer.com/auth/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh_token: refreshToken })
});
```

**Option 2: Proxy endpoint** (If needed)
If routing through the main server is preferred:

```typescript
export function createTokenRefreshEndpoint(awsProps: PropertyGetter) {
    const authServiceUrl = awsProps('authServiceUrl', 'https://api.compiler-explorer.com');

    return async (req, res) => {
        const { refresh_token } = req.body;

        if (!refresh_token) {
            return res.status(401).json({ error: 'No refresh token provided' });
        }

        try {
            // Proxy to Lambda auth service (no secrets in this server)
            const response = await fetch(`${authServiceUrl}/auth/refresh`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token })
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

### Frontend Integration (Pug Templates)

#### Navigation Bar Enhancement

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

#### TypeScript Client Implementation

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
            const refreshToken = params.get('refresh_token');
            const expiresIn = parseInt(params.get('expires_in') || '1800');

            // Store tokens in localStorage
            localStorage.setItem('ce_access_token', this.accessToken);
            localStorage.setItem('ce_refresh_token', refreshToken);

            // Set expiry
            this.tokenExpiry = Date.now() + (expiresIn * 1000);
            localStorage.setItem('ce_token_expiry', this.tokenExpiry.toString());

            // Clean URL
            window.history.replaceState({}, document.title, window.location.pathname);

            // Update UI
            await this.updateAuthUI();
        } else {
            // Try to get existing token from localStorage
            await this.loadFromStorage();
        }
    }

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
        localStorage.removeItem('ce_refresh_token');
        localStorage.removeItem('ce_token_expiry');

        // Update UI
        this.updateAuthUI();
    }

    async getValidToken(): Promise<string | null> {
        if (this.accessToken && Date.now() < this.tokenExpiry) {
            return this.accessToken;
        }

        return await this.refreshTokenIfNeeded();
    }

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
        const refreshToken = localStorage.getItem('ce_refresh_token');

        if (!refreshToken) {
            return null;
        }

        try {
            const response = await fetch('https://api.compiler-explorer.com/auth/refresh', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ refresh_token: refreshToken })
            });

            if (!response.ok) {
                // Clear invalid tokens
                this.signOut();
                return null;
            }

            const tokens = await response.json();

            // Update tokens
            this.accessToken = tokens.access_token;
            this.tokenExpiry = Date.now() + (tokens.expires_in * 1000);

            // Store new tokens
            localStorage.setItem('ce_access_token', this.accessToken);
            localStorage.setItem('ce_refresh_token', tokens.refresh_token);
            localStorage.setItem('ce_token_expiry', this.tokenExpiry.toString());

            await this.updateAuthUI();
            return this.accessToken;

        } catch (error) {
            console.error('Token refresh failed:', error);
            this.signOut();
            return null;
        }
    }

    private async updateAuthUI(): Promise<void> {
        const signInDropdown = document.getElementById('auth-sign-in');
        const userDropdown = document.getElementById('auth-dropdown');

        if (this.accessToken) {
            // Get user info from token
            const payload = JSON.parse(atob(this.accessToken.split('.')[1]));

            // Update UI elements
            document.getElementById('auth-username').textContent = payload.username || 'User';
            document.getElementById('auth-user-email').textContent = payload.email || '';

            // Show/hide dropdowns
            signInDropdown?.classList.add('d-none');
            userDropdown?.classList.remove('d-none');
        } else {
            // Show sign in, hide user dropdown
            signInDropdown?.classList.remove('d-none');
            userDropdown?.classList.add('d-none');
        }
    }
}
```

#### Integration with Compilation API

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

### Auth Lambda Service

#### Lambda Function Implementation

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
    else:
        return {
            'statusCode': 404,
            'body': json.dumps({'error': 'Not found'})
        }

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

        # Redirect back with tokens as URL fragments
        redirect_url = f"{return_to}#access_token={tokens['access_token']}&refresh_token={tokens['refresh_token']}&expires_in={tokens['expires_in']}"

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

### WAF Configuration

#### Enhanced Rate Limiting Rules

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

### Cognito User Pool Configuration

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

  # OAuth configuration
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

### Identity Provider Configuration

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

# Lambda permission for API Gateway
resource "aws_lambda_permission" "auth_service_apigw" {
  statement_id  = "AllowExecutionFromAPIGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.auth_service.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.auth_service.execution_arn}/*/*"
}
```

## Deployment Guide

### Phase 1: Infrastructure Setup

1. **Create OAuth Applications**
   ```bash
   # GitHub OAuth App
   # - Go to https://github.com/settings/applications/new
   # - Application name: "Compiler Explorer"
   # - Homepage URL: https://godbolt.org
   # - Authorization callback URL: https://[cognito-domain]/oauth2/idpresponse

   # Google OAuth App
   # - Go to https://console.developers.google.com/
   # - Create new project or select existing
   # - Enable Google+ API
   # - Create OAuth 2.0 client ID
   # - Authorized redirect URIs: https://[cognito-domain]/oauth2/idpresponse

   # Apple Sign-In
   # - Go to https://developer.apple.com/account/resources/identifiers/list/serviceId
   # - Create new Services ID
   # - Configure return URLs: https://[cognito-domain]/oauth2/idpresponse
   ```

2. **Deploy Infrastructure**
   ```bash
   cd terraform/

   # Set variables
   export TF_VAR_github_oauth_client_id="your_github_client_id"
   export TF_VAR_github_oauth_client_secret="your_github_client_secret"
   export TF_VAR_google_oauth_client_id="your_google_client_id"
   export TF_VAR_google_oauth_client_secret="your_google_client_secret"

   # Deploy
   terraform init
   terraform plan
   terraform apply
   ```

3. **Configure DNS**
   ```bash
   # Add CNAME record for auth service
   # auth.compiler-explorer.com -> [api-gateway-url]
   ```

### Phase 2: Backend Integration

1. **Update Environment Variables**
   ```bash
   # Add to compiler-explorer server environment
   export COGNITO_USER_POOL_ID="us-east-1_XXXXXXXXX"
   export COGNITO_CLIENT_ID="your_client_id"
   export COGNITO_DOMAIN="auth-ce-12345678.auth.us-east-1.amazoncognito.com"
   ```

2. **Install Dependencies**
   ```bash
   npm install aws-jwt-verify
   ```

3. **Deploy Backend Changes**
   ```bash
   # Test locally first
   npm run test
   npm run lint

   # Deploy to staging
   ./deploy.sh staging

   # Verify auth endpoints work
   curl -X POST https://staging.godbolt.org/api/auth/refresh
   ```

### Phase 3: Frontend Integration

1. **Add TypeScript Auth Client**
   ```bash
   # Copy auth-client.ts to static/auth/
   # Update main.ts to initialize auth client
   ```

2. **Update Pug Templates**
   ```bash
   # Update views/index.pug with auth navigation
   # Test templates render correctly
   ```

3. **Test Frontend Flow**
   ```bash
   npm run dev
   # Manual testing:
   # 1. Click "Sign In with GitHub"
   # 2. Complete OAuth flow
   # 3. Verify token storage
   # 4. Test API calls with token
   # 5. Test token refresh
   # 6. Test sign out
   ```

### Phase 4: WAF Configuration

1. **Deploy WAF Rules**
   ```bash
   cd terraform/
   terraform apply -target=aws_wafv2_web_acl.compiler_explorer_enhanced
   ```

2. **Test Rate Limiting**
   ```bash
   # Test anonymous rate limiting
   for i in {1..110}; do curl -s https://godbolt.org/api/compile; done

   # Test authenticated rate limiting
   for i in {1..1010}; do curl -s -H "Authorization: Bearer $TOKEN" https://godbolt.org/api/compile; done
   ```

### Phase 5: Production Deployment

1. **Gradual Rollout**
   ```bash
   # Deploy to beta environment first
   ./deploy.sh beta

   # Monitor for 24 hours
   # Check CloudWatch metrics
   # Verify no increase in error rates

   # Deploy to production
   ./deploy.sh production
   ```

2. **Post-Deployment Verification**
   ```bash
   # Verify all auth flows work
   # Check rate limiting is working
   # Monitor CloudWatch dashboards
   # Test rollback procedures
   ```

## Testing Strategy

### Unit Tests

#### Backend Tests
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

#### Frontend Tests
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

### Integration Tests

#### Auth Flow Tests
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

#### Rate Limiting Tests
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

### Load Testing

```bash
# Load test auth endpoints
artillery run auth-load-test.yml

# Test compilation API with auth
artillery run compile-auth-load-test.yml
```

## Security Considerations

### Token Security

1. **Access Token Lifetime**: 30 minutes balances security vs usability
2. **localStorage Security**: Protected by strong CSP headers and XSS prevention
3. **Token Validation**: JWT signature verification without storing secrets
4. **Token Rotation**: Refresh tokens rotated on each use
5. **Automatic Cleanup**: Expired tokens automatically removed from localStorage

### XSS Protection Strategy

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

### CORS Configuration

```typescript
// Enhanced CORS configuration
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

## Monitoring and Alerting

### CloudWatch Metrics

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

## GDPR Compliance

### Data Processing Overview

**Data Collected:**
- Email address (for account linking)
- Username (from OAuth provider)
- Authentication timestamps
- Provider information (GitHub, Google, Apple)
- Tokens stored in browser localStorage (user-controlled)

**Data NOT Collected:**
- Compilation code (remains anonymous)
- IP addresses (beyond AWS standard logs)
- Browsing history
- Personal preferences (unless user explicitly saves)

**localStorage Considerations:**
- Tokens stored locally in user's browser
- User has full control (can clear browser data)
- No server-side session tracking
- Automatic cleanup of expired tokens

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

**Required additions:**
1. **Optional Authentication**: Clearly state that authentication is optional and anonymous usage continues unchanged
2. **Data Collection**: Describe what data is collected for authenticated users (email, username, auth timestamps)
3. **Data Usage**: Explain how data is used (account linking, rate limiting, user identification)
4. **localStorage Usage**: Mention that authentication tokens are stored in browser localStorage under user control
5. **Data Retention**: 30-day refresh token lifetime, automatic cleanup of expired tokens
6. **User Rights**: Data export and account deletion capabilities
7. **Third-party Providers**: OAuth integration with GitHub, Google, and Apple
8. **No Tracking**: Emphasize that compilation code remains anonymous and no additional tracking is introduced


## Performance Considerations

### Latency Impact

**Token Validation:**
- JWT verification is performed for each authenticated request
- JWKS cache: Updated every 5 minutes by aws-jwt-verify library
- Measure actual performance impact in the CE environment

**Rate Limiting:**
- WAF evaluation: <1ms per request
- No impact on compilation performance

### Throughput Impact

**Anonymous Users:**
- No change in throughput
- Same compilation limits

**Authenticated Users:**
- 10x higher rate limits
- Improved user experience
- No additional server load


## Future Enhancements

### Planned Features

1. **User Preferences Storage**
   - Theme preferences
   - Compiler defaults
   - Layout preferences

2. **Compilation History**
   - Optional compilation history
   - Search and filter capabilities
   - Export functionality

3. **Link Ownership**
   - Associate short links with users
   - Manage user-created links
   - Link analytics

4. **Advanced Rate Limiting**
   - Per-user rate limits
   - Supporter tier benefits
   - Usage analytics

### Technical Improvements

1. **Enhanced Security**
   - Rotate JWT signing keys
   - Implement PKCE for OAuth
   - Add 2FA support

2. **Performance Optimizations**
   - **JWT Token Caching**: Only consider if performance monitoring shows high CPU usage from token validation. Requires Redis for multi-server deployment and adds complexity around cache invalidation vs JWT expiration.
   - CDN for auth assets

3. **Operational Improvements**
   - Automated testing
   - Enhanced monitoring

## Conclusion

This authentication system provides:

✅ **Simple Integration**: Minimal changes to existing codebase
✅ **Security First**: No secrets in web application code
✅ **Optional Usage**: Full anonymous functionality preserved
✅ **Developer Focus**: GitHub, Google, Apple OAuth providers
✅ **Scalable Rate Limiting**: WAF-based enforcement
✅ **Account Linking**: Unified user experience across providers
✅ **GDPR Compliant**: User data export and deletion
✅ **Monitoring Ready**: Comprehensive metrics and alerts
✅ **Implementation Ready**: Clear technical guidance for both repositories

The implementation can be done incrementally:
- Infrastructure setup (Cognito, Lambda, WAF)
- Backend integration (auth middleware, token validation)
- Frontend integration (Pug templates, TypeScript client)
- Security hardening and testing

This design enables both repositories to work with clear guidance and minimal complexity while maintaining the security and scalability requirements of Compiler Explorer.
