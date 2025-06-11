# Compiler Explorer Infrastructure Cost Report

**Report Date:** June 2025 | **Data Period:** October 2024 - April 2025
**Total Monthly Operating Cost:** $3,100 (April 2025) | **Annual Budget:** ~$37,000 | **Cost per Compilation:** ~$0.00039

## Executive Summary

Compiler Explorer serves approximately **8 million backend compilations per month** (down from peaks of 14M+ in 2024) through what's become a surprisingly complex global infrastructure. This report provides complete transparency on where patron and sponsor contributions go, covering both the $2,550/month AWS infrastructure costs (April 2025) and the additional $550/month in operational expenses that keep this amateur project running (mostly) smoothly.

### Seven-Month AWS Cost Trends
- **October 2024:** $2,742 (AWS) + $550 (operational) = **$3,292 total**
- **November 2024:** $2,704 (AWS) + $550 (operational) = **$3,254 total**
- **December 2024:** $2,542 (AWS) + $550 (operational) = **$3,092 total**
- **January 2025:** $2,795 (AWS) + $550 (operational) = **$3,345 total** ← Peak month
- **February 2025:** $2,637 (AWS) + $550 (operational) = **$3,187 total**
- **March 2025:** $2,690 (AWS) + $550 (operational) = **$3,240 total**
- **April 2025:** $2,550 (AWS) + $550 (operational) = **$3,100 total**
- **Reality check:** Costs are volatile, not consistently decreasing. January 2025 was actually our highest month.
- **Annual projection:** ~$37,000 with fluctuations around $3,100-3,300/month

### Cost Efficiency
- **$0.00039 per compilation** (based on ~8M monthly backend compilations in recent months)
- **Compilation volume trends:** Down from 14M+ monthly peaks in 2024 to ~8M in 2025
- **24/7 global availability** across all major geographic regions (when things aren't broken)
- **Multi-architecture support** (x86_64, ARM64, GPU computing)
- **Surprisingly reliable operations** considering it's mostly just me and some very kind volunteers

---

## Complete Cost Breakdown

### AWS Infrastructure ($2,550/month - 82.3%)

The core AWS infrastructure that powers Compiler Explorer's global compilation service.

### Operational Infrastructure ($550/month - 17.7%)

Essential services and operational costs that help keep the lights on and the service running:

#### **Monitoring & Observability ($100/month)**
- **Grafana Cloud ($50/month):** Pretty graphs and alerts that help us spot when things are going wrong (see them at https://stats.compiler-explorer.com/)
- **Papertrail ($30/month):** Centralized log storage so we can figure out what broke and when
- **Sentry ($20/month):** Error tracking that tells us about problems, hopefully before users do

#### **Development & Operations ($450/month)**
- **Office Space ($350/month):** My portion of office rental costs (I work on CE stuff roughly half the time I'm there, hence only charging a percentage). This is a recent change and is only temporary while I'm between "real" jobs.
- **Development Tools:** IDE licenses, various subscriptions for development and testing
- **Community Operations ($50/month average):**
  - Discord server subscription ($250/year): Where we chat with contributors and users
  - Shipping costs for patron goodies ($200/year average): Stickers and swag for supporters

---

## AWS Infrastructure Detailed Breakdown

### 1. EC2 Compute Infrastructure ($1,276/month - 50.0%)

This is the backbone of Compiler Explorer, providing the actual compilation compute power across multiple architectures and environments. *Note: This includes $262/month for CI infrastructure (tagged "Continuous Integration" in AWS) within the total.*

#### **Main x86_64 Production Fleet ($200-300/month estimated)**
- **Blue-Green Deployment:** Transitioning to blue-green architecture with up to 40 instances per environment
- **Instance Types:** 16 different types (`m5.large`, `m6i.large`, `m7i.large`, `r6a.large`, `i3.large`, etc.)
- **Spot Strategy:** 100% spot instances using `price-capacity-optimized` allocation for maximum cost savings
- **Auto-scaling:** CPU-based targeting 50% utilization
- **Status:** Infrastructure defined but migration from legacy system still in progress
- **What this enables:** Main x86_64 compilation workload serving the majority of user requests

#### **Multi-Architecture Production Fleet ($200-300/month estimated)**
- **ARM64 Production:** 1-6x `r7g.medium` instances using 100% spot pricing with queue-based scaling
- **Windows Production:** 2-8x mixed `m5/m6` large instances with 100% spot pricing
- **What this enables:** Cross-platform compilation support for ARM and Windows development

#### **GPU Computing Environment ($400-500/month estimated)**
- **GPU Production:** 2-4x `g4dn.xlarge`/`g4dn.2xlarge` with 1 on-demand base + spot instances
- **Purpose:** CUDA, OpenCL, and graphics programming compilation
- **Highest cost per instance:** GPU instances are significantly more expensive than standard compute
- **What this enables:** Allows developers to compile and test GPU-accelerated code including CUDA kernels, OpenCL programs, and graphics shaders

#### **Continuous Integration Infrastructure ($262/month)**
- **External CI System:** Separate scalable CI infrastructure (see https://github.com/compiler-explorer/ce-ci)
- **Purpose:** Daily and ad hoc compiler builds
- **Configuration:** Mix of x86_64, ARM64, and Windows builders
- **What this enables:** Regular automated compiler updates

#### **Staging & Test Environments ($20-50/month estimated)**
- **x86_64 Staging:** `m5.large` instances (0-4 capacity, typically off)
- **Beta Environment:** Blue-green `m5.large` setup for pre-production testing. Very infrequently used
- **ARM64 Staging:** `r7g.medium` instances with 100% spot (0-4 capacity)
- **Windows Staging/Test:** `m6i.large` and `c5ad.large` instances (0-4 capacity each)
- **What this enables:** Safe testing of infrastructure changes before production deployment

#### **Always-On Infrastructure (~$28/month)**
- **AdminNode:** `t3a.small` for management and monitoring (~$14/month)
- **ConanNode:** `t3.micro` for package management (~$7.50/month)
- **CESMBServer:** `t4g.micro` for SMB file sharing (~$6/month)
- **What this enables:** Basic infrastructure management, monitoring, and file sharing

#### **On-Demand Build Infrastructure (~$210/month)**
- **BuilderNode:** 1x `c5d.4xlarge` (16 vCPU, 32GB RAM, 2x300GB NVMe SSD)
  - Builds libraries (eventual plans to transition to the scalable CI)
  - Usage pattern: ~37.5% uptime, actual cost ~$207/month
  - Savings: ~$346/month vs always-on ($553/month)
- **CERunner:** 1x `c5.xlarge` (4 vCPU, 8GB RAM)
  - Used to pre-cache deployed compiler information by "dry run" of startup followed by state saving
  - Usage pattern: ~2.1% uptime (~15 hours/month), actual cost ~$3/month
  - Savings: ~$135/month vs always-on ($138/month)
- **Combined smart scheduling savings:** ~$481/month vs running 24/7
- **What this enables:** Library builds; operational work relating to faster node startup

**Cost Optimization Strategies:**
- **Spot instances:** The entire production fleet uses 100% spot instances (except 1 on-demand GPU instance for availability), providing 60-90% cost savings
- **Smart scheduling:** Build infrastructure runs only when needed, saving ~$481/month vs always-on
  - BuilderNode: 37.5% uptime saves ~$346/month
  - CERunner: 2.1% uptime saves ~$135/month
- **Minimal always-on footprint:** Only ~$28/month in truly always-on infrastructure for basic operations
- **Right-sizing:** Always-on infrastructure uses small, efficient instances for basic operational tasks
- **Graceful scaling:** Infrastructure designed to handle capacity fluctuations while maintaining service availability

#### **Traffic Analysis (ALB Metrics & Compilation Stats)**
Based on ALB request data from Oct 2024 - Apr 2025, the infrastructure handles:
- **Peak ALB requests:** Up to 1.66M requests/day (February 2025) - significantly higher than previous peaks
- **Peak compilation day:** February 4th, 2025 with 918,817 backend compilations (~20% higher than next highest at 698,869)
- **High traffic days:** Multiple days over 1M ALB requests/day (Jan-Apr 2025)
- **Typical weekdays:** 700K-950K ALB requests/day
- **Weekend dips:** 400K-600K ALB requests/day
- **Holiday periods:** Reduced traffic (Christmas/New Year: ~450K-580K requests/day)
- **Traffic growth:** Clear upward trend in peak traffic loads during 2025

### 2. Shared Storage Infrastructure ($469/month - 18.4%)

#### **EFS - Compiler Binary Storage**
- **Purpose:** Centralized storage for 100+ compiler toolchains
- **Configuration:** Multi-AZ EFS with lifecycle policies (14-day transition to IA storage)
- **Contents:**
  - `/efs/compiler-explorer/` - All compiler binaries, toolchains and library sources
  - `/efs/winshared` - All Windows compiler binaries and tools
  - `/efs/squash-images/` - Compressed compiler environments
  - `/efs/cefs-images/` - In-progress sketch of alternative compressed file system
  - Total ~4TB
- **What this enables:**
  - Single source of truth for all compiler versions
  - Eliminates need for each instance to store 4TB+ of compilers and libraries locally
  - Supports rapid auto-scaling without compiler installation delays
  - Cost-effective compared to individual instance storage

#### **Cost Efficiency Analysis**
- **Alternative cost:** ~40 instances × 100GB storage = 4TB individual storage ≈ $400/month in EBS costs alone (assuming we could split the storage sensibly)
- **Current approach:** Shared storage serves all instances simultaneously
- **Additional benefits:** Centralized updates, consistency across environments

### 3. Global Content Delivery ($305/month - 12.0%)

#### **CloudFront CDN Infrastructure**
- **5 CloudFront Distributions:**
  - 3 identical main distributions (godbolt.org, compiler-explorer.com, godbo.lt)
  - 1 static content CDN (static.ce-cdn.net)
  - 1 Conan package manager CDN (conan.compiler-explorer.com)

#### **Global Traffic Patterns (CloudFront Analysis)**
Recent CloudFront metrics show significant geographic distribution:
- **Peak traffic days:** 500K+ CloudFront requests
- **Typical days:** 30K-40K CloudFront requests
- **Global edge delivery:** All CloudFront price classes enabled for worldwide performance
- **Cache efficiency:** Mix of static assets and dynamic compilation results

#### **What this enables:**
- **Fast response times** worldwide for compilation results
- **Reduced server load** through caching (less things breaking under load)
- **Geographic redundancy** so if one region has issues, others keep working
- **Bandwidth cost savings** since repeated requests hit the cache instead of our servers

### 4. Supporting Infrastructure ($470/month - 18.4%)

#### **EC2 Other ($186/month)**
- **EBS Storage:** Persistent storage for instances (~150GB across admin, conan, SMB nodes)
- **Data Transfer:** Inter-AZ communication, internet egress
- **Snapshots:** Automated backups for critical data
- **EBS Optimization:** Enhanced networking for build infrastructure

#### **S3 Storage ($106/month)**
- **Public compiler binaries:** Downloadable toolchains and libraries
- **Log storage:** 32-day retention for CloudFront and ALB logs
- **Persistent cache:** Compilation results cached in S3 for a day or so
- **Build artifacts:** Temporary storage with automated cleanup
- **Static assets:** Web interface components and documentation

#### **Network & Load Balancing ($111/month)**
- **VPC Costs ($62):** Cross-AZ data transfer, no expensive NAT gateways
- **ALB ($45):** Single load balancer serving 7 environments with intelligent routing
- **Route53 ($4):** DNS for 4 hosted zones (godbolt.org, compiler-explorer.com, etc.)

#### **Security & AWS Monitoring ($62/month)**
- **AWS WAF:** Keeps the bad actors out and rate-limits overly enthusiastic users (12K POST requests per 5 min per IP)
- **CloudWatch:** Basic AWS metrics and alarms (the ones that actually work reliably)
- **Lambda functions:** Little serverless helpers for alerts and statistics
- **Note:** The more useful monitoring happens via Grafana and Papertrail

---

## Operational Insights

### Traffic Patterns and Scaling
- **Peak Usage:** US daytime hours (EST) show highest compilation activity
- **Geographic Distribution:** Global user base with significant traffic from all continents
- **Seasonal Trends:** Reduced usage during holidays, increased activity during academic semesters
- **Auto-scaling Response:** Infrastructure automatically scales from minimum viable capacity to handle peak loads

### Cost Optimization Strategies Already Implemented
1. **Spot Instance Usage:** ~80% of fleet runs on spot instances (60-90% cost savings)
2. **EFS Lifecycle Policies:** Automatic transition to cheaper storage tiers
3. **Intelligent Auto-scaling:** SQS-driven scaling prevents over-provisioning
4. **Single ALB Strategy:** All environments share one load balancer
5. **No NAT Gateways:** Direct internet access reduces networking costs

---

## Future Optimization Opportunities

### High-Impact, Low-Effort Improvements

#### **CloudFront Optimization (Potential 20-30% CDN savings)**
- **Domain Consolidation:** Consider consolidating three identical distributions
- **Price Class Optimization:** Evaluate restricting to major regions (US/EU/Asia)
- **Cache Policy Tuning:** Improve cache hit rates for static content

#### **Storage Optimization (Potential 15-25% savings)**
- **EFS Intelligent Tiering:** Automatic cost optimization based on access patterns
- **S3 Storage Class Analysis:** Transition infrequently accessed content to cheaper tiers
- **Compiler Archive Management:** Remove obsolete compiler versions

#### **Compute Optimization (Potential 5-10% savings)**
- **EBS Volume Type Migration:** Switch from gp2 to gp3 for better price/performance
- **Instance Type Review:** Evaluate newer generation instances for better performance/cost
- **Reserved Instance Strategy:** Consider RIs for always-on infrastructure components

---

## Value Delivered to the Community

### Direct Impact
- **~8M monthly backend compilations** served globally with sub-second response times (down from 14M+ peaks)
- **100+ compiler toolchains** maintained and updated regularly
- **24/7 availability** across multiple architectures (x86_64, ARM64, GPU)
- **Zero user tracking** - privacy-first approach with no analytics beyond aggregate metrics

### What We've Managed to Build
- **Multi-architecture support** so you can see how your code compiles on different platforms
- **GPU computing capabilities** for when you want to play with CUDA or OpenCL
- **Global CDN delivery** that mostly keeps things fast worldwide
- **Automatic scaling** that usually handles traffic spikes (so long as we can boot up new nodes quickly enough)

### Who Uses This Thing
- **Students** learning about compilers and optimization (and procrastinating on assignments)
- **Engineers** checking what their code actually does at the assembly level
- **Compiler developers** checking older builds, corroborating bug reports from users
- **Researchers** doing compiler and language research
- **Open source developers** testing their libraries across different compilers and platforms

---

## Cost Transparency and Accountability

### How We Try to Keep Costs Down
- **Volatile but manageable costs:** Despite traffic growth, we've kept costs in the $3,100-3,300 range
- **Auto-scaling:** Only pay for what we actually need (when the algorithms work correctly)
- **Regular cost reviews:** Constantly looking for ways to optimize without breaking things
- **Spot instances everywhere:** Using AWS's discounted "spare" capacity whenever possible (60-90% savings)
- **Peak management:** January 2025 showed us what happens when traffic spikes - $3,345 total cost

### What You Get for Your Money
- **$0.00039 per compilation:** Incredible value even with lower volumes (8M monthly vs 14M+ peaks)
- **Completely free:** No user fees, no ads, no "premium" tiers
- **No tracking:** We genuinely don't know who you are or what you're compiling (by design)
- **Surprisingly reliable:** For a project run mostly by one person and volunteers
- **Fixed costs, variable usage:** Infrastructure costs stay steady even as compilation volumes fluctuate

---

## Operational Transparency

### What Your Contributions Support

**Technical Infrastructure (82.3% - $2,550/month):**
- Global AWS infrastructure serving ~8M monthly backend compilations
- Multi-architecture compilation support (x86_64, ARM64, GPU computing)
- 24/7 availability with intelligent auto-scaling (handling peak days of 1.66M ALB requests)
- 100+ compiler toolchains maintained and updated

**Operations & Development (17.7% - $550/month):**
- Development time and workspace costs (partial office rental)
- Monitoring tools that actually tell us when things break
- Error tracking so we can fix problems quickly
- Community infrastructure and sending stickers to supporters

### The Reality Check

Based on 7 months of data (Oct 2024 - Apr 2025):
- **Volatile costs:** Monthly costs range from $3,092 to $3,345, with January 2025 being our peak month
- **Compilation volume decline:** Backend compilations down from 14M+ (2024 peaks) to ~8M monthly in 2025
- **Annual budget:** ~$37,000 to keep everything running (assuming $3,100-3,300/month average)
- **Incredibly efficient:** At $0.00039 per compilation, we're getting amazing value from the infrastructure
- **Always optimizing:** Constantly trying to squeeze more efficiency out of AWS (it's like a game at this point)
- **Fixed cost reality:** Infrastructure costs remain steady even as compilation volumes fluctuate significantly

---

*This report is our attempt at transparency about where your money goes. Every dollar contributed directly supports keeping this project running for thousands of developers worldwide.*

**Questions or suggestions about this cost analysis?** Contact Matt: matt@godbolt.org
