# Compiler Explorer AWS Architecture (Current State)

## High-Level Architecture Diagram

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

            DefRule["Default Rule - Prod TG"]
            BetaRule["'/beta*' - Beta TG"]
            StagingRule["'/staging*' - Staging TG"]
            GPURule["'/gpu*' - GPU TG"]
            WinRule["'/win*' - Win TGs"]
            AArch64Rule["'/aarch64*' - AArch64 TGs"]
        end
    end

    subgraph "Target Groups"
        TGProdBlue[TG: Prod-Blue<br/>Port 80]
        TGProdGreen[TG: Prod-Green<br/>Port 80]
        TGBetaBlue[TG: Beta-Blue<br/>Port 80]
        TGBetaGreen[TG: Beta-Green<br/>Port 80]
        TGStaging[TG: Staging<br/>Port 80]
        TGGpu[TG: GPU<br/>Port 80]
        TGWin[TG: WinProd/Staging<br/>Port 80]
        TGAArch[TG: AArch64Prod/Staging<br/>Port 80]
        TGConan[TG: Conan<br/>Port 1080]
    end

    subgraph "Auto Scaling Groups"
        ASGProdBlue[ASG: prod-blue<br/>Min: 0, Max: 40<br/>Spot Instances]
        ASGProdGreen[ASG: prod-green<br/>Min: 0, Max: 40<br/>Spot Instances]
        ASGBetaBlue[ASG: beta-blue<br/>Min: 0, Max: 4]
        ASGBetaGreen[ASG: beta-green<br/>Min: 0, Max: 4]
        ASGStaging[ASG: staging<br/>Min: 0, Max: 4]
        ASGGpu[ASG: gpu<br/>Min: 0, Max: 8<br/>GPU Instances]
        ASGWin[ASG: winprod-mixed<br/>Windows Instances]
        ASGAArch[ASG: aarch64prod-mixed<br/>ARM Instances]
    end

    subgraph "EC2 Instances"
        EC2Prod[EC2 Instances<br/>m5/m6 family<br/>EBS Optimized]
        EC2Beta[EC2 Instances<br/>On-demand]
        EC2Staging[EC2 Instances<br/>On-demand]
        EC2Gpu[EC2 Instances<br/>g4dn.xlarge]
        EC2Win[EC2 Instances<br/>Windows]
        EC2AArch[EC2 Instances<br/>ARM/Graviton]
        ConanNode[Conan Node<br/>Static Instance]
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

    HTTPS --> DefRule
    HTTPS --> BetaRule
    HTTPS --> StagingRule
    HTTPS --> GPURule
    HTTPS --> WinRule
    HTTPS --> AArch64Rule

    DefRule -.->|Switchable| TGProdBlue
    DefRule -.->|Switchable| TGProdGreen
    BetaRule -.->|Switchable| TGBetaBlue
    BetaRule -.->|Switchable| TGBetaGreen
    StagingRule --> TGStaging
    GPURule --> TGGpu
    WinRule --> TGWin
    AArch64Rule --> TGAArch

    TGProdBlue --> ASGProdBlue
    TGProdGreen --> ASGProdGreen
    TGBetaBlue --> ASGBetaBlue
    TGBetaGreen --> ASGBetaGreen
    TGStaging --> ASGStaging
    TGGpu --> ASGGpu
    TGWin --> ASGWin
    TGAArch --> ASGAArch
    TGConan --> ConanNode

    ASGProdBlue --> EC2Prod
    ASGProdGreen --> EC2Prod
    ASGBetaBlue --> EC2Beta
    ASGBetaGreen --> EC2Beta
    ASGStaging --> EC2Staging
    ASGGpu --> EC2Gpu
    ASGWin --> EC2Win
    ASGAArch --> EC2AArch

    EC2Prod --> EFS
    EC2Beta --> EFS
    EC2Staging --> EFS
    EC2Gpu --> EFS

    ALB --> S3Logs
    CF --> S3Static
```

## Component Details

### CloudFront Distribution
- **Domain**: godbolt.org, compiler-explorer.com
- **Origin**: ALB (GccExplorerApp)
- **Behaviors**:
  - Static content cached
  - Dynamic content passed through
- **SSL**: ACM certificate for HTTPS

### Application Load Balancer (ALB)
- **Name**: GccExplorerApp
- **Type**: Internet-facing
- **Listeners**:
  - HTTP (80) → Redirect to HTTPS
  - HTTPS (443) → Route based on path
- **Health Checks**: `/healthcheck` endpoint
- **Deregistration Delay**: 20 seconds

### Path-Based Routing Rules
| Priority | Path Pattern | Target Group | Environment |
|----------|-------------|--------------|-------------|
| Default  | `/*`        | Prod         | Production  |
| 1        | `/beta*`    | Beta         | Beta testing |
| 2        | `/staging*` | Staging      | Pre-prod testing |
| 3        | `/gpu*`     | GPU          | GPU compilers |
| 6        | `/wintest*` | WinTest      | Windows test |
| 7        | `/winstaging*` | WinStaging | Windows staging |
| 8        | `/winprod*` | WinProd      | Windows prod |

### Auto Scaling Groups

#### Production ASGs (Blue-Green)
- **Blue ASG**: prod-blue (active or standby)
- **Green ASG**: prod-green (active or standby)
- **Instance Types**: m5.large, m6.large, etc. (mixed instances policy)
- **Purchase Options**: 100% Spot instances
- **Scaling**: CPU target tracking (50%) on active ASG
- **Health Check**: ELB type, 240s grace period
- **Target Groups**: Prod-Blue and Prod-Green (ALB switches between them)
- **State Management**: SSM parameters track active color

#### Specialized ASGs
- **GPU**: g4dn.xlarge instances for CUDA compilers
- **Windows**: Windows Server instances
- **AArch64**: ARM/Graviton2 instances

### Target Group Health Checks
- **Protocol**: HTTP
- **Path**: `/healthcheck`
- **Interval**: 10 seconds
- **Timeout**: 8 seconds
- **Healthy Threshold**: 2 checks
- **Unhealthy Threshold**: 3 checks

### Storage Architecture
- **EFS**: Shared filesystem for compiler cache
  - Mounted on all Linux instances
  - Burst mode for performance
- **S3 Buckets**:
  - `compiler-explorer`: Static content
  - `compiler-explorer-logs`: ALB access logs
  - `ce-cdn-net`: CDN content

## Request Flow

1. **User Request** → godbolt.org
2. **Route 53** → Resolves to CloudFront
3. **CloudFront** → Checks cache, forwards to ALB if needed
4. **ALB** → Routes based on path:
   - `/beta*` → Beta target group
   - `/staging*` → Staging target group
   - Default → Production target group
5. **Target Group** → Selects healthy instance
6. **EC2 Instance** → Processes compilation request
7. **Response** → Returns through ALB → CloudFront → User

## High Availability Features

- **Multi-AZ Deployment**: Instances spread across availability zones
- **Auto Scaling**: Automatic capacity adjustment based on load
- **Health Checks**: Automatic instance replacement on failure
- **Spot Instance Diversification**: Multiple instance types for availability
- **CloudFront Caching**: Reduces origin load
- **Connection Draining**: 20-second graceful shutdown

## Current Limitations

1. **Other Environments**: Rolling deployments still cause mixed versions in staging/gpu/win/aarch64
2. **Legacy Dependencies**: Some monitoring/tooling may still reference old ASG names
3. **Resource Overhead**: Blue-green requires brief 2x capacity during deployments
