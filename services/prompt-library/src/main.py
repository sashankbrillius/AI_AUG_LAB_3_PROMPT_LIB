import hashlib
import json
import logging
import os
import random
import re
import time
from datetime import datetime
from typing import Dict, List, Optional

import yaml
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel

from shared.telemetry import (
    CATEGORY_USAGE,
    EXPORT_OPS,
    PROMPT_QUALITY,
    PROMPT_TESTS,
    TOKEN_ESTIMATE,
    prom_middleware,
)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("prompt-library")

SERVICE = "prompt-library"

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
RCA_MODE = os.environ.get("RCA_MODE", "mock").lower()
PROMPT_QUALITY_THRESHOLD = float(os.environ.get("PROMPT_QUALITY_THRESHOLD", "0.6"))
EXPORT_FORMAT = os.environ.get("EXPORT_FORMAT", "yaml").lower()

PROMPTS_TOTAL = Gauge("prompts_library_total", "Total prompts in library", ["service"])
PROMPTS_BY_CATEGORY = Gauge("prompts_by_category", "Prompts per category", ["service", "category"])
QUALITY_THRESHOLD_GAUGE = Gauge("prompt_quality_threshold_info", "Current quality threshold", ["service"])
TESTS_RUN_TOTAL = Gauge("prompt_tests_run_total_gauge", "Total test runs executed", ["service"])

app = FastAPI(title="SmartDine DevOps Prompt Library", version="1.0")
app.middleware("http")(prom_middleware(SERVICE))

_tests_run_count = 0


PROMPT_LIBRARY: Dict[str, Dict] = {
    "debug-log-analysis": {
        "id": "debug-log-analysis",
        "category": "debugging",
        "name": "Log Analysis Debugger",
        "description": "Analyze application logs to identify error patterns, root causes, and affected components",
        "prompt": (
            "Role: You are a senior site reliability engineer specializing in log analysis.\n"
            "Task: Analyze the following application logs and identify error patterns, their root causes, and affected components.\n"
            "Input: {log_data}\n"
            "Constraints: Focus only on ERROR and WARN entries. Do not speculate beyond what the logs show. Identify correlations between timestamps.\n"
            "Output Format: JSON with fields: error_pattern, root_cause, affected_components (list), severity (critical/high/medium/low), confidence (0-1)"
        ),
        "variables": ["log_data"],
        "tags": ["logs", "errors", "patterns"],
    },
    "debug-error-triage": {
        "id": "debug-error-triage",
        "category": "debugging",
        "name": "Error Triage Classifier",
        "description": "Classify and prioritize errors by impact, urgency, and blast radius",
        "prompt": (
            "Role: You are an incident triage specialist for a restaurant technology platform.\n"
            "Task: Classify this error by impact level, urgency, and blast radius.\n"
            "Input: {error_message}\n"
            "Constraints: Impact must be one of: revenue-blocking, degraded-experience, internal-only, cosmetic. "
            "Urgency must be: immediate, within-1-hour, next-business-day, backlog.\n"
            "Output Format: JSON with fields: impact, urgency, blast_radius (list of affected services), recommended_action, escalation_needed (boolean)"
        ),
        "variables": ["error_message"],
        "tags": ["triage", "prioritization", "errors"],
    },
    "debug-dependency-trace": {
        "id": "debug-dependency-trace",
        "category": "debugging",
        "name": "Dependency Chain Tracer",
        "description": "Trace error propagation through service dependency chains",
        "prompt": (
            "Role: You are a distributed systems debugger.\n"
            "Task: Trace how this error propagated through the service dependency chain and identify the originating service.\n"
            "Input: {trace_data}\n"
            "Constraints: Map only confirmed dependencies from the trace data. Mark uncertain connections as 'inferred'. "
            "Order the chain chronologically.\n"
            "Output Format: JSON with fields: origin_service, propagation_chain (list of {service, timestamp, error_type}), "
            "total_services_affected (int), cascade_duration_seconds (int)"
        ),
        "variables": ["trace_data"],
        "tags": ["dependencies", "tracing", "cascade"],
    },
    "debug-performance-bottleneck": {
        "id": "debug-performance-bottleneck",
        "category": "debugging",
        "name": "Performance Bottleneck Identifier",
        "description": "Identify performance bottlenecks from metrics and latency data",
        "prompt": (
            "Role: You are a performance engineer analyzing a slow API endpoint.\n"
            "Task: Identify the performance bottleneck from these metrics and suggest specific optimizations.\n"
            "Input: {metrics_data}\n"
            "Constraints: Focus on the top 3 bottlenecks by latency contribution. Quantify each bottleneck's percentage of total latency. "
            "Suggestions must be actionable within 1 sprint.\n"
            "Output Format: JSON with fields: bottlenecks (list of {component, latency_ms, percentage, optimization}), "
            "total_latency_ms, target_latency_ms, estimated_improvement_percent"
        ),
        "variables": ["metrics_data"],
        "tags": ["performance", "latency", "optimization"],
    },
    "rca-incident-timeline": {
        "id": "rca-incident-timeline",
        "category": "rca",
        "name": "Incident Timeline Builder",
        "description": "Construct a minute-by-minute incident timeline from mixed log and alert data",
        "prompt": (
            "Role: You are an incident commander reconstructing a production incident.\n"
            "Task: Build a chronological incident timeline from these logs and alerts.\n"
            "Input: {incident_data}\n"
            "Constraints: Use only timestamps from the data. Mark the detection time, escalation time, and resolution time. "
            "Calculate TTD (time to detect), TTR (time to resolve), and TTM (time to mitigate).\n"
            "Output Format: JSON with fields: timeline (list of {timestamp, event, source, severity}), "
            "ttd_minutes, ttr_minutes, ttm_minutes, total_duration_minutes"
        ),
        "variables": ["incident_data"],
        "tags": ["timeline", "incident", "chronology"],
    },
    "rca-root-cause": {
        "id": "rca-root-cause",
        "category": "rca",
        "name": "Root Cause Identifier",
        "description": "Identify the root cause of an incident using the 5 Whys technique",
        "prompt": (
            "Role: You are a root cause analysis specialist.\n"
            "Task: Apply the 5 Whys technique to identify the root cause of this incident.\n"
            "Input: {incident_summary}\n"
            "Constraints: Each 'why' must be supported by evidence from the input data. "
            "Do not speculate beyond available evidence. Distinguish between proximate cause and root cause.\n"
            "Output Format: JSON with fields: proximate_cause, five_whys (list of {level, question, answer, evidence}), "
            "root_cause, category (config-change/code-bug/capacity/external-dependency/human-error)"
        ),
        "variables": ["incident_summary"],
        "tags": ["root-cause", "5-whys", "analysis"],
    },
    "rca-blast-radius": {
        "id": "rca-blast-radius",
        "category": "rca",
        "name": "Blast Radius Mapper",
        "description": "Map the blast radius of an incident across services, users, and revenue",
        "prompt": (
            "Role: You are a business impact analyst for a technology platform.\n"
            "Task: Map the complete blast radius of this incident across services, users, and revenue.\n"
            "Input: {incident_metrics}\n"
            "Constraints: Quantify impact in dollars where possible. Distinguish between direct and indirect impact. "
            "Include only confirmed affected services.\n"
            "Output Format: JSON with fields: affected_services (list of {name, impact_type, severity}), "
            "users_affected (int), revenue_impact_usd (float), direct_impact, indirect_impact, sla_breaches (list)"
        ),
        "variables": ["incident_metrics"],
        "tags": ["blast-radius", "impact", "business"],
    },
    "rca-remediation-plan": {
        "id": "rca-remediation-plan",
        "category": "rca",
        "name": "Remediation Plan Generator",
        "description": "Generate a prioritized remediation plan with immediate, short-term, and long-term actions",
        "prompt": (
            "Role: You are a technical program manager creating a remediation plan.\n"
            "Task: Generate a prioritized remediation plan for this incident with immediate, short-term, and long-term actions.\n"
            "Input: {rca_findings}\n"
            "Constraints: Immediate actions must be completable within 4 hours. Short-term within 2 weeks. Long-term within 1 quarter. "
            "Each action must have a clear owner role and success criteria.\n"
            "Output Format: JSON with fields: immediate (list of {action, owner_role, success_criteria}), "
            "short_term (list), long_term (list), estimated_total_effort_days (int)"
        ),
        "variables": ["rca_findings"],
        "tags": ["remediation", "action-items", "planning"],
    },
    "infra-architecture-explainer": {
        "id": "infra-architecture-explainer",
        "category": "infra-explanation",
        "name": "Architecture Diagram Explainer",
        "description": "Explain infrastructure architecture from configuration files in plain language",
        "prompt": (
            "Role: You are a cloud architect explaining infrastructure to a new team member.\n"
            "Task: Explain this infrastructure configuration in plain language, covering what each component does and how they connect.\n"
            "Input: {config_file}\n"
            "Constraints: Use non-jargon language where possible. Explain WHY each component exists, not just WHAT it is. "
            "Identify single points of failure.\n"
            "Output Format: JSON with fields: components (list of {name, purpose, connects_to}), "
            "data_flow (list of steps), single_points_of_failure (list), overall_purpose"
        ),
        "variables": ["config_file"],
        "tags": ["architecture", "explanation", "onboarding"],
    },
    "infra-config-audit": {
        "id": "infra-config-audit",
        "category": "infra-explanation",
        "name": "Configuration Audit Reviewer",
        "description": "Audit infrastructure configuration for security, performance, and reliability issues",
        "prompt": (
            "Role: You are a DevOps security auditor reviewing infrastructure configuration.\n"
            "Task: Audit this configuration for security vulnerabilities, performance issues, and reliability risks.\n"
            "Input: {config_content}\n"
            "Constraints: Rate each finding as critical/high/medium/low. Only flag issues you can confirm from the config. "
            "Reference specific lines or settings. Provide the fix for each issue.\n"
            "Output Format: JSON with fields: findings (list of {issue, severity, line_or_setting, risk, fix}), "
            "overall_risk_level, passing_checks (list), score_out_of_100 (int)"
        ),
        "variables": ["config_content"],
        "tags": ["audit", "security", "configuration"],
    },
    "infra-capacity-planner": {
        "id": "infra-capacity-planner",
        "category": "infra-explanation",
        "name": "Capacity Planning Advisor",
        "description": "Analyze current resource usage and project capacity needs for growth",
        "prompt": (
            "Role: You are a capacity planning engineer for a growing restaurant chain.\n"
            "Task: Analyze current resource utilization and project capacity needs for the next growth milestone.\n"
            "Input: {resource_metrics}\n"
            "Constraints: Base projections on the provided growth rate. Flag resources that will hit 80% utilization within the projection window. "
            "Cost estimates must use current cloud pricing.\n"
            "Output Format: JSON with fields: current_utilization (dict of resource: percent), "
            "projected_needs (dict), bottleneck_resources (list), scaling_recommendations (list of {resource, action, timeline, cost_delta_monthly})"
        ),
        "variables": ["resource_metrics"],
        "tags": ["capacity", "scaling", "planning"],
    },
    "infra-cost-analyzer": {
        "id": "infra-cost-analyzer",
        "category": "infra-explanation",
        "name": "Cloud Cost Analyzer",
        "description": "Analyze cloud spending patterns and identify optimization opportunities",
        "prompt": (
            "Role: You are a FinOps engineer optimizing cloud costs.\n"
            "Task: Analyze this cloud billing data and identify the top cost optimization opportunities.\n"
            "Input: {billing_data}\n"
            "Constraints: Focus on savings of $100+/month. Calculate annual impact. "
            "Only suggest changes that do not reduce reliability below 99.9% uptime.\n"
            "Output Format: JSON with fields: total_monthly_spend, top_optimizations (list of {resource, current_cost, optimized_cost, savings_monthly, action, risk_level}), "
            "total_monthly_savings, annual_savings, savings_percentage"
        ),
        "variables": ["billing_data"],
        "tags": ["cost", "finops", "optimization"],
    },
    "script-monitoring-setup": {
        "id": "script-monitoring-setup",
        "category": "script-generation",
        "name": "Monitoring Setup Script Generator",
        "description": "Generate monitoring configuration scripts for Prometheus, Grafana, or Datadog",
        "prompt": (
            "Role: You are a monitoring engineer setting up observability for a microservices platform.\n"
            "Task: Generate a complete monitoring setup script for the specified tool and services.\n"
            "Input: {monitoring_requirements}\n"
            "Constraints: Script must be idempotent (safe to run multiple times). Include health check verification. "
            "Add comments explaining each section. Use environment variables for configurable values.\n"
            "Output Format: JSON with fields: script (string — the full bash script), "
            "config_files (list of {filename, content}), verification_commands (list), estimated_setup_minutes (int)"
        ),
        "variables": ["monitoring_requirements"],
        "tags": ["monitoring", "prometheus", "scripts"],
    },
    "script-deployment-automation": {
        "id": "script-deployment-automation",
        "category": "script-generation",
        "name": "Deployment Automation Script",
        "description": "Generate deployment scripts with rollback capability and health checks",
        "prompt": (
            "Role: You are a release engineer creating a deployment script with built-in safety checks.\n"
            "Task: Generate a deployment script for this service with pre-deploy checks, rollback capability, and post-deploy verification.\n"
            "Input: {deployment_spec}\n"
            "Constraints: Must include rollback trigger conditions. Health check must pass before marking deployment complete. "
            "Script must exit non-zero on any failure. Log every step with timestamps.\n"
            "Output Format: JSON with fields: script (string — the full bash script), "
            "rollback_script (string), pre_checks (list), post_checks (list), estimated_deploy_minutes (int)"
        ),
        "variables": ["deployment_spec"],
        "tags": ["deployment", "automation", "rollback"],
    },
    "script-backup-restore": {
        "id": "script-backup-restore",
        "category": "script-generation",
        "name": "Backup & Restore Script Generator",
        "description": "Generate database backup and restore scripts with verification",
        "prompt": (
            "Role: You are a database reliability engineer creating backup automation.\n"
            "Task: Generate backup and restore scripts for this database with integrity verification.\n"
            "Input: {database_spec}\n"
            "Constraints: Backup must include integrity checksum. Restore must verify checksum before applying. "
            "Include retention policy (keep last N backups). Script must handle both full and incremental backups.\n"
            "Output Format: JSON with fields: backup_script (string), restore_script (string), "
            "verify_script (string), cron_schedule, retention_policy, estimated_backup_size_gb (float)"
        ),
        "variables": ["database_spec"],
        "tags": ["backup", "database", "restore"],
    },
    "script-alerting-rules": {
        "id": "script-alerting-rules",
        "category": "script-generation",
        "name": "Alerting Rules Generator",
        "description": "Generate Prometheus alerting rules based on SLO definitions",
        "prompt": (
            "Role: You are an SRE defining alerting rules based on service level objectives.\n"
            "Task: Generate Prometheus alerting rules that detect SLO violations for these services.\n"
            "Input: {slo_definitions}\n"
            "Constraints: Each alert must have a clear threshold, evaluation window, and severity. "
            "Include burn-rate alerts for error budget consumption. Avoid alert fatigue — no more than 5 rules per service.\n"
            "Output Format: JSON with fields: alert_rules (list of {name, expr, for_duration, severity, summary, runbook_url}), "
            "total_rules (int), estimated_monthly_alerts (int)"
        ),
        "variables": ["slo_definitions"],
        "tags": ["alerting", "slo", "prometheus"],
    },
    "postmortem-blameless-writeup": {
        "id": "postmortem-blameless-writeup",
        "category": "postmortems",
        "name": "Blameless Postmortem Writer",
        "description": "Generate a blameless postmortem document from incident data",
        "prompt": (
            "Role: You are a blameless postmortem facilitator following Google's SRE postmortem guidelines.\n"
            "Task: Write a complete blameless postmortem document from this incident data.\n"
            "Input: {incident_data}\n"
            "Constraints: Never name individuals — use roles (e.g., 'on-call engineer'). Focus on system failures, not human failures. "
            "Every action item must be actionable and have a priority (P0-P3). Include what went well.\n"
            "Output Format: JSON with fields: title, date, severity, duration_minutes, summary, "
            "impact (users_affected, revenue_loss), timeline (list), root_cause, contributing_factors (list), "
            "what_went_well (list), action_items (list of {action, priority, owner_role, due_date_relative})"
        ),
        "variables": ["incident_data"],
        "tags": ["postmortem", "blameless", "documentation"],
    },
    "postmortem-action-items": {
        "id": "postmortem-action-items",
        "category": "postmortems",
        "name": "Action Item Extractor",
        "description": "Extract and prioritize action items from a postmortem discussion",
        "prompt": (
            "Role: You are a technical program manager tracking postmortem follow-ups.\n"
            "Task: Extract actionable items from this postmortem discussion and prioritize them by risk reduction impact.\n"
            "Input: {postmortem_notes}\n"
            "Constraints: Each action must be SMART (Specific, Measurable, Achievable, Relevant, Time-bound). "
            "Group by category: detection, prevention, mitigation, process. Maximum 10 items.\n"
            "Output Format: JSON with fields: action_items (list of {id, action, category, priority, owner_role, "
            "effort_days, risk_reduction_score, due_date_relative, success_metric}), total_effort_days (int)"
        ),
        "variables": ["postmortem_notes"],
        "tags": ["action-items", "tracking", "prioritization"],
    },
    "postmortem-slo-impact": {
        "id": "postmortem-slo-impact",
        "category": "postmortems",
        "name": "SLO Impact Report Generator",
        "description": "Calculate the SLO and error budget impact of an incident",
        "prompt": (
            "Role: You are an SRE calculating the SLO impact of a production incident.\n"
            "Task: Calculate how this incident affected each SLO and the remaining error budget.\n"
            "Input: {incident_metrics}\n"
            "Constraints: Use the standard 30-day rolling window for error budget. Show both absolute and percentage impact. "
            "Flag any SLO that dropped below its target. Include time to recover the burned budget at normal error rates.\n"
            "Output Format: JSON with fields: slo_impacts (list of {slo_name, target, current_value, budget_burned_percent, "
            "budget_remaining_percent, recovery_days}), worst_affected_slo, total_budget_burned_minutes, "
            "recommendation (continue-deploying/slow-down/freeze-deployments)"
        ),
        "variables": ["incident_metrics"],
        "tags": ["slo", "error-budget", "impact"],
    },
    "postmortem-comms-template": {
        "id": "postmortem-comms-template",
        "category": "postmortems",
        "name": "Incident Communication Template",
        "description": "Generate stakeholder communications for different audiences during and after incidents",
        "prompt": (
            "Role: You are an incident communication manager for a customer-facing platform.\n"
            "Task: Generate incident communications for three audiences: engineering team, executive leadership, and affected customers.\n"
            "Input: {incident_details}\n"
            "Constraints: Engineering message includes technical details. Executive message focuses on business impact and timeline. "
            "Customer message must be empathetic, avoid blame, and include compensation if applicable. Keep customer message under 200 words.\n"
            "Output Format: JSON with fields: engineering_update (string), executive_summary (string), "
            "customer_notification (string), status_page_update (string), follow_up_schedule (list of {audience, timing, content_focus})"
        ),
        "variables": ["incident_details"],
        "tags": ["communication", "stakeholders", "messaging"],
    },
}

TEST_SCENARIOS: Dict[str, Dict] = {
    "scenario-debugging": {
        "id": "scenario-debugging",
        "category": "debugging",
        "name": "SmartDine Payment Timeout Debugging",
        "description": "Payment service returning 504 Gateway Timeout errors during dinner rush",
        "context": (
            "Service: payment-service v2.8.1\n"
            "Error: 504 Gateway Timeout on POST /api/payments\n"
            "Frequency: 23 errors in last 5 minutes (was 0 before 19:15)\n"
            "Logs:\n"
            "19:15:02 [WARN] payment-service: db_pool active=8/10, queued=3\n"
            "19:15:15 [ERROR] payment-service: ConnectionPoolExhausted: timeout waiting for connection (5000ms)\n"
            "19:15:22 [ERROR] order-service: upstream dependency payment-service returned 504\n"
            "19:15:30 [WARN] inventory-service: reservation lock timeout — payment confirmation pending\n"
            "19:15:45 [ERROR] nginx: upstream timed out (110: Connection timed out) while connecting to payment-service"
        ),
        "expected_keywords": ["connection pool", "db_pool", "timeout", "cascade", "payment-service"],
    },
    "scenario-rca": {
        "id": "scenario-rca",
        "category": "rca",
        "name": "SmartDine Deployment Rollback Incident",
        "description": "Deployment D-4721 caused cascading failure requiring emergency rollback",
        "context": (
            "Incident: INC-0198 (P1, 8-minute duration)\n"
            "Deployment: D-4721, payment-service v2.8.1, change PAY-88\n"
            "Change: db_pool_max reduced from 100 to 10\n"
            "Impact: 47 failed orders, $1,400 revenue loss, 4 services affected\n"
            "Timeline:\n"
            "19:14:50 — Deployment D-4721 started\n"
            "19:15:05 — v2.8.1 live with db_pool_max=10\n"
            "19:16:00 — First ERROR: connection pool timeout\n"
            "19:16:30 — Circuit breaker OPEN\n"
            "19:17:00 — Cascade to order-service\n"
            "19:21:35 — Rollback initiated (D-4722)\n"
            "19:23:25 — Incident resolved, all alerts cleared"
        ),
        "expected_keywords": ["db_pool_max", "rollback", "D-4721", "cascade", "circuit breaker"],
    },
    "scenario-infra": {
        "id": "scenario-infra",
        "category": "infra-explanation",
        "name": "SmartDine Kubernetes Config Review",
        "description": "Review and explain SmartDine's Kubernetes deployment configuration",
        "context": (
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: payment-service\n"
            "  namespace: smartdine-prod\n"
            "spec:\n"
            "  replicas: 3\n"
            "  strategy:\n"
            "    type: RollingUpdate\n"
            "    rollingUpdate:\n"
            "      maxSurge: 1\n"
            "      maxUnavailable: 0\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            "      - name: payment-service\n"
            "        image: smartdine/payment:v2.8.0\n"
            "        resources:\n"
            "          requests: {cpu: 250m, memory: 512Mi}\n"
            "          limits: {cpu: 1000m, memory: 1Gi}\n"
            "        readinessProbe:\n"
            "          httpGet: {path: /health, port: 8080}\n"
            "          initialDelaySeconds: 10\n"
            "          periodSeconds: 5"
        ),
        "expected_keywords": ["replicas", "rolling update", "readiness", "resources", "payment-service"],
    },
    "scenario-script": {
        "id": "scenario-script",
        "category": "script-generation",
        "name": "SmartDine Monitoring Setup",
        "description": "Set up Prometheus monitoring for SmartDine's 4 core services",
        "context": (
            "Services to monitor:\n"
            "  - payment-service (port 8080, critical, SLO 99.95%)\n"
            "  - order-service (port 8081, critical, SLO 99.9%)\n"
            "  - inventory-service (port 8082, high, SLO 99.5%)\n"
            "  - notification-service (port 8083, medium, SLO 99.0%)\n"
            "Requirements:\n"
            "  - Prometheus scrape interval: 15s for critical, 30s for others\n"
            "  - Alert on error rate > 1% for critical services\n"
            "  - Alert on p99 latency > 2s\n"
            "  - Dashboard with request rate, error rate, latency percentiles\n"
            "  - PagerDuty integration for P1 alerts"
        ),
        "expected_keywords": ["scrape_interval", "alert", "error_rate", "latency", "prometheus"],
    },
    "scenario-postmortem": {
        "id": "scenario-postmortem",
        "category": "postmortems",
        "name": "SmartDine Friday Peak-Hour Outage",
        "description": "Write a blameless postmortem for the Friday evening payment outage",
        "context": (
            "Incident: INC-0198 — Payment Service Cascading Failure\n"
            "Date: Friday, 7:15 PM (peak dinner hour)\n"
            "Duration: 8 minutes 35 seconds\n"
            "Severity: P1 (revenue-impacting)\n"
            "Root Cause: Deployment D-4721 reduced db_pool_max from 100 to 10\n"
            "Impact:\n"
            "  - 47 failed customer orders\n"
            "  - $1,400 estimated revenue loss\n"
            "  - 4 services affected (payment, order, inventory, notification)\n"
            "  - ~200 customers experienced checkout failures\n"
            "What went well:\n"
            "  - On-call responded within 2 minutes of page\n"
            "  - Rollback completed in under 90 seconds\n"
            "  - Circuit breaker prevented complete system collapse\n"
            "What went poorly:\n"
            "  - No pre-deployment config validation\n"
            "  - 6-minute detection delay\n"
            "  - No canary deployment for config changes"
        ),
        "expected_keywords": ["blameless", "action items", "db_pool_max", "rollback", "detection"],
    },
}

MOCK_RESPONSES = {
    "debugging": {
        "analysis": "The logs show a classic connection pool exhaustion pattern in payment-service. "
        "The db_pool was configured with only 10 connections, which saturated under peak traffic. "
        "The cascade propagated to order-service (payment dependency timeout), inventory-service "
        "(reservation lock timeout), and nginx (upstream connection timeout).",
        "findings": {
            "error_pattern": "ConnectionPoolExhausted → upstream timeout → cascading service failure",
            "root_cause": "Database connection pool sized at 10 is insufficient for peak traffic (~50 concurrent requests)",
            "affected_components": ["payment-service", "order-service", "inventory-service", "nginx"],
            "severity": "critical",
            "confidence": 0.95,
        },
    },
    "rca": {
        "analysis": "Root cause analysis confirms deployment D-4721 (change PAY-88) as the trigger. "
        "The db_pool_max reduction from 100 to 10 was a configuration error that passed review because "
        "there was no automated validation of connection pool sizing against traffic baselines.",
        "findings": {
            "proximate_cause": "Connection pool exhaustion under peak traffic",
            "root_cause": "Configuration change PAY-88 reduced db_pool_max from 100 to 10 without load testing",
            "category": "config-change",
            "five_whys": [
                {"level": 1, "question": "Why did payments fail?", "answer": "Connection pool exhausted (10/10 active)"},
                {"level": 2, "question": "Why was the pool exhausted?", "answer": "Pool sized at 10, peak traffic needs ~50"},
                {"level": 3, "question": "Why was pool set to 10?", "answer": "Deployment D-4721 changed db_pool_max from 100 to 10"},
                {"level": 4, "question": "Why was this change approved?", "answer": "No automated config validation gate in CI/CD"},
                {"level": 5, "question": "Why is there no validation?", "answer": "Config changes treated differently from code changes in review process"},
            ],
            "timeline_summary": "8 min 35 sec total — 6 min detection, 2.5 min resolution",
        },
    },
    "infra-explanation": {
        "analysis": "This Kubernetes deployment configures payment-service with 3 replicas using a rolling "
        "update strategy. The zero-downtime configuration (maxUnavailable: 0) ensures service availability "
        "during deployments. Resource limits are set conservatively but the readiness probe configuration "
        "is appropriate for a payment processing service.",
        "findings": {
            "components": [
                {"name": "payment-service Deployment", "purpose": "Runs 3 copies of the payment service for high availability"},
                {"name": "RollingUpdate strategy", "purpose": "Updates pods one at a time without downtime"},
                {"name": "Readiness probe", "purpose": "Ensures new pods are healthy before receiving traffic"},
            ],
            "single_points_of_failure": ["No PodDisruptionBudget defined", "No anti-affinity rules — all pods could land on same node"],
            "overall_assessment": "Good baseline configuration with room for improvement in resilience",
            "score_out_of_100": 72,
        },
    },
    "script-generation": {
        "analysis": "Generated a Prometheus monitoring configuration for SmartDine's 4 core services "
        "with differentiated scrape intervals based on criticality. Includes alerting rules for error rate "
        "and latency SLO violations, plus PagerDuty integration for P1 alerts.",
        "findings": {
            "script_summary": "Complete prometheus.yml with 4 scrape targets, alerts.yml with 8 alerting rules, "
            "and grafana-dashboard.json with request rate, error rate, and latency panels",
            "total_rules": 8,
            "estimated_setup_minutes": 15,
            "verification_commands": [
                "curl http://localhost:9090/-/healthy",
                "curl http://localhost:9090/api/v1/targets",
                "curl http://localhost:9090/api/v1/rules",
            ],
        },
    },
    "postmortems": {
        "analysis": "Blameless postmortem for INC-0198 (Friday Peak-Hour Payment Outage). "
        "The incident was caused by a configuration change that bypassed standard validation. "
        "Three systemic improvements are recommended: automated config validation, canary deployments "
        "for config changes, and faster cascade detection.",
        "findings": {
            "title": "INC-0198: Payment Service Cascading Failure During Peak Hour",
            "severity": "P1",
            "duration_minutes": 8.5,
            "summary": "Deployment D-4721 reduced payment-service db_pool_max from 100 to 10, causing connection pool exhaustion and cascading failure across 4 services during Friday dinner rush.",
            "action_items": [
                {"action": "Add db_pool_max >= 50 validation gate to CI/CD pipeline", "priority": "P0", "effort_days": 2},
                {"action": "Implement canary deployment for config changes", "priority": "P1", "effort_days": 5},
                {"action": "Add cascade detection alerting (< 2 min TTD target)", "priority": "P1", "effort_days": 3},
                {"action": "Move connection pool config to centralized config service", "priority": "P2", "effort_days": 8},
            ],
            "total_effort_days": 18,
        },
    },
}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc), "type": type(exc).__name__, "path": request.url.path})


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(status_code=404, content={"error": "not found", "path": request.url.path})


@app.exception_handler(405)
async def method_not_allowed_handler(request: Request, exc):
    return JSONResponse(status_code=405, content={"error": "method not allowed", "method": request.method, "path": request.url.path})


def _update_library_gauges():
    PROMPTS_TOTAL.labels(service=SERVICE).set(len(PROMPT_LIBRARY))
    cats = {}
    for p in PROMPT_LIBRARY.values():
        c = p["category"]
        cats[c] = cats.get(c, 0) + 1
    for c, n in cats.items():
        PROMPTS_BY_CATEGORY.labels(service=SERVICE, category=c).set(n)
    QUALITY_THRESHOLD_GAUGE.labels(service=SERVICE).set(PROMPT_QUALITY_THRESHOLD)


_update_library_gauges()


def estimate_tokens(text: str) -> int:
    return max(1, int(len(text) / 4))


def score_prompt_quality(prompt_text: str) -> dict:
    lower = prompt_text.lower()
    components = {
        "role": any(k in lower for k in ["role:", "you are", "as a", "acting as"]),
        "task": any(k in lower for k in ["task:", "classify", "analyze", "generate", "identify", "build", "create", "extract", "calculate", "write", "map", "trace", "audit", "explain"]),
        "input": any(k in lower for k in ["input:", "{", "the following", "this"]),
        "constraints": any(k in lower for k in ["constraints:", "must be", "only", "do not", "maximum", "minimum", "focus on"]),
        "output_format": any(k in lower for k in ["output format:", "output:", "json with", "return json", "json:", "format:"]),
    }

    detected = sum(1 for v in components.values() if v)
    score = detected / 5.0

    token_count = estimate_tokens(prompt_text)
    if token_count > 500:
        score = max(0.1, score - 0.1)

    if detected == 5:
        quality_level = "full_production"
    elif detected >= 4:
        quality_level = "near_production"
    elif detected >= 3:
        quality_level = "developing"
    elif detected >= 2:
        quality_level = "basic"
    elif detected >= 1:
        quality_level = "minimal"
    else:
        quality_level = "bare_minimum"

    passes_threshold = score >= PROMPT_QUALITY_THRESHOLD

    return {
        "score": round(score, 2),
        "quality_level": quality_level,
        "components_detected": components,
        "components_present": detected,
        "components_total": 5,
        "token_estimate": token_count,
        "passes_threshold": passes_threshold,
        "threshold": PROMPT_QUALITY_THRESHOLD,
    }


def mock_test_prompt(prompt_text: str, scenario: dict) -> dict:
    quality = score_prompt_quality(prompt_text)
    category = scenario.get("category", "debugging")
    mock_data = MOCK_RESPONSES.get(category, MOCK_RESPONSES["debugging"])

    base_consistency = min(1.0, quality["score"] + 0.2)
    consistency = round(base_consistency + random.uniform(-0.05, 0.05), 2)
    consistency = max(0.0, min(1.0, consistency))

    prompt_tokens = estimate_tokens(prompt_text + scenario.get("context", ""))
    completion_tokens = estimate_tokens(json.dumps(mock_data["findings"]))

    keyword_matches = 0
    expected = scenario.get("expected_keywords", [])
    response_text = json.dumps(mock_data["findings"]).lower()
    for kw in expected:
        if kw.lower() in response_text:
            keyword_matches += 1
    relevance = round(keyword_matches / max(1, len(expected)), 2)

    return {
        "quality_score": quality["score"],
        "quality_level": quality["quality_level"],
        "consistency_score": consistency,
        "relevance_score": relevance,
        "mock_response": mock_data["findings"],
        "analysis": mock_data["analysis"],
        "tokens_used": {
            "prompt": prompt_tokens,
            "completion": completion_tokens,
            "total": prompt_tokens + completion_tokens,
        },
        "keyword_matches": keyword_matches,
        "expected_keywords": expected,
    }


class TestRequest(BaseModel):
    prompt_id: Optional[str] = None
    prompt_text: Optional[str] = None
    scenario_id: Optional[str] = None

class ScoreRequest(BaseModel):
    prompt_text: str

class AddPromptRequest(BaseModel):
    id: str
    category: str
    name: str
    description: str
    prompt: str
    variables: Optional[List[str]] = []
    tags: Optional[List[str]] = []


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": SERVICE,
        "mode": RCA_MODE,
        "prompt_quality_threshold": PROMPT_QUALITY_THRESHOLD,
        "export_format": EXPORT_FORMAT,
        "model": OPENAI_MODEL,
        "prompts_in_library": len(PROMPT_LIBRARY),
        "scenarios_available": len(TEST_SCENARIOS),
    }


@app.get("/config")
def config():
    return {
        "service": SERVICE,
        "mode": RCA_MODE,
        "model": OPENAI_MODEL,
        "prompt_quality_threshold": PROMPT_QUALITY_THRESHOLD,
        "export_format": EXPORT_FORMAT,
        "prompts_in_library": len(PROMPT_LIBRARY),
        "scenarios_available": len(TEST_SCENARIOS),
        "categories": list(set(p["category"] for p in PROMPT_LIBRARY.values())),
    }


@app.get("/prompts")
def list_prompts(category: Optional[str] = Query(None)):
    prompts = list(PROMPT_LIBRARY.values())
    if category:
        prompts = [p for p in prompts if p["category"] == category]

    summary = {}
    for p in prompts:
        c = p["category"]
        summary[c] = summary.get(c, 0) + 1

    return {
        "total": len(prompts),
        "category_breakdown": summary,
        "prompts": [
            {
                "id": p["id"],
                "category": p["category"],
                "name": p["name"],
                "description": p["description"],
                "tags": p.get("tags", []),
            }
            for p in prompts
        ],
    }


@app.get("/prompts/{prompt_id}")
def get_prompt(prompt_id: str):
    if prompt_id not in PROMPT_LIBRARY:
        raise HTTPException(status_code=404, detail=f"Prompt '{prompt_id}' not found. Use GET /prompts to see available prompts.")

    p = PROMPT_LIBRARY[prompt_id]
    quality = score_prompt_quality(p["prompt"])

    CATEGORY_USAGE.labels(service=SERVICE, category=p["category"]).inc()

    return {
        "prompt": p,
        "quality_analysis": quality,
    }


@app.post("/prompts")
def add_prompt(req: AddPromptRequest):
    if req.id in PROMPT_LIBRARY:
        raise HTTPException(status_code=409, detail=f"Prompt '{req.id}' already exists. Use a different ID.")

    valid_categories = {"debugging", "rca", "infra-explanation", "script-generation", "postmortems"}
    if req.category not in valid_categories:
        raise HTTPException(status_code=400, detail=f"Invalid category '{req.category}'. Must be one of: {sorted(valid_categories)}")

    prompt_data = {
        "id": req.id,
        "category": req.category,
        "name": req.name,
        "description": req.description,
        "prompt": req.prompt,
        "variables": req.variables or [],
        "tags": req.tags or [],
    }
    PROMPT_LIBRARY[req.id] = prompt_data
    _update_library_gauges()

    quality = score_prompt_quality(req.prompt)
    PROMPT_QUALITY.labels(service=SERVICE, category=req.category).observe(quality["score"])

    logger.info(f"Added prompt '{req.id}' to category '{req.category}' (quality: {quality['score']})")

    return {
        "ok": True,
        "prompt": prompt_data,
        "quality_analysis": quality,
        "library_total": len(PROMPT_LIBRARY),
    }


@app.get("/scenarios")
def list_scenarios():
    return {
        "total": len(TEST_SCENARIOS),
        "scenarios": [
            {
                "id": s["id"],
                "category": s["category"],
                "name": s["name"],
                "description": s["description"],
            }
            for s in TEST_SCENARIOS.values()
        ],
    }


@app.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    if scenario_id not in TEST_SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found. Use GET /scenarios to see available scenarios.")
    return TEST_SCENARIOS[scenario_id]


@app.post("/prompts/test")
def test_prompt(req: TestRequest):
    global _tests_run_count

    if req.prompt_id and req.prompt_id not in PROMPT_LIBRARY:
        raise HTTPException(status_code=404, detail=f"Prompt '{req.prompt_id}' not found.")

    prompt_text = req.prompt_text
    prompt_category = None
    if req.prompt_id:
        p = PROMPT_LIBRARY[req.prompt_id]
        prompt_text = p["prompt"]
        prompt_category = p["category"]

    if not prompt_text:
        raise HTTPException(status_code=400, detail="Provide either 'prompt_id' or 'prompt_text'.")

    scenario_id = req.scenario_id
    if not scenario_id and prompt_category:
        for s in TEST_SCENARIOS.values():
            if s["category"] == prompt_category:
                scenario_id = s["id"]
                break

    if not scenario_id:
        scenario_id = "scenario-debugging"

    if scenario_id not in TEST_SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Scenario '{scenario_id}' not found.")

    scenario = TEST_SCENARIOS[scenario_id]

    if RCA_MODE != "mock":
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise HTTPException(
                status_code=501,
                detail="Live mode (RCA_MODE=llm) requires OPENAI_API_KEY. Set it in .env and restart, or use RCA_MODE=mock.",
            )
        logger.info("Live LLM mode not yet implemented — falling back to mock for this lab version")

    result = mock_test_prompt(prompt_text, scenario)

    cat = prompt_category or scenario["category"]
    test_result = "pass" if result["quality_score"] >= PROMPT_QUALITY_THRESHOLD else "fail"
    PROMPT_TESTS.labels(service=SERVICE, category=cat, result=test_result).inc()
    PROMPT_QUALITY.labels(service=SERVICE, category=cat).observe(result["quality_score"])
    CATEGORY_USAGE.labels(service=SERVICE, category=cat).inc()
    TOKEN_ESTIMATE.labels(service=SERVICE, direction="prompt").inc(result["tokens_used"]["prompt"])
    TOKEN_ESTIMATE.labels(service=SERVICE, direction="completion").inc(result["tokens_used"]["completion"])

    _tests_run_count += 1
    TESTS_RUN_TOTAL.labels(service=SERVICE).set(_tests_run_count)

    logger.info(f"Tested prompt (category={cat}, score={result['quality_score']}, result={test_result})")

    return {
        "ok": True,
        "prompt_id": req.prompt_id,
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "mode": RCA_MODE,
        "test_result": test_result,
        "threshold": PROMPT_QUALITY_THRESHOLD,
        **result,
    }


@app.post("/prompts/score")
def score_prompt(req: ScoreRequest):
    quality = score_prompt_quality(req.prompt_text)

    cat = "custom"
    PROMPT_QUALITY.labels(service=SERVICE, category=cat).observe(quality["score"])

    return {
        "ok": True,
        "mode": RCA_MODE,
        **quality,
        "suggestions": _get_quality_suggestions(quality),
    }


def _get_quality_suggestions(quality: dict) -> list:
    suggestions = []
    components = quality["components_detected"]
    if not components["role"]:
        suggestions.append("Add a Role component (e.g., 'Role: You are a senior SRE...')")
    if not components["task"]:
        suggestions.append("Add a Task component (e.g., 'Task: Analyze these logs and identify...')")
    if not components["input"]:
        suggestions.append("Add an Input placeholder (e.g., 'Input: {log_data}')")
    if not components["constraints"]:
        suggestions.append("Add Constraints (e.g., 'Constraints: Focus only on ERROR entries...')")
    if not components["output_format"]:
        suggestions.append("Add an Output Format (e.g., 'Output Format: JSON with fields: ...')")
    if quality["token_estimate"] > 500:
        suggestions.append("Consider making the prompt more concise — high token count increases cost")
    if not suggestions:
        suggestions.append("Prompt looks well-structured! Consider testing against a scenario to verify consistency.")
    return suggestions


@app.get("/export")
def export_library(format: Optional[str] = Query(None)):
    export_fmt = (format or EXPORT_FORMAT).lower()

    library_data = {
        "metadata": {
            "title": "SmartDine DevOps Prompt Library",
            "version": "1.0",
            "total_prompts": len(PROMPT_LIBRARY),
            "categories": list(set(p["category"] for p in PROMPT_LIBRARY.values())),
            "exported_at": datetime.utcnow().isoformat() + "Z",
        },
        "prompts": {},
    }

    for pid, p in PROMPT_LIBRARY.items():
        cat = p["category"]
        if cat not in library_data["prompts"]:
            library_data["prompts"][cat] = []
        quality = score_prompt_quality(p["prompt"])
        library_data["prompts"][cat].append({
            "id": p["id"],
            "name": p["name"],
            "description": p["description"],
            "prompt": p["prompt"],
            "variables": p.get("variables", []),
            "tags": p.get("tags", []),
            "quality_score": quality["score"],
            "quality_level": quality["quality_level"],
        })

    EXPORT_OPS.labels(service=SERVICE, format=export_fmt).inc()

    if export_fmt == "markdown":
        md = _render_markdown(library_data)
        logger.info(f"Exported library as markdown ({len(PROMPT_LIBRARY)} prompts)")
        return PlainTextResponse(content=md, media_type="text/markdown")
    else:
        yaml_content = yaml.dump(library_data, default_flow_style=False, sort_keys=False, allow_unicode=True)
        logger.info(f"Exported library as YAML ({len(PROMPT_LIBRARY)} prompts)")
        return PlainTextResponse(content=yaml_content, media_type="text/yaml")


def _render_markdown(data: dict) -> str:
    lines = [
        f"# {data['metadata']['title']}",
        "",
        f"**Version:** {data['metadata']['version']}  ",
        f"**Total Prompts:** {data['metadata']['total_prompts']}  ",
        f"**Exported:** {data['metadata']['exported_at']}  ",
        f"**Categories:** {', '.join(data['metadata']['categories'])}",
        "",
        "---",
        "",
    ]
    for cat, prompts in data["prompts"].items():
        lines.append(f"## {cat.replace('-', ' ').title()}")
        lines.append("")
        for p in prompts:
            lines.append(f"### {p['name']}")
            lines.append("")
            lines.append(f"**ID:** `{p['id']}`  ")
            lines.append(f"**Quality:** {p['quality_level']} ({p['quality_score']})  ")
            lines.append(f"**Tags:** {', '.join(p['tags'])}  ")
            lines.append("")
            lines.append(f"> {p['description']}")
            lines.append("")
            lines.append("```")
            lines.append(p["prompt"])
            lines.append("```")
            lines.append("")
            if p["variables"]:
                lines.append(f"**Variables:** `{'`, `'.join(p['variables'])}`")
                lines.append("")
            lines.append("---")
            lines.append("")
    return "\n".join(lines)


@app.get("/stats")
def library_stats():
    categories = {}
    quality_scores = []
    for p in PROMPT_LIBRARY.values():
        c = p["category"]
        categories[c] = categories.get(c, 0) + 1
        q = score_prompt_quality(p["prompt"])
        quality_scores.append(q["score"])

    avg_quality = round(sum(quality_scores) / max(1, len(quality_scores)), 2)
    passing = sum(1 for s in quality_scores if s >= PROMPT_QUALITY_THRESHOLD)

    return {
        "total_prompts": len(PROMPT_LIBRARY),
        "total_scenarios": len(TEST_SCENARIOS),
        "category_breakdown": categories,
        "quality_summary": {
            "average_score": avg_quality,
            "passing_count": passing,
            "failing_count": len(quality_scores) - passing,
            "threshold": PROMPT_QUALITY_THRESHOLD,
        },
        "tests_run": _tests_run_count,
    }


@app.get("/metrics")
def metrics():
    return PlainTextResponse(content=generate_latest().decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


@app.on_event("startup")
def startup():
    _update_library_gauges()
    logger.info(
        f"Prompt Library started: {len(PROMPT_LIBRARY)} prompts, "
        f"{len(TEST_SCENARIOS)} scenarios, mode={RCA_MODE}, "
        f"threshold={PROMPT_QUALITY_THRESHOLD}, export_format={EXPORT_FORMAT}"
    )
