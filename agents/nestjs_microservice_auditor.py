#!/usr/bin/env python3
"""
AURA-OS NestJS Microservices Auditor Agent
Audit architecture microservices NestJS + API Gateway 2026
Team: core (dev workflows)
Sources: NestJS docs, BackendWorks/nestjs-microservices, Kong patterns
"""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Any
from datetime import datetime
from collections import defaultdict


class NestJSMicroserviceAuditor:
    """Audit architecture microservices NestJS."""

    # Patterns à vérifier
    PATTERNS = {
        "api_gateway": [
            (r'ClientsModule\.register', "ClientsModule registration found"),
            (r'@Client\s*\(', "Client decorator for microservice"),
            (r'ClientProxy', "ClientProxy usage"),
            (r'Transport\.(TCP|REDIS|NATS|KAFKA|GRPC|RMQ)', "Transport protocol"),
        ],
        "communication": [
            (r'@MessagePattern\s*\(["\']([^"\']+)', "Message pattern: {}"),
            (r'@EventPattern\s*\(["\']([^"\']+)', "Event pattern: {}"),
            (r'\.send\s*\(["\']([^"\']+)', "Send to pattern: {}"),
            (r'\.emit\s*\(["\']([^"\']+)', "Emit event: {}"),
        ],
        "cqrs": [
            (r'@CommandHandler', "CQRS Command Handler"),
            (r'@QueryHandler', "CQRS Query Handler"),
            (r'@EventsHandler', "CQRS Event Handler"),
            (r'@Saga', "Saga pattern"),
            (r'AggregateRoot', "Event Sourcing Aggregate"),
        ],
        "health": [
            (r'TerminusModule', "Terminus health checks"),
            (r'@HealthCheck', "Health check endpoint"),
            (r'HealthIndicator', "Health indicator"),
            (r'HttpHealthIndicator', "HTTP health check"),
            (r'TypeOrmHealthIndicator|MikroOrmHealthIndicator', "Database health check"),
        ],
        "resilience": [
            (r'CircuitBreaker|@CircuitBreaker', "Circuit breaker pattern"),
            (r'Retry|@Retry', "Retry pattern"),
            (r'Timeout|@Timeout', "Timeout pattern"),
            (r'Bulkhead', "Bulkhead pattern"),
        ],
        "security": [
            (r'JwtModule', "JWT Module"),
            (r'@UseGuards.*JwtAuthGuard', "JWT Auth Guard"),
            (r'ThrottlerModule|@Throttle', "Rate limiting"),
            (r'enableCors', "CORS configuration"),
        ],
        "observability": [
            (r'OpenTelemetry|@opentelemetry', "OpenTelemetry tracing"),
            (r'Prometheus|PrometheusModule', "Prometheus metrics"),
            (r'Jaeger', "Jaeger tracing"),
            (r'pino|winston|bunyan', "Structured logging"),
        ]
    }

    REQUIRED_PATTERNS = {
        "gateway": ["ClientsModule", "Transport"],
        "service": ["@MessagePattern", "@Controller"],
        "health": ["TerminusModule", "HealthCheck"],
    }

    def __init__(self, path: Path, verbose: bool = False):
        self.path = path.resolve()
        self.verbose = verbose
        self.results: dict[str, Any] = {
            "path": str(self.path),
            "audited_at": datetime.now().isoformat(),
            "architecture": {
                "type": "unknown",
                "services": [],
                "gateway": None,
                "shared_libs": []
            },
            "patterns_found": defaultdict(list),
            "communication_map": {
                "messages": [],
                "events": []
            },
            "health_status": {
                "endpoints": 0,
                "indicators": []
            },
            "issues": [],
            "recommendations": [],
            "score": 100
        }

    def detect_architecture(self):
        """Détecte le type d'architecture."""
        # Check for monorepo structure
        apps_dir = self.path / "apps"
        libs_dir = self.path / "libs"
        nest_cli = self.path / "nest-cli.json"

        if apps_dir.exists():
            self.results["architecture"]["type"] = "monorepo"
            # List apps
            for app_dir in apps_dir.iterdir():
                if app_dir.is_dir():
                    app_info = {
                        "name": app_dir.name,
                        "path": str(app_dir),
                        "has_main": (app_dir / "src" / "main.ts").exists(),
                        "type": "service"
                    }
                    # Check if gateway
                    if "gateway" in app_dir.name.lower() or "api" in app_dir.name.lower():
                        app_info["type"] = "gateway"
                        self.results["architecture"]["gateway"] = app_dir.name

                    self.results["architecture"]["services"].append(app_info)

            # List shared libs
            if libs_dir.exists():
                for lib_dir in libs_dir.iterdir():
                    if lib_dir.is_dir():
                        self.results["architecture"]["shared_libs"].append(lib_dir.name)
        else:
            # Standard single app
            self.results["architecture"]["type"] = "single"
            if (self.path / "src" / "main.ts").exists():
                self.results["architecture"]["services"].append({
                    "name": self.path.name,
                    "path": str(self.path),
                    "type": "monolith"
                })

        # Parse nest-cli.json if exists
        if nest_cli.exists():
            try:
                config = json.loads(nest_cli.read_text())
                if "projects" in config:
                    self.results["architecture"]["nest_cli_projects"] = list(config["projects"].keys())
            except Exception:
                pass

    def scan_patterns(self, filepath: Path):
        """Scan un fichier pour les patterns."""
        try:
            content = filepath.read_text(encoding='utf-8', errors='ignore')
            rel_path = str(filepath.relative_to(self.path))

            for category, patterns in self.PATTERNS.items():
                for pattern, description in patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        for match in matches:
                            finding = {
                                "file": rel_path,
                                "pattern": description.format(match) if "{}" in description else description,
                                "match": match if isinstance(match, str) else match[0] if match else ""
                            }
                            self.results["patterns_found"][category].append(finding)

                            # Build communication map
                            if category == "communication":
                                if "MessagePattern" in description or "Send" in description:
                                    if match not in self.results["communication_map"]["messages"]:
                                        self.results["communication_map"]["messages"].append(match)
                                elif "EventPattern" in description or "Emit" in description:
                                    if match not in self.results["communication_map"]["events"]:
                                        self.results["communication_map"]["events"].append(match)

        except Exception as e:
            if self.verbose:
                print(f"Error scanning {filepath}: {e}")

    def check_docker(self):
        """Vérifie la configuration Docker."""
        docker_info = {
            "dockerfiles": [],
            "compose_files": [],
            "services": []
        }

        # Find Dockerfiles
        for df in self.path.rglob("Dockerfile*"):
            docker_info["dockerfiles"].append(str(df.relative_to(self.path)))

        # Find docker-compose files
        for dc in self.path.glob("docker-compose*.yml"):
            docker_info["compose_files"].append(dc.name)
            try:
                content = dc.read_text()
                services = re.findall(r'^\s{2}(\w+):\s*$', content, re.MULTILINE)
                docker_info["services"].extend(services)
            except Exception:
                pass

        self.results["docker"] = docker_info

    def analyze(self):
        """Lance l'analyse complète."""
        self.detect_architecture()
        self.check_docker()

        # Scan all TS files
        exclude_dirs = {'node_modules', 'dist', 'build', '.git', 'coverage'}

        for filepath in self.path.rglob('*.ts'):
            if any(excl in filepath.parts for excl in exclude_dirs):
                continue
            self.scan_patterns(filepath)

        # Generate issues and recommendations
        self._analyze_findings()

        return self.results

    def _analyze_findings(self):
        """Analyse les findings et génère des recommandations."""
        arch = self.results["architecture"]
        patterns = self.results["patterns_found"]

        # Check API Gateway
        if arch["type"] == "monorepo" and not arch.get("gateway"):
            self.results["issues"].append("No API Gateway detected in monorepo")
            self.results["recommendations"].append("Consider adding an API Gateway service for centralized routing")
            self.results["score"] -= 10

        # Check communication patterns
        if not patterns.get("api_gateway") and arch["type"] == "monorepo":
            self.results["issues"].append("No microservice communication patterns found")
            self.results["recommendations"].append("Set up ClientsModule with appropriate transport (TCP, Redis, NATS, Kafka)")
            self.results["score"] -= 15

        # Check health checks
        if not patterns.get("health"):
            self.results["issues"].append("No health check endpoints found")
            self.results["recommendations"].append("Add @nestjs/terminus for health monitoring")
            self.results["score"] -= 10
        else:
            self.results["health_status"]["endpoints"] = len([p for p in patterns["health"] if "HealthCheck" in p["pattern"]])
            self.results["health_status"]["indicators"] = [p["pattern"] for p in patterns["health"] if "Indicator" in p["pattern"]]

        # Check resilience
        if not patterns.get("resilience") and len(arch.get("services", [])) > 2:
            self.results["issues"].append("No resilience patterns (circuit breaker, retry) found")
            self.results["recommendations"].append("Implement circuit breaker pattern for inter-service calls")
            self.results["score"] -= 10

        # Check security
        if not patterns.get("security"):
            self.results["issues"].append("Security patterns not detected")
            self.results["recommendations"].append("Ensure JWT authentication and rate limiting are configured")
            self.results["score"] -= 15

        # Check observability
        if not patterns.get("observability") and len(arch.get("services", [])) > 1:
            self.results["recommendations"].append("Consider adding distributed tracing (OpenTelemetry, Jaeger)")
            self.results["score"] -= 5

        # Check Docker
        docker = self.results.get("docker", {})
        if arch["type"] == "monorepo" and not docker.get("compose_files"):
            self.results["recommendations"].append("Add docker-compose for local development with all services")
            self.results["score"] -= 5

        # Positive patterns
        if patterns.get("cqrs"):
            self.results["recommendations"].append("CQRS pattern detected - ensure proper event sourcing")

        self.results["score"] = max(0, self.results["score"])


def print_report(results: dict[str, Any], verbose: bool = False):
    """Affiche le rapport."""
    print(f"\n{'='*60}")
    print(f" NestJS Microservices Audit Report")
    print(f" Path: {results['path']}")
    print(f"{'='*60}\n")

    # Architecture
    arch = results["architecture"]
    print(f" Architecture: {arch['type'].upper()}")
    print(f"   Services: {len(arch['services'])}")
    if arch.get("gateway"):
        print(f"   API Gateway: {arch['gateway']}")
    if arch.get("shared_libs"):
        print(f"   Shared Libs: {', '.join(arch['shared_libs'][:5])}")

    for svc in arch["services"][:10]:
        icon = "[GW]" if svc["type"] == "gateway" else "[MS]"
        print(f"     {icon} {svc['name']}")

    # Score
    print(f"\n Architecture Score: {results['score']}/100")

    # Communication Map
    comm = results["communication_map"]
    if comm["messages"] or comm["events"]:
        print(f"\n Communication Patterns:")
        if comm["messages"]:
            print(f"   Message patterns: {len(comm['messages'])}")
            for msg in comm["messages"][:5]:
                print(f"     - {msg}")
        if comm["events"]:
            print(f"   Event patterns: {len(comm['events'])}")
            for evt in comm["events"][:5]:
                print(f"     - {evt}")

    # Patterns Found
    patterns = results["patterns_found"]
    if patterns:
        print(f"\n Patterns Detected:")
        for category, findings in patterns.items():
            if findings:
                print(f"   {category}: {len(findings)} occurrences")
                if verbose:
                    for f in findings[:3]:
                        print(f"     - {f['pattern']} ({f['file']})")

    # Health Status
    health = results["health_status"]
    if health["endpoints"] > 0:
        print(f"\n Health Monitoring:")
        print(f"   Endpoints: {health['endpoints']}")
        print(f"   Indicators: {', '.join(set(health['indicators'][:5]))}")

    # Docker
    docker = results.get("docker", {})
    if docker:
        print(f"\n Docker Configuration:")
        print(f"   Dockerfiles: {len(docker.get('dockerfiles', []))}")
        print(f"   Compose services: {len(docker.get('services', []))}")

    # Issues
    if results["issues"]:
        print(f"\n Issues:")
        for issue in results["issues"]:
            print(f"   [X] {issue}")

    # Recommendations
    if results["recommendations"]:
        print(f"\n Recommendations:")
        for rec in results["recommendations"]:
            print(f"   * {rec}")

    print(f"\n{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="AURA NestJS Microservices Auditor")
    parser.add_argument("path", nargs="?", default=".", help="Path to audit")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--json", action="store_true")

    args = parser.parse_args()
    path = Path(args.path)

    if not path.exists():
        print(f"Path not found: {path}")
        sys.exit(1)

    auditor = NestJSMicroserviceAuditor(path, verbose=args.verbose)
    results = auditor.analyze()

    if args.json:
        print(json.dumps(results, indent=2, default=list))
    else:
        print_report(results, verbose=args.verbose)


if __name__ == "__main__":
    main()
