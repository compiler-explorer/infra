# Compiler Explorer AWS Architecture - Blue-Green Deployment

## Blue-Green Architecture Diagram (Proposed)

```mermaid
graph TB
    subgraph "Internet"
        User[Users]
    end

    subgraph "CloudFront CDN"
        CF[CloudFront Distribution<br/>godbolt.org]
    end

    subgraph "Route 53"
        R53[Route 53 DNS<br/>godbolt.org]
    end

    subgraph "Application Load Balancer"
        ALB[ALB: GccExplorerApp<br/>Port 80/443]

        subgraph "Listener Rules"
            HTTPS[HTTPS Listener :443]
            HTTP[HTTP Listener :80]

            DefRule["Default Rule - Switchable"]
            BetaRule["'/beta*' - Switchable"]
            StagingRule["'/staging*' - Staging TG"]
            GPURule["'/gpu*' - GPU TG"]
            WinRule["'/win*' - Win TGs"]
            AArch64Rule["'/aarch64*' - AArch64 TGs"]
        end
    end

    subgraph "Production Blue-Green"
        subgraph "Prod Target Groups"
            TGProdBlue[TG: Prod-Blue<br/>Port 80]
            TGProdGreen[TG: Prod-Green<br/>Port 80]
            ProdSwitch{{"SSM: /prod/active-tg"}}
        end

        subgraph "Prod ASGs"
            ASGProdBlue[ASG: prod-blue<br/>Min: 0, Max: 24<br/>Spot Instances]
            ASGProdGreen[ASG: prod-green<br/>Min: 0, Max: 24<br/>Spot Instances]
        end

        subgraph "Prod EC2"
            EC2ProdBlue[EC2 Instances<br/>Version A<br/>m5/m6 family]
            EC2ProdGreen[EC2 Instances<br/>Version B<br/>m5/m6 family]
        end
    end

    subgraph "Beta Blue-Green"
        subgraph "Beta Target Groups"
            TGBetaBlue[TG: Beta-Blue<br/>Port 80]
            TGBetaGreen[TG: Beta-Green<br/>Port 80]
            BetaSwitch{{"SSM: /beta/active-tg"}}
        end

        subgraph "Beta ASGs"
            ASGBetaBlue[ASG: beta-blue<br/>Min: 0, Max: 4]
            ASGBetaGreen[ASG: beta-green<br/>Min: 0, Max: 4]
        end

        subgraph "Beta EC2"
            EC2BetaBlue[EC2 Instances<br/>Version A]
            EC2BetaGreen[EC2 Instances<br/>Version B]
        end
    end

    subgraph "Legacy Environments"
        TGStaging[TG: Staging<br/>Port 80]
        TGGpu[TG: GPU<br/>Port 80]
        TGWin[TG: WinProd/Staging<br/>Port 80]
        TGAArch[TG: AArch64Prod/Staging<br/>Port 80]

        ASGStaging[ASG: staging<br/>Rolling Deploy]
        ASGGpu[ASG: gpu<br/>Rolling Deploy]
        ASGWin[ASG: winprod-mixed<br/>Rolling Deploy]
        ASGAArch[ASG: aarch64prod-mixed<br/>Rolling Deploy]
    end

    subgraph "Storage"
        EFS[EFS: Compiler Cache<br/>Shared Storage]
        S3Logs[S3: compiler-explorer-logs]
        S3Static[S3: compiler-explorer]
    end

    %% Connections
    User --> CF
    User --> R53
    R53 --> CF
    CF --> ALB

    ALB --> HTTPS
    ALB --> HTTP

    %% Production Blue-Green Flow
    HTTPS --> DefRule
    DefRule -.->|Active| TGProdBlue
    DefRule -.->|Inactive| TGProdGreen
    ProdSwitch -->|Controls| DefRule

    TGProdBlue --> ASGProdBlue
    TGProdGreen --> ASGProdGreen

    ASGProdBlue --> EC2ProdBlue
    ASGProdGreen --> EC2ProdGreen

    %% Beta Blue-Green Flow
    HTTPS --> BetaRule
    BetaRule -.->|Active| TGBetaBlue
    BetaRule -.->|Inactive| TGBetaGreen
    BetaSwitch -->|Controls| BetaRule

    TGBetaBlue --> ASGBetaBlue
    TGBetaGreen --> ASGBetaGreen

    ASGBetaBlue --> EC2BetaBlue
    ASGBetaGreen --> EC2BetaGreen

    %% Legacy routing (unchanged)
    HTTPS --> StagingRule
    HTTPS --> GPURule
    HTTPS --> WinRule
    HTTPS --> AArch64Rule

    StagingRule --> TGStaging
    GPURule --> TGGpu
    WinRule --> TGWin
    AArch64Rule --> TGAArch

    TGStaging --> ASGStaging
    TGGpu --> ASGGpu
    TGWin --> ASGWin
    TGAArch --> ASGAArch

    %% Storage connections
    EC2ProdBlue --> EFS
    EC2ProdGreen --> EFS
    EC2BetaBlue --> EFS
    EC2BetaGreen --> EFS

    ALB --> S3Logs
    CF --> S3Static

    %% Styling
    classDef active fill:#90EE90,stroke:#228B22,stroke-width:3px
    classDef inactive fill:#FFB6C1,stroke:#DC143C,stroke-width:2px,stroke-dasharray: 5 5
    classDef switch fill:#87CEEB,stroke:#4682B4,stroke-width:2px

    class TGProdBlue,ASGProdBlue,EC2ProdBlue active
    class TGProdGreen,ASGProdGreen,EC2ProdGreen inactive
    class TGBetaBlue,ASGBetaBlue,EC2BetaBlue active
    class TGBetaGreen,ASGBetaGreen,EC2BetaGreen inactive
    class ProdSwitch,BetaSwitch switch
```

## Blue-Green Deployment Flow

### Production Environment

```mermaid
sequenceDiagram
    participant User
    participant ALB
    participant SSM as SSM Parameter
    participant Blue as Prod-Blue (Active)
    participant Green as Prod-Green (Inactive)
    participant Deploy as Deployment Process

    Note over Blue: Version 1.0 Running
    Note over Green: Scaled to 0

    User->>ALB: Requests to godbolt.org
    ALB->>Blue: Route all traffic
    Blue->>User: Response v1.0

    Deploy->>Green: Deploy version 2.0
    Deploy->>Green: Scale up instances
    Note over Green: Launching...

    Deploy->>Green: Health checks
    Note over Green: All healthy

    Deploy->>SSM: Update active-tg to Green
    Deploy->>ALB: Switch default rule to Green TG

    Note over Blue,Green: Atomic Switch

    User->>ALB: Requests to godbolt.org
    ALB->>Green: Route all traffic
    Green->>User: Response v2.0

    Deploy->>Blue: Scale down to 0
    Note over Blue: Standby for rollback
```

### Beta Environment

```mermaid
sequenceDiagram
    participant User
    participant ALB
    participant SSM as SSM Parameter
    participant Blue as Beta-Blue (Active)
    participant Green as Beta-Green (Inactive)
    participant Deploy as Deployment Process

    Note over Blue: Version A Running
    Note over Green: Scaled to 0

    User->>ALB: Requests to /beta
    ALB->>Blue: Route based on rule
    Blue->>User: Response vA

    Deploy->>Green: Deploy version B
    Deploy->>Green: Scale up instances
    Deploy->>Green: Health checks

    Deploy->>SSM: Update active-tg
    Deploy->>ALB: Switch /beta rule to Green TG

    User->>ALB: Requests to /beta
    ALB->>Green: Route based on rule
    Green->>User: Response vB

    Deploy->>Blue: Scale down (optional)
```

## Key Differences from Current Architecture

### Production (Hybrid Approach)
- **Two Target Groups**: Prod-Blue and Prod-Green
- **Two ASGs**: prod-blue and prod-green (only one active)
- **SSM Parameter**: Controls which TG receives traffic
- **ALB Default Rule**: Dynamically points to active TG
- **Deployment**: Scale up inactive, switch, scale down old

### Beta (Full Blue-Green)
- **Two Target Groups**: Beta-Blue and Beta-Green
- **Two ASGs**: beta-blue and beta-green
- **Path-based Rule**: `/beta*` switches between TGs
- **Testing Ground**: Validates blue-green before prod

### Other Environments (Unchanged)
- Staging, GPU, Windows, AArch64 keep rolling deployments
- Single target group and ASG per environment
- Instance refresh for updates

## Deployment States

### State 1: Normal Operation
```
Production:
  - Blue: Active (10 instances) → Serving traffic
  - Green: Inactive (0 instances) → Standby

Beta:
  - Blue: Active (1 instance) → Serving traffic
  - Green: Inactive (0 instances) → Standby
```

### State 2: During Deployment
```
Production:
  - Blue: Active (10 instances) → Still serving
  - Green: Warming up (10 instances) → Health checks

Beta:
  - Blue: Active (1 instance) → Still serving
  - Green: Warming up (1 instance) → Health checks
```

### State 3: Switch Moment
```
Production:
  - ALB Default Rule: Prod-Blue TG → Prod-Green TG
  - Traffic instantly moves to new version
  - No mixed versions!

Beta:
  - ALB /beta Rule: Beta-Blue TG → Beta-Green TG
  - Instant switch for beta traffic
```

### State 4: Post-Deployment
```
Production:
  - Blue: Inactive (10 instances) → Rollback ready
  - Green: Active (10 instances) → Serving traffic

Beta:
  - Blue: Inactive (0 instances) → Scaled down
  - Green: Active (1 instance) → Serving traffic
```

## Advantages Over Current System

1. **No Mixed Versions**: Traffic switches atomically between versions
2. **Instant Rollback**: Previous version stays warm (prod) or can be quickly restored
3. **Pre-deployment Validation**: New instances fully tested before receiving traffic
4. **Reduced Risk**: Bad deployments never receive production traffic
5. **Flexible Strategy**: Different approaches for different environments

## Implementation Priority

1. **Phase 1**: Beta environment (testing ground)
   - Validate blue-green mechanics
   - Test CLI tooling
   - Measure switch timing

2. **Phase 2**: Production environment
   - Implement hybrid approach
   - Keep old ASG warm for rollback
   - Monitor performance impact

3. **Phase 3**: Consider other environments
   - Evaluate if staging/gpu need blue-green
   - Keep simpler environments on rolling deploy
