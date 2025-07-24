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
│  │  │  /* (default)  ──────→ [Prod TGs] (switchable)                │   │  │
│  │  │  /beta*        ──────→ [Beta TGs] (switchable)               │   │  │
│  │  │  /staging*     ──────→ [Staging TGs] (switchable)            │   │  │
│  │  │  /gpu*         ──────→ [GPU TGs] (switchable)                │   │  │
│  │  │  /win*         ──────→ [Win TGs] (switchable)                │   │  │
│  │  │  /aarch64*     ──────→ [AArch64 TGs] (switchable)            │   │  │
│  │  └─────────────────────────────────────────────────────────────────┘   │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            TARGET GROUP LAYER                                   │
│                                                                                 │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                  │
│  │ Prod TGs       │  │ Beta TGs       │  │ Staging TGs    │                  │
│  │ Blue + Green   │  │ Blue + Green   │  │ Blue + Green   │                  │
│  │ Port: 80       │  │ Port: 80       │  │ Port: 80       │                  │
│  │ Health: /hc    │  │ Health: /hc    │  │ Health: /hc    │                  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘                  │
│          │                   │                   │                             │
│          ↓                   ↓                   ↓                             │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐                  │
│  │ GPU TGs        │  │ Win TGs        │  │ AArch64 TGs    │                  │
│  │ Blue + Green   │  │ Blue + Green   │  │ Blue + Green   │                  │
│  │ Port: 80       │  │ Port: 80       │  │ Port: 80       │                  │
│  │ Health: /hc    │  │ Health: /hc    │  │ Health: /hc    │                  │
│  └───────┬────────┘  └───────┬────────┘  └───────┬────────┘                  │
└──────────┼───────────────────┼───────────────────┼─────────────────────────────┘
           ↓                   ↓                   ↓
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          AUTO SCALING GROUP LAYER                               │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │ ASG: prod               │ ASG: beta           │ ASG: staging           │  │
│  │ Blue + Green pairs     │ Blue + Green pairs  │ Blue + Green pairs     │  │
│  │ Min: 0, Max: 40 each   │ Min: 0, Max: 4 each │ Min: 0, Max: 4 each   │  │
│  │ Current: ~10-15 (1 ASG)│ Current: 0-1 (1 ASG)│ Current: 0-1 (1 ASG)  │  │
│  │ Spot: 100%             │ On-Demand: 100%     │ On-Demand: 100%       │  │
│  │ ┌─────┐ ┌─────┐ ┌─────┐│ ┌─────┐             │ ┌─────┐               │  │
│  │ │ EC2 │ │ EC2 │ │ EC2 ││ │ EC2 │             │ │ EC2 │               │  │
│  │ │ m5. │ │ m6. │ │ m5. ││ │ t3. │             │ │ t3. │               │  │
│  │ └─────┘ └─────┘ └─────┘│ └─────┘             │ └─────┘               │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │ ASG: gpu               │ ASG: win             │ ASG: aarch64           │  │
│  │ Blue + Green pairs     │ Blue + Green pairs   │ Blue + Green pairs     │  │
│  │ Min: 0, Max: 8 each    │ Min: 0, Max: 4 each  │ Min: 0, Max: 8 each   │  │
│  │ GPU: g4dn.xlarge       │ Windows Server       │ ARM: t4g/m6g          │  │
│  │ ┌─────┐                │ ┌─────┐              │ ┌─────┐               │  │
│  │ │ EC2 │                │ │ EC2 │              │ │ EC2 │               │  │
│  │ │ GPU │                │ │ Win │              │ │ ARM │               │  │
│  │ └─────┘                │ └─────┘              │ └─────┘               │  │
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

## Instance Refresh Process (Legacy Issue - Solved for All Environments)

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
NOTE: This problem is now solved for ALL environments via blue-green deployment!
```

## Deployment Strategy (Current for All Environments)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    ALB Paths: ALL ENVIRONMENTS                          │
│                              ↓                                          │
│     ┌─────────────────────────────────────────────────────────────────┐│
│     │  /* → Prod TGs        │  /beta* → Beta TGs                     ││
│     │  /staging* → Staging TGs  │  /gpu* → GPU TGs                   ││
│     │  /win* → Win TGs      │  /aarch64* → AArch64 TGs               ││
│     └─────────────────────┬───────────────────────────────────────────┘│
│                           ↓                                            │
│        ┌──────────────────┴──────────────────┐                       │
│        ↓                                     ↓                       │
│ ┌─────────────────┐                ┌─────────────────┐               │
│ │ ASG: {env} A    │                │ ASG: {env} B    │               │
│ │ Version: A      │                │ Version: B      │               │
│ │ State: Active   │                │ State: Standby  │               │
│ └─────────────────┘                └─────────────────┘               │
│                                                                        │
│ Deployment: Scale up standby → Switch TG → Scale down old             │
│ Available for: prod, beta, staging, gpu, win*, aarch64*               │
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
