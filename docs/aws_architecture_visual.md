# Compiler Explorer AWS Architecture - Visual Overview

## Current Architecture (Simplified)

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                    INTERNET                                     │
│                                       ↓                                         │
│                              [Users Worldwide]                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                                 EDGE LAYER                                      │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                        CloudFront CDN Distribution                       │  │
│  │                         - godbolt.org                                    │  │
│  │                         - compiler-explorer.com                          │  │
│  │                         - Global edge locations                         │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              LOAD BALANCING LAYER                               │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                    Application Load Balancer (ALB)                       │  │
│  │                         "GccExplorerApp"                                 │  │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │  │
│  │  │ HTTPS Listener (:443) with path-based routing rules:            │   │  │
│  │  │                                                                  │   │  │
│  │  │  /* (default)  ──────→ [Prod Target Group]                     │   │  │
│  │  │  /beta*        ──────→ [Beta Target Group]                     │   │  │
│  │  │  /staging*     ──────→ [Staging Target Group]                  │   │  │
│  │  │  /gpu*         ──────→ [GPU Target Group]                      │   │  │
│  │  │  /winprod*     ──────→ [WinProd Target Group]                  │   │  │
│  │  │  /aarch64prod* ──────→ [AArch64Prod Target Group]              │   │  │
│  │  └─────────────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            TARGET GROUP LAYER                                   │
│                                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                  │
│  │  Prod TG       │  │  Beta TG       │  │  Staging TG    │                  │
│  │  Port: 80      │  │  Port: 80      │  │  Port: 80      │                  │
│  │  Health: /hc   │  │  Health: /hc   │  │  Health: /hc   │                  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘                  │
│          │                   │                   │                             │
│          ↓                   ↓                   ↓                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                  │
│  │  GPU TG        │  │  WinProd TG    │  │  AArch64 TG    │                  │
│  │  Port: 80      │  │  Port: 80      │  │  Port: 80      │                  │
│  │  Health: /hc   │  │  Health: /hc   │  │  Health: /hc   │                  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘                  │
└──────────┼───────────────────┼───────────────────┼─────────────────────────────┘
           ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          AUTO SCALING GROUP LAYER                               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │ ASG: prod-blue/green     │ ASG: beta-blue/green│ ASG: staging           │  │
│  │ Min: 0, Max: 40 each    │ Min: 0, Max: 4 each │ Min: 0, Max: 4        │  │
│  │ Current: ~10-15 (1 ASG) │ Current: 0-1 (1 ASG)│ Current: 0-1          │  │
│  │ Spot: 100%              │ On-Demand: 100%     │ On-Demand: 100%       │  │
│  │ ┌─────┐ ┌─────┐ ┌─────┐│ ┌─────┐             │ ┌─────┐               │  │
│  │ │ EC2 │ │ EC2 │ │ EC2 ││ │ EC2 │             │ │ EC2 │               │  │
│  │ │ m5. │ │ m6. │ │ m5. ││ │ t3. │             │ │ t3. │               │  │
│  │ └─────┘ └─────┘ └─────┘│ └─────┘             │ └─────┘               │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │ ASG: gpu                 │ ASG: winprod-mixed  │ ASG: aarch64prod      │  │
│  │ Min: 0, Max: 8          │ Min: 0, Max: 4      │ Min: 0, Max: 8        │  │
│  │ GPU: g4dn.xlarge        │ Windows Server      │ ARM: t4g/m6g          │  │
│  │ ┌─────┐                 │ ┌─────┐             │ ┌─────┐               │  │
│  │ │ EC2 │                 │ │ EC2 │             │ │ EC2 │               │  │
│  │ │ GPU │                 │ │ Win │             │ │ ARM │               │  │
│  │ └─────┘                 │ └─────┘             │ └─────┘               │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              STORAGE LAYER                                      │
│                                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐   │
│  │   EFS File System   │  │    S3 Buckets       │  │   Instance Storage  │   │
│  │  - Compiler cache   │  │  - Static content   │  │  - Local SSD/EBS    │   │
│  │  - Shared libs      │  │  - Access logs      │  │  - Temp files       │   │
│  │  - Mount: /opt/ce   │  │  - Build artifacts  │  │  - Compilation out  │   │
│  └─────────────────────┘  └─────────────────────┘  └─────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

## Instance Refresh Process (Legacy Issue - Solved for Prod/Beta)

```
Time →
T0: Initial State (all instances version A)
    [A] [A] [A] [A] [A] [A] [A] [A]

T1: Refresh starts (MinHealthyPercent: 75%)
    [A] [A] [A] [A] [A] [A] [X] [X]  ← 25% terminating

T2: New instances launching
    [A] [A] [A] [A] [A] [A] [B] [B]  ← New version B

T3: Mixed version state (PROBLEM!)
    [A] [A] [A] [A] [B] [B] [B] [B]  ← Users hit different versions

T4: Continuing refresh
    [A] [A] [X] [X] [B] [B] [B] [B]

T5: Final state (all instances version B)
    [B] [B] [B] [B] [B] [B] [B] [B]

Problem Period: T2-T4 where both A and B serve traffic
NOTE: This problem is now solved for production and beta via blue-green deployment!
```

## Blue-Green Deployment (Current for Prod/Beta)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        ALB Path: /beta*                                 │
│                              ↓                                          │
│                   ┌─────────────────────┐                              │
│                   │  Can switch between │                              │
│                   │   Beta-Blue TG  ←───┼──→  Beta-Green TG           │
│                   └─────────┬───────────┘                              │
│                             ↓                                          │
│              ┌──────────────┴──────────────┐                          │
│              ↓                             ↓                          │
│     ┌─────────────────┐          ┌─────────────────┐                 │
│     │ ASG: beta-blue  │          │ ASG: beta-green │                 │
│     │ Version: A      │          │ Version: B      │                 │
│     │ State: Active   │          │ State: Standby  │                 │
│     └─────────────────┘          └─────────────────┘                 │
│                                                                        │
│     Deployment: Scale up green → Switch TG → Scale down blue          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Metrics and Monitoring

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CloudWatch Metrics                              │
├─────────────────────────────────────────────────────────────────────────┤
│ ALB:                                                                    │
│  - RequestCount: ~1M requests/hour (peak)                              │
│  - TargetResponseTime: <100ms average                                  │
│  - UnHealthyHostCount: Should be 0                                     │
│  - HTTPCode_Target_5XX_Count: Monitor for errors                       │
│                                                                         │
│ Auto Scaling:                                                           │
│  - CPUUtilization: Target 50%                                         │
│  - NetworkIn/Out: ~100MB/s peak                                       │
│  - StatusCheckFailed: Triggers replacement                            │
│                                                                         │
│ Target Groups:                                                          │
│  - HealthyHostCount: Matches desired capacity                         │
│  - UnHealthyHostCount: Should be 0                                    │
│  - RequestCountPerTarget: Load distribution                           │
└─────────────────────────────────────────────────────────────────────────┘
```
