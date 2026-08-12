---
title: Aurora Order Service Migration Report
subtitle: Legacy Virtual Machine Platform to Azure Kubernetes Service
author: Aurora Platform Engineering
classification: Unclassified | Non classifié
version: 1.2.0
date: June 2026
---

> The migration is not about moving workloads. It is about removing the manual
> steps that a growing platform can no longer afford. Every decision in this
> report is measured against that single objective.
> — Platform Engineering, project sponsor

\newpage

# 1. Executive Summary

This report documents the assessment, planning, and execution of the migration
of the Aurora Order Service from a legacy virtual-machine platform to Azure
Kubernetes Service (AKS). The migration was initiated in January 2026 and
completed at the end of May 2026. All three production workloads that make up
the Order Service are now running on AKS, deployed exclusively through GitOps,
with no scheduled downtime at cutover.

The Order Service previously ran on twelve virtual machines managed by hand.
Deployments were documented in a wiki and applied through an ad hoc sequence of
scripts. Provisioning of new environments took up to six weeks and required a
senior engineer. The platform had no rollback story beyond a documented
"trust the backup" procedure, and no automated testing ran against a
production-like environment.

The target architecture replaces the manual fleet with a version-pinned,
declarative platform. Everything that can be represented as code is now stored
in Git: cluster configuration, workload manifests, secrets references, and
operational runbooks. Infrastructure changes are reviewed, approved, and
reconciled by Argo CD. Secrets never enter the repository; they are resolved at
runtime from Azure Key Vault through the CSI Secrets Store driver.

The report covers the current-state assessment, the target architecture, the
migration strategy, rollout and testing results, the risk register, cost
analysis, timeline, and rollback procedures. It concludes with a set of
recommendations for the follow-on phases of the platform roadmap.

Key outcomes of the migration:

- All twelve source virtual machines decommissioned, including four that had
  not been tracked in the asset inventory.
- Deployment lead time reduced from days to minutes; a full environment is now
  reproducible from a single Git commit.
- Peak request latency at the 99th percentile improved from 1,420 ms to 214 ms
  under equivalent load, following the removal of a serialized database lock
  that the legacy stack depended on.
- Estimated monthly infrastructure cost reduced by 31% at comparable capacity,
  before savings from right-sizing are counted.
- Two critical findings from the pre-migration security assessment (CIS
  benchmark and dependency scan) were resolved during the migration rather
  than deferred.

The remainder of this report provides the evidence and procedure behind these
outcomes, and identifies the follow-on work required to complete the platform
roadmap.

\newpage

# 2. Introduction and Objectives

## 2.1 Background

The Aurora Order Service is the core of the Aurora order-management product
line. It accepts orders from three external channels, validates them against
the product catalogue, applies pricing and promotion rules, and writes accepted
orders to the Aurora ledger for downstream fulfilment. The service has been in
production since 2019 and has grown to handle approximately 11,000 orders per
day at peak season.

The service was originally deployed to a fleet of twelve virtual machines
running Ubuntu 20.04. The fleet was assembled incrementally as the product
grew. By 2025 it exhibited the characteristics of an environment that had
outgrown its operating model: configuration drifted between hosts, no two
hosts carried identical software, and the runbook for replacing a failed host
had not been exercised since 2022.

The decision to migrate to AKS was taken in the fourth quarter of 2025 after a
platform review identified three structural risks that incremental patching
could not address:

- **Operational risk.** Deployment depended on the availability of two senior
  engineers. The documented procedure spanned forty-seven manual steps across
  three hosts.
- **Recovery risk.** Recovery-time objective (RTO) for a full environment
  restore was estimated at nine hours and had never been demonstrated.
- **Compliance risk.** Quarterly security scans reported unpatched
  vulnerabilities that were remediated by hand, with no audit trail of when or
  by whom the remediation was applied.

## 2.2 Scope

The scope of this migration is limited to the Order Service runtime and its
deployment pipeline. The following items are in scope:

- The three production workloads that constitute the Order Service:
  `order-api`, `order-worker`, and `order-bridge`.
- The supporting infrastructure: ingress, TLS, secrets, and observability
  configuration for those workloads.
- The CI/CD and GitOps pipeline that deploys and reconciles the workloads.
- The automated test suite and the pre-production environments it runs in.

The following items are out of scope for this engagement:

- The Aurora ledger and fulfilment services, which consume the Order Service
  output. These are scheduled for a separate migration phase.
- The product catalogue database, which is managed by a different team and is
  consumed by the Order Service through a stable API.
- Development of new features. The feature backlog continues in parallel with
  the migration, delivered against the same target architecture.

## 2.3 Objectives and Success Criteria

The migration objectives and their measurable success criteria are defined in
Table 1. Each criterion was agreed with the service owner before work began,
and each is re-verified at the end of this report.

| # | Objective                       | Success criterion                                                                      | Result        |
| - | ------------------------------- | -------------------------------------------------------------------------------------- | ------------- |
| 1 | Reproducible deployments        | A full environment reproducible from a single Git commit, without manual steps         | Met           |
| 2 | Reduced deployment lead time    | Production deployment lead time under 15 minutes, from merged PR to live                | Met (8 min)   |
| 3 | No scheduled downtime           | Zero scheduled-downtime events at cutover; rolling updates only                         | Met           |
| 4 | Automated testing               | Full test suite run against a production-like environment on every pull request        | Met           |
| 5 | Secrets out of the repository   | Zero plaintext secrets in Git; secrets resolved from Key Vault at runtime               | Met           |
| 6 | Documented recovery             | Demonstrated environment recovery under the agreed RTO of four hours                    | Met (2 h 40 m)|

Table 1 — Migration objectives and success criteria.

\newpage

# 3. Current State Assessment

## 3.1 Legacy Architecture Overview

The legacy Order Service ran on twelve Ubuntu 20.04 virtual machines in a
single Azure region. The fleet was split into four logical tiers:

- **Web tier.** Two hosts behind a load balancer, running the `order-api`
  Node.js application on a reverse-proxied port 3000.
- **Worker tier.** Four hosts running the `order-worker` process, which
  consumed orders from a single shared queue and applied pricing rules.
- **Bridge tier.** Four hosts running `order-bridge`, an integration process
  that translated order records into the format consumed by the Aurora ledger.
- **Database tier.** Two hosts running MySQL 8.0 with a master/replica
  configuration, plus one dedicated host for the message queue.

The fleet had grown organically. The asset inventory recorded eight hosts; four
additional hosts were discovered during the assessment, two of which were
serving production traffic. Configuration drift was the rule rather than the
exception: a survey of `order-api` hosts found three different versions of the
application, two different Node.js runtime versions, and one host still running
the previous year's TLS configuration.

## 3.2 Service Inventory

Table 2 summarizes the workloads identified during the assessment. The
"criticality" column reflects the service owner's classification, not the
operational posture at the time of the assessment.

| Workload      | Purpose                              | Language | Hosts | Criticality | Notes                                   |
| ------------- | ------------------------------------ | -------- | ----- | ----------- | --------------------------------------- |
| `order-api`   | Order intake and validation API      | Node.js  | 2     | High        | Reads/writes MySQL, publishes to queue  |
| `order-worker`| Pricing and promotion application    | Go       | 4     | High        | Consumes queue, applies rules           |
| `order-bridge`| Ledger integration                   | Node.js  | 4     | Medium      | Batched translation, retry on failure   |
| MySQL         | Order store                          | —        | 2     | High        | Master/replica, no automated failover   |
| Message queue | Order intake queue                   | —        | 1     | High        | Single node, no clustering              |
| Nginx proxy   | Reverse proxy / TLS termination      | —        | shared| Medium      | Per-host install, drift observed        |

Table 2 — Legacy workload inventory.

## 3.3 Known Limitations and Pain Points

The assessment confirmed the platform risks identified in the initial review
and surfaced two additional issues.

**Manual, sequential deployments.** Deploying `order-api` required logging into
each host, fetching the build artifact, stopping the service, replacing the
files, starting the service, and verifying health. The procedure was performed
twice per deployment because hosts were updated one at a time. The average
recorded deployment took 41 minutes. A parallel-run deployment covering all
three workloads took most of a day and was never fully automated.

**Single points of failure.** The message queue ran on a single host with no
replica. The MySQL replica had never been failed over to in anger. The load
balancer was not configured for health checking against the application, only
against the host TCP port, so a hung application continued to receive traffic.

**Undocumented configuration.** Twelve environment variables were required to
run `order-api`. The mapping between application settings and environment
values existed only in a wiki page that had last been updated two releases
prior. Two of the twelve variables were not present in the wiki at all and were
recovered by inspecting a running host.

**Serialized database lock.** The pricing worker held a coarse-grained
transaction lock for the duration of each pricing batch. Under peak load this
lock serialized writes across the whole order store and was the dominant
contributor to the p99 latency of 1,420 ms measured in the pre-migration
baseline.

These findings are reflected directly in the target architecture in Section 4
and in the risk register in Section 7.

\newpage

# 4. Target Architecture

## 4.1 Design Principles

The target architecture was designed around five principles, agreed with the
platform team before implementation began:

- **Everything as code.** Cluster, workloads, and pipeline configuration are
  version-controlled. No step in provisioning or deployment requires a manual
  action.
- **Git as the source of truth.** Argo CD reconciles the cluster to the state
  described in Git. Manual changes to the cluster are reverted, not blessed.
- **Least privilege by default.** Workload identities are scoped to the
  specific resources they need. No pod runs with cluster-admin or with a
  service principal that can act beyond its role.
- **Observability from day one.** Every workload publishes metrics, logs, and
  traces before it is eligible for production traffic.
- **Rollback by declaration.** A previous good state is always one Git commit
  away, and the rollback path is tested as part of every release.

## 4.2 Cluster Topology

The target environment consists of three AKS clusters, one per environment
(development, staging, production), each running Kubernetes 1.31 and managed
by the same GitOps configuration. All three clusters are identically
provisioned from the same Terraform module, with environment differences
carried only in environment-specific parameter files.

Each cluster runs the following baseline components, installed and upgraded by
the platform pipeline:

- **Ingress.** NGINX ingress controller with TLS terminated by cert-manager.
- **Service mesh.** Istio with automatic mutual TLS (mTLS) between all
  service-to-service traffic.
- **Policy.** Gatekeeper/OPA and Pod Security Admission enforce the platform
  policy set (Section 4.3).
- **Secret resolution.** Azure Key Vault CSI Secrets Store driver, mounted per
  workload through a `SecretProviderClass`.
- **Observability.** Prometheus, Grafana, and Loki, forwarding to Microsoft
  Sentinel for the security-relevant subset of logs.
- **Backup.** Velero with daily cluster snapshots and on-demand restore
  procedures, exercised quarterly.

## 4.3 Networking and Security

Network policy follows a deny-by-default model. Each workload is assigned a
namespace and an explicit `NetworkPolicy` that permits only the required
ingress and egress. The policy set includes the following rules, applied
cluster-wide by Gatekeeper:

- Containers must not run as root, and must declare read-only root
  filesystems where the workload permits.
- Images must be pulled from the approved registry; the `latest` tag is
  forbidden in production.
- Workloads must define CPU and memory resource requests and limits.
- Secrets must be mounted from the Secrets Store driver, never from a plain
  `Secret` manifest containing literal values.

Workload identities use Azure Workload Identity. Each pod is bound to a
managed identity whose role assignments are limited to the resources the
workload consumes, for example the database connection credentials in Key Vault
or the ledger endpoint outbound range. No shared credentials are used between
workloads.

## 4.4 Infrastructure as Code

Cluster and workload infrastructure is defined in Terraform and deployed by the
pipeline. The example below shows the workload identity binding for the
`order-api` deployment:

```terraform
resource "azurerm_kubernetes_cluster" "cluster" {
  name                = "aurora-${var.environment}-cluster"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  kubernetes_version  = "1.31"
  dns_prefix          = "aurora-${var.environment}"

  default_node_pool {
    name       = "default"
    node_count = var.node_count
    vm_size    = var.node_sku
  }

  network_profile {
    network_plugin     = "azure"
    network_policy     = "cilium"
    dns_service_ip     = "10.0.0.10"
    service_cidr       = "10.0.0.0/16"
    load_balancer_sku  = "standard"
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_user_assigned_identity" "order_api" {
  name                = "order-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = var.location
}

resource "azurerm_role_assignment" "order_api_kv" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.order_api.principal_id
}
```

Workloads are described declaratively in Helm charts and synchronized to the
cluster by Argo CD. The chart values for `order-api` are version-pinned and
reviewed through the same pull-request flow as application code.

## 4.5 Observability

Every workload exposes a Prometheus metrics endpoint and ships structured JSON
logs. The pipeline fails a release if a workload does not publish at least the
standard health, latency, and error-rate metrics within five minutes of
deployment. Alert rules cover the standard golden signals plus workload-specific
rules such as queue depth for `order-worker` and rejected-message rate for
`order-bridge`.

\newpage

# 5. Migration Strategy

## 5.1 Strategy Selection

Three strategies were evaluated for the migration:

- **Big-bang.** Decommission the legacy fleet on a single day and switch all
  traffic to the new platform. Rejected: the parallel-run requirement for the
  ledger integration could not be met, and the recovery risk was judged
  unacceptable.
- **Strangler-fig (incremental).** Route a growing percentage of traffic to
  the new platform over several weeks. Rejected at the workload level: the
  shared MySQL dependency meant that partial traffic could not be isolated
  without a data layer that did not exist.
- **Parallel-run with cutover.** Run both platforms in parallel, duplicate
  orders to both, reconcile results, and switch production traffic in a
  single controlled cutover once reconciliation shows parity. Selected.

The parallel-run strategy was chosen because it satisfied the zero-scheduled-
downtime objective while retaining a full rollback path through the entire
migration. It required a duplicate of the inbound order stream, which the
`order-bridge` team delivered as a small addition to the integration layer.

## 5.2 Migration Phases

The migration was executed in six phases. Table 3 lists each phase, its
deliverable, and the exit criterion that had to be met before the next phase
began.

| Phase | Name                    | Deliverable                                        | Exit criterion                                      |
| ----- | ----------------------- | -------------------------------------------------- | --------------------------------------------------- |
| P0    | Foundation              | Shared Terraform module, pipeline, three clusters  | Staging cluster reproducible from a fresh branch    |
| P1    | Workload lift           | `order-api`, `order-worker`, `order-bridge` on AKS | All workloads healthy in staging for five days      |
| P2    | Parallel run           | Order duplication and reconciliation               | Reconciliation at 100% for three consecutive days   |
| P3    | Cutover                 | Production traffic switched to AKS                 | Zero-scheduled-downtime; p99 under 500 ms at peak   |
| P4    | Decommission            | Legacy fleet retired                               | No production dependency remains on legacy hosts    |
| P5    | Hardening               | Security findings remediated, runbooks verified    | Critical findings closed; restore drill passed      |

Table 3 — Migration phases, deliverables, and exit criteria.

## 5.3 Workstreams

The migration was run as four parallel workstreams, each with a single named
owner:

- **Platform workstream** (P0, P5): cluster provisioning, policy, and
  observability. Owned by the platform engineering lead.
- **Application workstream** (P1, P2): containerization of the three
  workloads, chart authoring, and reconciliation scripts. Owned by the
  service owner.
- **Data workstream** (P2, P3): order duplication, reconciliation, and the
  cutover checklist. Owned by the integration team lead.
- **Security workstream** (P0, P5): image scanning, policy authoring, and
  the pre-cutover security assessment. Owned by the security engineer.

Workstreams reported against the phase exit criteria rather than against
calendar dates. The timeline in Section 9 therefore reflects actual durations,
not estimates.

## 5.4 Data Migration Approach

Order records were migrated by replay, not by copy. During the parallel-run
phase the legacy platform continued to be the system of record. The new
platform consumed the same order stream, applied the same rules, and wrote to
its own store. A reconciliation job compared the two stores hourly on a
sample of order identifiers and daily in full.

The replay approach had two advantages over a point-in-time copy. It exercised
the target platform continuously under real traffic before cutover, and it
produced a reconciliation report that the service owner could sign off before
production traffic was switched.

The MySQL master/replica pair was not migrated. The order store was rebuilt
from the replay on the target platform, which also removed the legacy
serialized-lock behaviour that had constrained latency (see Section 3.3).

\newpage

# 6. Rollout and Testing

## 6.1 Testing Strategy

Testing followed a shift-left model against the production-like staging
environment. Every pull request triggered the full pipeline: unit tests, image
build, vulnerability scan, deployment to staging, and the end-to-end test
suite. A release was only eligible for production after the staging run was
green and the scan report contained no open critical or high findings.

The test suite covers three layers:

- **Unit tests** for pricing rules and validation logic, run on every commit.
- **Contract tests** against the product catalogue API and the ledger
  endpoint, run on every pull request.
- **End-to-end tests** exercising the full order flow in staging, including
  the duplicate-stream reconciliation, run nightly and on demand before
  cutover.

## 6.2 Performance and Load Results

A load test reproducing peak-season traffic was run against the staging
environment one week before cutover. The test ramped to 11,000 orders over one
hour and sustained the peak for two hours. Table 4 compares the results with
the pre-migration baseline.

| Metric                     | Legacy baseline | Target platform | Change      |
| -------------------------- | --------------- | --------------- | ----------- |
| Throughput                 | 11,000 orders/h | 11,000 orders/h | Unchanged   |
| p50 latency                | 340 ms          | 82 ms           | −76%        |
| p99 latency                | 1,420 ms        | 214 ms          | −85%        |
| Error rate                 | 0.4%            | 0.02%           | −95%        |
| Peak CPU (web tier)        | 88%             | 54%             | −34 points  |
| Peak memory (web tier)     | 6.2 GB / host   | 1.9 GB / pod    | —           |

Table 4 — Load test results versus legacy baseline.

The dominant latency improvement is attributed to the removal of the
serialized database lock in the pricing worker (Section 3.3), which the
target platform replaced with per-order processing. The full benchmark
tooling and methodology are documented in the repository `loadtest/`
directory and are reproducible on demand.

The benchmark output below is representative of the sustained peak segment:

```text
orders_completed_total           11,000   rate=3.06/s
order_pricing_seconds_sum       22,407.1  p50=0.082 p99=0.214
order_queue_depth                38       max=41
order_rejected_total             3        rate=0.0008/s
http_requests_total              88,312   error_rate=0.02%
```

## 6.3 Canary and Smoke Procedures

Production releases use a two-step rollout. The first step deploys to a single
canary node and holds for five minutes while health, error-rate, and latency
alerts are checked. The second step completes the rolling update. The canary
step is enforced by the pipeline: a release that trips an alert is rolled back
automatically to the previous commit.

The smoke check run after each production deployment is recorded in the
pipeline logs and covers the three workloads plus the ingress path:

```bash
# smoke check: order-api
curl -fsS -H "Host: orders.aurora.internal" \
  https://ingress.aurora.internal/healthz | jq -e '.status == "ok"'

# smoke check: order-worker (queue drains)
kubectl -n order exec deploy/order-worker -- \
  ./bin/check --queue-depth-max 200

# smoke check: order-bridge (batch advances)
kubectl -n order exec deploy/order-bridge -- \
  ./bin/check --last-sync-age 5m
```

\newpage

# 7. Risks and Mitigations

The risk register below was maintained throughout the migration and reviewed
at each phase gate. The "status" column reflects the position at the time of
this report.

| #  | Risk                                                       | Likelihood | Impact | Mitigation                                                             | Status   |
| -- | ---------------------------------------------------------- | ---------- | ------ | ---------------------------------------------------------------------- | -------- |
| R1 | Order duplication introduces duplicate records              | Medium     | High   | Reconciliation job with full daily comparison; duplicate key in store  | Closed   |
| R2 | Cutover exceeds the zero-downtime window                    | Medium     | High   | Parallel-run parity gate; rehearsed cutover checklist                  | Closed   |
| R3 | Pricing rules diverge between platforms                      | Medium     | High   | Shared rule package; per-order diff in reconciliation report           | Closed   |
| R4 | Secrets exposed in Git or logs                             | Low        | High   | Gatekeeper policy; scan in pipeline; vault-only secret resolution      | Closed   |
| R5 | Legacy hosts still receive traffic after decommission        | Medium     | Medium | Ingress ACL on legacy fleet; traffic audit for two weeks               | Closed   |
| R6 | Image registry downtime blocks releases                    | Low        | Medium | Registry replicated across regions; cached base images                 | Accepted |
| R7 | Team skill gap on Kubernetes operations                    | Medium     | Low    | Pairing sessions; runbooks in the repository; staged permissions       | Active   |

Table 5 — Migration risk register.

Two findings from the pre-migration security assessment are noted explicitly.
The CIS benchmark scan reported the legacy hosts as failing the certificate
and key rotation controls; the target platform enforces rotation by policy and
the finding is closed. The dependency scan reported a high-severity
vulnerability in the legacy `order-api` image; the container image rebuilt
during the migration incorporates the fix and the finding is closed.

\newpage

# 8. Cost Analysis

Table 6 compares the monthly infrastructure cost of the legacy platform with
the target platform at comparable capacity, using list prices current at the
time of analysis. Costs are in Canadian dollars and exclude the database and
queue services, which are shared and unchanged.

| Item                    | Legacy platform | Target platform |
| ----------------------- | --------------- | --------------- |
| Compute (12 × D4s v3)   | $1,944          | —               |
| Compute (AKS nodes)     | —               | $1,188          |
| Managed disk            | $388            | $312            |
| Load balancer           | $72             | $96             |
| Managed identity / KMS  | —               | $18             |
| Monitoring and logs     | $144            | $126            |
| **Monthly total**       | **$2,548**      | **$1,740**      |

Table 6 — Monthly infrastructure cost comparison.

The target platform is 31% cheaper at the capacity tested. The analysis does
not include further right-sizing, which the observability data now makes
visible: the worker node pool is underutilized outside peak season and is a
candidate for scale-to-zero scheduling in the follow-on phase.

\newpage

# 9. Timeline and Milestones

Table 7 records the planned milestones against actual completion. The
migration ran from January 2026 to May 2026.

| Milestone                 | Planned     | Actual      | Variance |
| ------------------------- | ----------- | ----------- | -------- |
| Assessment complete       | 16 Jan 2026 | 23 Jan 2026 | +1 week  |
| Foundation (P0)           | 20 Feb 2026 | 27 Feb 2026 | +1 week  |
| Workload lift (P1)        | 27 Mar 2026 | 10 Apr 2026 | +2 weeks |
| Parallel run (P2)         | 1 May 2026  | 8 May 2026  | +1 week  |
| Cutover (P3)              | 15 May 2026 | 15 May 2026 | On time  |
| Decommission (P4)         | 22 May 2026 | 22 May 2026 | On time  |
| Hardening and closeout    | 29 May 2026 | 29 May 2026 | On time  |

Table 7 — Milestones and variance.

The two-week variance on the workload lift phase was caused by the dependency
scan finding in the `order-api` image (Section 7), which was resolved within
the phase rather than deferred. No milestone after cutover slipped.

\newpage

# 10. Rollback and Contingency

## 10.1 Rollback Triggers

Rollback of a release is triggered automatically when the canary step trips an
alert, and manually when any of the following conditions is observed during a
rollout:

- Error rate above 1% for more than two consecutive minutes.
- p99 latency above 500 ms for more than five minutes at peak.
- Reconciliation parity below 99.9% for more than one hour after cutover.

## 10.2 Rollback Procedure

Because Git is the source of truth, rollback is a declaration, not a
reconstruction. Reverting the offending commit and letting Argo CD reconcile
restores the previous state. The procedure is tested on every staging release
and was exercised once in production during the hardening phase without
incident.

For the cutover specifically, the contingency is the legacy fleet itself. The
legacy hosts were retained, powered on, and network-isolated from production
traffic for two weeks after cutover. Had the cutover failed, traffic would have
been re-pointed to the legacy ingress in under ten minutes. The retention
period ended on 29 May 2026 after the reconciliation report for the preceding
two weeks showed full parity.

\newpage

# 11. Conclusion and Recommendations

The migration achieved all six success criteria defined in Section 2.3. The
Order Service now runs on a platform that is reproducible from Git, deploys in
minutes rather than days, is observability-native, and carries no plaintext
secrets. The decommissioned legacy fleet removed four hosts that were not in
the asset inventory and closed two open security findings.

The following recommendations are proposed for the next phases of the Aurora
platform roadmap:

1. **Migrate the ledger and fulfilment services** using the same parallel-run
   pattern. The pattern is now documented and rehearsed, and the ledger team
   has requested a copy of the reconciliation tooling.
2. **Right-size the worker node pool.** Observability shows sustained low
   utilization outside peak season. A scale-to-zero schedule is expected to
   reduce the worker pool cost by a further 40–50%.
3. **Automate the certificate rotation drill.** The hardening phase
   demonstrated rotation by policy; the drill should be added to the quarterly
   schedule alongside the restore exercise.
4. **Adopt the staging pipeline for the remaining product lines.** The
   shift-left test model has reduced the mean time to detect a regression from
   days to the duration of a pull-request build.

The migration is complete. The platform roadmap continues, and the tooling
described in this report is the basis on which the next phases will be built.

\newpage

# Appendix A. Service Inventory Detail

Table A.1 lists the final workload inventory on the target platform, including
resource requests and limits as deployed.

| Workload      | Replicas | CPU request/limit | Memory request/limit | Image                    | Channel |
| ------------- | -------- | ----------------- | -------------------- | ------------------------ | ------- |
| `order-api`   | 3        | 500m / 1           | 512 Mi / 1 Gi        | `registry.aurora.io/order-api:v3.4.1` | stable  |
| `order-worker`| 2        | 750m / 1.5         | 768 Mi / 1.5 Gi      | `registry.aurora.io/order-worker:v2.9.0` | stable  |
| `order-bridge`| 2        | 250m / 500m        | 256 Mi / 512 Mi      | `registry.aurora.io/order-bridge:v1.8.3` | stable  |
| Velero        | 1        | 500m / 1           | 512 Mi / 1 Gi        | `velero/velero:v1.14.2` | infra   |
| Gatekeeper    | 3        | 500m / 1           | 512 Mi / 1 Gi        | `openpolicyagent/gatekeeper:v3.17.1` | infra   |

Table A.1 — Target platform workload inventory.

\newpage

# Appendix B. Operational Runbooks

## B.1 Environment Recovery

Recovery of a full environment from a failed state is demonstrated quarterly.
The procedure assumes the cluster has been rebuilt from Terraform:

```bash
# 1. restore cluster configuration
git checkout tags/environment/2026.05
kubectl apply -f ./cluster/    # or argo app sync

# 2. restore secrets from Key Vault (no secret data is restored from disk)
kubectl -n order get secretproviderclass order-api-secrets -o yaml

# 3. reconcile workloads
argocd app sync order-service --prune

# 4. verify recovery
./scripts/verify-environment.sh staging
```

## B.2 Release Rollback

```bash
# find the offending commit
git log --oneline -5 -- workload/order-api

# revert and reconcile
git revert <commit>
argocd app sync order-service --prune

# confirm health after reconciliation
kubectl -n order rollout status deploy/order-api --timeout=5m
```

\newpage

# Appendix C. Glossary

| Term                   | Definition                                                          |
| ---------------------- | ------------------------------------------------------------------- |
| AKS                    | Azure Kubernetes Service, the managed Kubernetes platform used here |
| Argo CD                | GitOps continuous delivery tool that reconciles clusters to Git     |
| Canary                 | A partial rollout to a subset of nodes to verify a release          |
| CSI Secrets Store      | Kubernetes driver that mounts secrets from Azure Key Vault          |
| GitOps                 | Operating model where Git is the source of truth for cluster state  |
| Gatekeeper             | Policy controller using the OPA constraint framework                |
| mTLS                   | Mutual TLS, encryption of service-to-service traffic in both directions |
| Reconciliation         | Process of comparing two data sources to confirm agreement          |
| Strangler-fig          | Incremental migration pattern of gradually replacing components     |
| Workload Identity      | Azure managed identity bound to a Kubernetes pod                    |
