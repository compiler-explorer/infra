# Design of an authentication setup.

For ease of implementation, after researching a few alternatives and talking to some people with experience, I decided to see what we could do with Amazon's own Cognito.

The first step is to just get authentication, so we know when a user is logged in, and then we can e.g. store preferences for that user and give higher rate limits for logged-in users.

Whatever we do, we would need to update the privacy policy accordingly.

### Open questions

-   our subdomains and our beta/staging etc make configuration tricky. Can hardcode "beta" and "staging" etc but is there a better way?

### Integrating with Existing Request Flow

```typescript
// Extends current Express.js API endpoints at /api/*
import { CognitoJwtVerifier } from "aws-jwt-verify";
import { signInWithRedirect, getCurrentUser } from "aws-amplify/auth";

// Neither of these are sensitive so could be public.
const cognitoUserPoolId = /* fetch from SSM using awsProps */;
const cognitoClientId = /* ditto */;
const verifier = CognitoJwtVerifier.create({ userPoolId, tokenUse: "access", clientId });

// Add to existing Express middleware
app.use("/api/compile", async (req, res, next) => {
    const authHeader = req.headers.authorization;
    let userId: string | null = null;

    // Optional authentication - maintains current anonymous functionality
    if (authHeader?.startsWith("Bearer ")) {
        try {
            const token = authHeader.split(" ")[1];
            const payload = await verifier.verify(token);
            userId = payload.sub;
            req.user = { id: userId, tier: "authenticated" };
        } catch {
            // Invalid token, continue as anonymous (your current behavior)
            req.user = { tier: "anonymous" };
        }
    } else {
        req.user = { tier: "anonymous" };
    }

    next();
});

// EXAMPLE ONLY DO NOT IMPLEMENT
// Existing compilation logic with optional user features
app.post("/api/compile", async (req, res) => {
    const { code, language, options } = req.body;

    const result = await runCompilation(code, language, options);

    // EXAMPLE: Optional features for authenticated users
    if (req.user?.id) {
        // Save compilation history...or stats per user or ... whatever we decide is OK
        // Privacy policy would need to be updated as appropriate.
        await saveCompilationHistory(req.user.id, { code, language, result });
        result.saved = true;
    }

    res.json(result);
});
```

### Frontend: Path-Based Environment Support

```typescript
const cognitoUserPoolId = /* fetch compilerExplorerOptions (exposed from server) */;
const cognitoClientId = /* ditto */;
const oauthDomain = /* ditto; e.g. 'auth.godbolt.org' */
Amplify.configure({
    Auth: {
        Cognito: {
            userPoolId: cognitoUserPoolId,
            userPoolClientId: cognitoClientId,
            loginWith: {
                oauth: {
                    domain: oauthDomain,
                    // Dynamic callback URLs based on current environment
                    // TODO this needs careful thought to work with subdomains _and_ things like godbolt.org/beta/...
                    redirectSignIn: [`${window.location.origin}/auth/callback`],
                    redirectSignOut: [`${window.location.origin}/`],
                    responseType: "code",
                    scopes: ["email", "openid", "profile"],
                },
            },
        },
    },
});

// Environment-aware authentication
const getAuthCallbackUrl = () => {
    const currentPath = window.location.pathname;
    const baseUrl = window.location.origin;

    // Handle path-based environments
    // TODO ensure this actually works, see oauth config above
    if (currentPath.startsWith("/beta/")) {
        return `${baseUrl}/beta/auth/callback`;
    } else if (currentPath.startsWith("/staging/")) {
        return `${baseUrl}/staging/auth/callback`;
    } else {
        return `${baseUrl}/auth/callback`;
    }
};

// TODO - this was sketched in Claude which assumed react.js. We _do not_ have react.
// we need to convert this to our `pug` format as appropriate, and style the buttons etc.
// but this is a start.
export const CompilerExplorerAuthComponent = () => {
    const [user, setUser] = useState(null);
    const [linkedProviders, setLinkedProviders] = useState([]);

    const signInWithProvider = async (provider: string) => {
        // This works whether user is on:
        // - godbolt.org
        // - godbolt.org/beta
        // - cpp.godbolt.org
        // - rust.godbolt.org
        // - compiler-explorer.com
        // etc.
        await signInWithRedirect({
            provider,
            customState: window.location.pathname, // Preserve current path
        });
    };

    return (
        <div className="ce-auth-component">
            {user ? (
                <div className="user-profile">
                    <span>Welcome, {user.username}!</span>
                    <span className="user-email">{user.attributes?.email}</span>

                    {/* Show which providers are linked */}
                    <div className="linked-providers">
                        {linkedProviders.map((provider) => (
                            <span key={provider} className="provider-badge">
                                {provider} ✓
                            </span>
                        ))}
                    </div>
                </div>
            ) : (
                <div className="auth-options">
                    <button onClick={() => signInWithProvider("GitHub")}>
                        Sign in with GitHub
                    </button>
                    <button onClick={() => signInWithProvider("Google")}>
                        Sign in with Google
                    </button>
                    <button
                        onClick={() => signInWithProvider("SignInWithApple")}
                    >
                        Sign in with Apple
                    </button>
                </div>
            )}
        </div>
    );
};
```

## Implementation Sketch

### GitHub OIDC Proxy

1. Deploy GitHub OIDC wrapper Lambda function
2. Test GitHub OAuth flow extensively
3. Ensure GitHub username mapping works correctly
4. Verify GitHub email privacy settings are handled

### Google & Apple

1. Add Google provider (native Cognito support)
2. Add Apple provider for iOS/Mac developers
3. Test multi-provider scenarios
4. Implement provider preference storage

### Features

In no particular order:

-   Higher rate limits for authenticated users
-   Stats for authenticated users - for the users themselves _and_ for us?
-   Adding "owner ID" to link creation
-   List "links created by me" and admin therein
-   GDPR compliance stuff like "forget me"
-   TODO: not specified in this document, but things like saving user preferences etc

### Admin features

-   Stats, MAUs etc
-   Reset user password? etc
-   Anything else ? We can do a lot with ad hoc AWS tooling and console

### Terraform Implementation

```terraform
# Cognito User Pool with automatic account linking
resource "aws_cognito_user_pool" "compiler_explorer" {
  name = "compiler-explorer-users"

  # Enable email-based account linking
  alias_attributes = ["email"]

  # Ensure users can't create duplicate accounts with same email
  username_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  # Email schema ensures linking works properly
  schema {
    attribute_data_type = "String"
    name               = "email"
    required           = true
    mutable            = true
  }

  # Developer-focused identity providers only
  supported_identity_providers = ["COGNITO", "GitHub", "Google", "SignInWithApple"]
}

# Client configuration
resource "aws_cognito_user_pool_client" "compiler_explorer_client" {
  name         = "compiler-explorer-web"
  user_pool_id = aws_cognito_user_pool.compiler_explorer.id

  # Real Compiler Explorer domains and path-based environments
  # TODO - this needs work to handle e.g. godbo.lt and anything else here
  callback_urls = [
    "https://godbolt.org/auth/callback",
    "https://godbolt.org/beta/auth/callback",
    "https://godbolt.org/staging/auth/callback",
    "https://compiler-explorer.com/auth/callback",
    "https://compiler-explorer.com/beta/auth/callback",
    "https://compiler-explorer.com/staging/auth/callback",
    # Add wildcard subdomain support for language-specific instances
    "https://*.godbolt.org/auth/callback",
    # Local development
    "http://localhost:10240/auth/callback"
  ]

  # TODO: as above
  logout_urls = [
    "https://godbolt.org/",
    "https://godbolt.org/beta/",
    "https://godbolt.org/staging/",
    "https://compiler-explorer.com/",
    "https://compiler-explorer.com/beta/",
    "https://compiler-explorer.com/staging/",
    "https://*.godbolt.org/",
    "http://localhost:10240/"
  ]

  supported_identity_providers = ["GitHub", "Google", "SignInWithApple"]
  oauth_flows = ["code"]
  oauth_scopes = ["email", "openid", "profile"]
  read_attributes  = ["email", "email_verified", "identities"]
  write_attributes = ["email"]

  # Prevent duplicate account errors
  prevent_user_existence_errors = "ENABLED"
}

# GitHub OAuth App Integration (see separate sectin)
resource "aws_cognito_identity_provider" "github_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "GitHub"
  provider_type = "OIDC"

  provider_details = {
    client_id     = var.github_oauth_client_id
    client_secret = var.github_oauth_client_secret

    # GitHub OIDC wrapper endpoints (see section below and adjust as appropriate depending on solution)
    oidc_issuer      = aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]
    authorize_scopes = "openid email profile"

    # Custom endpoints since GitHub doesn't natively support OIDC
    authorize_url    = "https://github.com/login/oauth/authorize"
    token_url        = "https://${aws_api_gateway_rest_api.github_oidc_proxy.id}.execute-api.${var.aws_region}.amazonaws.com/prod/token"
    attributes_url   = "https://${aws_api_gateway_rest_api.github_oidc_proxy.id}.execute-api.${var.aws_region}.amazonaws.com/prod/userinfo"
    jwks_uri         = "https://${aws_api_gateway_rest_api.github_oidc_proxy.id}.execute-api.${var.aws_region}.amazonaws.com/prod/.well-known/jwks.json"
  }

  # Map email for account linking
  attribute_mapping = {
    email              = "email"           # Links accounts by email
    username           = "login"           # GitHub username for display
    preferred_username = "login"
    name               = "name"
    email_verified     = "email_verified"  # GitHub emails are always verified
  }
}

# Google provider
resource "aws_cognito_identity_provider" "google_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "Google"
  provider_type = "Google"

  provider_details = {
    client_id        = var.google_oauth_client_id
    client_secret    = var.google_oauth_client_secret
    authorize_scopes = "email openid profile"
  }

  # Same email mapping ensures account linking
  attribute_mapping = {
    email          = "email"           # Same field = automatic linking
    username       = "sub"
    name           = "name"
    email_verified = "email_verified"  # Google emails are always verified
  }
}

# Apple provider
resource "aws_cognito_identity_provider" "apple_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "SignInWithApple"
  provider_type = "SignInWithApple"

  provider_details = {
    client_id    = var.apple_service_id
    team_id      = var.apple_team_id
    key_id       = var.apple_key_id
    private_key  = var.apple_private_key
    authorize_scopes = "email name"
  }

  # Apple email mapping (may be relay email like @privaterelay.appleid.com)
  attribute_mapping = {
    email    = "email"
    username = "sub"
  }
}
```

### GitHub OIDC Wrapper Implementation

GitHub only provides OAuth 2.0 endpoints, while AWS Cognito requires OpenID Connect (OIDC) providers. This creates an incompatibility that prevents direct integration. The missing OIDC endpoints that Cognito expects are:

-   `/.well-known/openid_configuration` (discovery document)
-   `/userinfo` (user profile endpoint)
-   `/.well-known/jwks.json` (JSON Web Key Set for token verification)

The community-maintained `github-cognito-openid-wrapper` by TimothyJones solves this by providing an OIDC translation layer. It wraps GitHub's OAuth API with the OIDC endpoints that Cognito requires.

We can deploy this using cloudformation directly:

```terraform
# Deploy the GitHub OIDC wrapper using their battle-tested CloudFormation template
resource "aws_cloudformation_stack" "github_oidc_wrapper" {
  name         = "github-oidc-wrapper"
  template_url = "https://github.com/TimothyJones/github-cognito-openid-wrapper/releases/latest/download/template.yaml"

  parameters = {
    GitHubClientId     = var.github_oauth_client_id
    GitHubClientSecret = var.github_oauth_client_secret
    CognitoDomain      = aws_cognito_user_pool_domain.compiler_explorer.domain
  }
}

# Reference the deployed API Gateway in your Cognito provider
resource "aws_cognito_identity_provider" "github_provider" {
  user_pool_id  = aws_cognito_user_pool.compiler_explorer.id
  provider_name = "GitHub"
  provider_type = "OIDC"

  provider_details = {
    client_id     = var.github_oauth_client_id
    client_secret = var.github_oauth_client_secret

    # Use the API Gateway URL from the CloudFormation stack
    oidc_issuer      = aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]
    authorize_scopes = "openid email profile"

    # Custom endpoints - GitHub OAuth + wrapper-provided OIDC endpoints
    authorize_url    = "https://github.com/login/oauth/authorize"
    token_url        = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/token"
    attributes_url   = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/userinfo"
    jwks_uri         = "${aws_cloudformation_stack.github_oidc_wrapper.outputs["ApiGatewayUrl"]}/.well-known/jwks.json"
  }

  attribute_mapping = {
    email              = "email"
    username           = "login"
    preferred_username = "login"
    name               = "name"
    email_verified     = "email_verified"
  }
}
```

#### Setup Steps

**Create GitHub OAuth App** at https://github.com/settings/applications/new

    - Application name: "Compiler Explorer"
    - Homepage URL: `https://godbolt.org`
    - Authorization callback URL: `https://your-cognito-domain.auth.region.amazoncognito.com/oauth2/idpresponse`

### Account Linking Behavior Examples

```typescript
// Example: User Journey with Account Linking

// Day 1: User signs up with GitHub
// POST /oauth2/authorize with provider=GitHub
// Result: Creates user with ID "abc123" and email "developer@example.com"

const user1 = {
    sub: "abc123",
    email: "developer@example.com",
    username: "githubuser",
    identities: [{ providerName: "GitHub", userId: "github_456789" }],
};

// Day 2: Same user clicks "Sign in with Google"
// Cognito detects email "developer@example.com" already exists
// Result: Links Google provider to SAME user ID "abc123"

const sameUser = {
    sub: "abc123", // SAME ID!
    email: "developer@example.com",
    username: "githubuser", // Preserves original username
    identities: [
        { providerName: "GitHub", userId: "github_456789" },
        { providerName: "Google", userId: "google_987654" }, // Added, not replaced
    ],
};

// User compilation history, settings, supporter status - all preserved!
```

### Frontend: Seamless Multi-Provider Experience

```typescript
// Enhanced auth component showing linked providers
export const UnifiedAuthComponent = () => {
    const [user, setUser] = useState(null);
    const [linkedProviders, setLinkedProviders] = useState([]);

    const updateUser = async () => {
        try {
            const currentUser = await getCurrentUser();
            setUser(currentUser);

            // Show user which providers they've linked
            const identities = currentUser.attributes?.identities || [];
            setLinkedProviders(identities.map((id) => id.providerName));
        } catch {
            setUser(null);
            setLinkedProviders([]);
        }
    };

    const signInWithAnyProvider = async (provider: string) => {
        // User can click any provider - Cognito handles the linking
        await signInWithRedirect({ provider });
    };

    return (
        <div>
            {user ? (
                <div className="user-profile">
                    <h3>Welcome, {user.username}!</h3>
                    <p>Email: {user.attributes?.email}</p>

                    {/* Show linked providers */}
                    <div className="linked-providers">
                        <span>Sign in with: </span>
                        {linkedProviders.map((provider) => (
                            <span key={provider} className="provider-badge">
                                {provider} ✓
                            </span>
                        ))}
                    </div>

                    {/* Allow linking additional providers */}
                    <div className="link-providers">
                        {!linkedProviders.includes("GitHub") && (
                            <button
                                onClick={() => signInWithAnyProvider("GitHub")}
                            >
                                Link GitHub Account
                            </button>
                        )}
                        {!linkedProviders.includes("Google") && (
                            <button
                                onClick={() => signInWithAnyProvider("Google")}
                            >
                                Link Google Account
                            </button>
                        )}
                    </div>
                </div>
            ) : (
                <div className="auth-options">
                    <h3>Sign in to save your compilation history</h3>
                    <p>Use any provider - we'll link them to one account</p>

                    <button onClick={() => signInWithAnyProvider("GitHub")}>
                        <GitHubIcon /> Sign in with GitHub
                    </button>
                    <button onClick={() => signInWithAnyProvider("Google")}>
                        <GoogleIcon /> Sign in with Google
                    </button>
                    <button
                        onClick={() => signInWithAnyProvider("SignInWithApple")}
                    >
                        <AppleIcon /> Sign in with Apple
                    </button>
                </div>
            )}
        </div>
    );
};
```

### Backend: Unified User Handling

```typescript
// Your compilation API works with unified user ID regardless of provider
app.post("/api/compile", async (req, res) => {
    const { code, language, options } = req.body;

    // Get unified user ID (same regardless of which provider they used today)
    const userId = req.user?.id; // Always the same Cognito sub

    const result = await runCompilation(code, language, options);

    if (userId) {
        // Save to compilation history using consistent user ID
        await saveCompilationHistory(userId, { code, language, result });

        // User preferences persist across all provider logins
        const preferences = await getUserPreferences(userId);
        result.preferences = preferences;
        result.saved = true;
    }

    res.json(result);
});

// User settings/preferences work seamlessly
app.get("/api/user/history", async (req, res) => {
    const userId = req.user?.id;

    // Returns ALL compilation history regardless of which provider
    // user has used to sign in over time
    const history = await getCompilationHistory(userId);
    res.json(history);
});
```

### Enhanced WAF Configuration for CE's Existing Setup

TODO: check this. I'm pretty sure the priority are the wrong way around for these.

```terraform
# Enhanced WAF rules extending your existing "very simple, very high rate limits per IP"
resource "aws_wafv2_web_acl" "compiler_explorer_enhanced" {
  name  = "compiler-explorer-enhanced"
  scope = "CLOUDFRONT"  # Matches your current CloudFront setup

  default_action {
    allow {}
  }

  # Anonymous rate limiting (stricter than your current "very high" limits)
  rule {
    name     = "AnonymousRateLimit"
    priority = 1

    statement {
      rate_based_statement {
        limit              = 100  # 100 requests per 5-minute window per IP
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

  # Authenticated users get much higher limits
  rule {
    name     = "AuthenticatedRateLimit"
    priority = 2

    statement {
      rate_based_statement {
        limit              = 1000  # 10x higher for authenticated users
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

  # EXAMPLE ONLY: Supporter tier with even higher limits
  # Currently no plans to do this as we don't offer "freemium" style service
  rule {
    name     = "SupporterRateLimit"
    priority = 3

    statement {
      rate_based_statement {
        limit              = 5000  # Very high limits for supporters
        aggregate_key_type = "IP"

        # Apply to requests with supporter tier in JWT claims
        scope_down_statement {
          byte_match_statement {
            search_string = "supporter"
            field_to_match {
              single_header {
                name = "x-user-tier"  # Custom header set by your backend
              }
            }
            text_transformation {
              priority = 0
              type     = "LOWERCASE"
            }
            positional_constraint = "CONTAINS"
          }
        }
      }
    }

    action {
      block {}
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name               = "SupporterRateLimit"
      sampled_requests_enabled  = true
    }
  }
}

# Associate enhanced WAF with your existing CloudFront distribution
resource "aws_wafv2_web_acl_association" "compiler_explorer_cloudfront" {
  resource_arn = aws_cloudfront_distribution.compiler_explorer.arn
  web_acl_arn  = aws_wafv2_web_acl.compiler_explorer_enhanced.arn
}
```

### Backend: Simple Token Validation (WAF Handles Rate Limiting)

TODO! combine this with the section at the top of the document and delete this.

```typescript
// Your Express.js middleware - rate limiting handled by WAF at edge
app.use("/api/compile", async (req, res, next) => {
    const authHeader = req.headers.authorization;
    let userId: string | null = null;
    let userTier: string = "anonymous";

    // Optional authentication - WAF already handled rate limiting
    if (authHeader?.startsWith("Bearer ")) {
        try {
            const token = authHeader.split(" ")[1];
            const payload = await verifier.verify(token);
            userId = payload.sub;
            // Set custom header for supporter tier detection (EXAMPLE)
            userTier = payload.tier || "authenticated";
            res.set("X-User-Tier", userTier);

            req.user = { id: userId, tier: userTier };
        } catch {
            // Invalid token: need to stop this. WAF doesn't check tokens are valid,
            // so we would enable subverting rate limits if we didn't reject bad tokens
            // here.
            res.status(401).json({
                error: 'Invalid authentication token',
                message: 'Please sign in again'
            });
            return;
        }
    } else {
        req.user = { tier: "anonymous" };
    }

    next();
});
```

## GDPR Compliance

Example of things we might need to consider

```typescript
class CEGDPRService {
    // Data export
    async exportUserData(userId: string): Promise<string> {
        const compilationHistory = await this.getUserCompilations(userId);

        const exportData = {
            profile: {
                userId,
                email: await this.getUserEmail(userId),
                createdAt: await this.getUserCreatedDate(userId),
            },
            // EXAMPLE ONLY WE DO NOT STORE COMPILATION HISTORY
            compilations: compilationHistory.map((c) => ({
                language: c.language,
                timestamp: c.timestamp,
                // Code not included by default for privacy
            })),
            // END EXAMPLE
            exportedAt: new Date().toISOString(),
            format: "json",
        };

        // EXAMPLE ONLY NEEDS MORE FLESHING OUT
        // Store export in your existing S3 bucket with lifecycle policy
        // Would need a random unguessable name here
        const exportKey = `user-exports/${userId}/${Date.now()}.json`;
        await this.s3
            .putObject({
                Bucket: process.env.COMPILATION_CACHE_BUCKET,
                Key: exportKey,
                Body: JSON.stringify(exportData),
                Tagging: "type=gdpr-export&retention=7days", // Auto-cleanup
            })
            .promise();

        return `https://compiler-explorer.com/data-export/${exportKey}`;
    }

    // User data deletion
    async deleteUserData(userId: string): Promise<void> {
        // Delete compilation history from S3 EXAMPLE ONLY WE DON'T ACTUALLY DO THIS
        await this.deleteS3ObjectsWithPrefix(`user-history/${userId}/`);

        // Remove user from Cognito
        await this.cognitoIdentityProvider
            .adminDeleteUser({
                UserPoolId: process.env.COGNITO_USER_POOL_ID,
                Username: userId,
            })
            .promise();

        // TODO consider deleting all links the user created? Need to think about that...

        console.log(`GDPR deletion completed for user ${userId}`);
    }

    // As we don't track anonymous users, GDPR is simplified:
    // - No consent management needed for anonymous compilation
    // - Only authenticated users have data to manage
    // - Clear consent through authentication opt-in process
}
```

## Security Best Practices Implementation

TODO thorough review needed here. VERY IMPORTANT

### Production-Ready Security Configuration

```typescript
// Security headers and CORS for compiler service
app.use(
    helmet({
        contentSecurityPolicy: {
            directives: {
                defaultSrc: ["'self'"],
                scriptSrc: ["'self'", "'unsafe-inline'"], // Required for Monaco editor
                styleSrc: ["'self'", "'unsafe-inline'"],
                imgSrc: ["'self'", "data:", "https:"],
                connectSrc: [
                    "'self'",
                    "https://api.github.com",
                    "https://accounts.google.com",
                ],
            },
        },
        hsts: {
            maxAge: 31536000,
            includeSubDomains: true,
            preload: true,
        },
    })
);

// CORS configuration for API
app.use(
    cors({
        origin: process.env.ALLOWED_ORIGINS?.split(",") || [
            "https://compiler-explorer.com",
        ],
        credentials: true,
        maxAge: 86400, // 24 hours
    })
);

```


### API Integration Pattern

TODO review and deduplicate.

```typescript
// API client with automatic token management
class CompilerAPIClient {
    private token: string | null = null;
    private tokenExpiry: number = 0;

    async compile(code: string, language: string, options: CompileOptions) {
        const token = await this.getValidToken();

        const response = await fetch("/api/compile", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                Authorization: token ? `Bearer ${token}` : "",
                "X-Anonymous-Session": !token
                    ? this.getAnonymousSessionId()
                    : "",
            },
            body: JSON.stringify({ code, language, options }),
        });

        if (response.status === 429) {
            const retryAfter = response.headers.get("Retry-After");
            throw new RateLimitError(
                `Rate limit exceeded. Retry after ${retryAfter}s`
            );
        }

        return response.json();
    }

    private async getValidToken(): Promise<string | null> {
        if (!this.session) return null;

        if (this.token && Date.now() < this.tokenExpiry) {
            return this.token;
        }

        // Get fresh compiler token
        const response = await fetch("/api/auth/compiler-token", {
            method: "POST",
            credentials: "include",
        });

        if (response.ok) {
            const { token, expiresIn } = await response.json();
            this.token = token;
            this.tokenExpiry = Date.now() + expiresIn * 1000;
            return token;
        }

        return null;
    }
}
```

## Monitoring and Observability

```typescript
// Authentication metrics tracking
class AuthMetrics {
    private prometheus = new PrometheusClient();

    trackAuthEvent(event: AuthEvent) {
        this.prometheus
            .counter("auth_events_total", {
                provider: event.provider,
                status: event.status,
                user_tier: event.userTier,
            })
            .inc();

        if (event.duration) {
            this.prometheus
                .histogram("auth_duration_seconds", {
                    provider: event.provider,
                })
                .observe(event.duration / 1000);
        }
    }
}
```

## Conclusion

For Compiler Explorer's specific infrastructure and developer audience, AWS Cognito + Amplify provides:

-   **Perfect AWS integration**: Leverages your existing CloudFront, ALB, WAF, and S3 infrastructure
-   **Zero additional costs**: Free for up to 50,000 MAUs, well above your current scale
-   **Developer-focused OAuth**: GitHub as primary provider, with Google and Apple support
-   **Email-based account linking**: Users can sign in with any provider and maintain unified accounts
-   **Operational simplicity**: Uses your existing terraform patterns, SSM for secrets, CloudWatch for monitoring
-   **Minimal infrastructure changes**: Enhances existing setup rather than requiring new services
-   **Privacy by design**: No anonymous tracking, strictly opt-in authentication

This solution balances robust authentication capabilities with your operational preferences for AWS-native services, while providing the developer-centric OAuth experience your users expect. The 7-10 week implementation timeline accounts for deployment automation needs rather than authentication complexity, ensuring safe rollout across your multi-cluster infrastructure.
