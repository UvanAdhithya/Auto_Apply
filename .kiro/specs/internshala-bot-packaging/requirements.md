# Requirements Document

## Introduction

This document defines the requirements for packaging the Internshala Automation Bot as a distributable product. The bot automates one-click internship applications on Internshala.com using Playwright browser automation and a self-healing CrewAI agent that auto-patches broken CSS selectors via GPT-4o/GPT-4o-mini.

The packaging effort must produce two deployment targets:
1. A Docker-based image for local or self-hosted deployment
2. A cloud-ready configuration for hosted/VM/serverless deployment

The packaged product must be runnable by a non-developer user with minimal setup steps, while preserving all existing bot capabilities including dry-run mode, persistent browser sessions, application logging, and the self-healing AI workflow.

---

## Glossary

- **Bot**: The Internshala automation system composed of `script.py` and `agent.py`
- **Container**: A Docker container image that bundles the Bot and all its runtime dependencies
- **Config_Loader**: The component responsible for reading and validating all runtime configuration values
- **Credential_Store**: The mechanism for securely supplying `INTERNSHALA_USERNAME`, `INTERNSHALA_PASSWORD`, and `OPENAI_API_KEY` to the Bot at runtime
- **Entrypoint**: The executable command or script that starts the Bot inside the Container
- **Health_Check**: A lightweight probe that verifies the Bot process is alive and responsive
- **Log_Exporter**: The component that makes application logs accessible outside the Container
- **Selector_Store**: The `selectors.yaml` file managed by the self-healing agent
- **Session_Store**: The persistent Chromium browser profile directory (`internshala_session/`)
- **CI_Pipeline**: The automated build, test, and publish workflow (e.g., GitHub Actions)
- **Registry**: A container image registry (e.g., Docker Hub, GHCR) where built images are published
- **Dry_Run**: A mode where the Bot simulates applications without submitting them

---

## Requirements

### Requirement 1: Containerization

**User Story:** As a self-hosted user, I want to run the Bot inside a Docker container, so that I do not need to manually install Python, Playwright, or any dependencies on my machine.

#### Acceptance Criteria

1. THE Container SHALL include Python 3.11+, all pip dependencies from `requirements.txt`, and a Playwright Chromium browser binary.
2. THE Container SHALL expose a single Entrypoint that accepts `--dry-run` and `--headed` flags equivalent to the existing `script.py` CLI interface.
3. WHEN the Container is built, THE Container SHALL produce a final image no larger than 2 GB.
4. WHEN the Container starts without required environment variables, THE Config_Loader SHALL exit with a non-zero status code and a human-readable error message listing the missing variables.
5. THE Container SHALL run as a non-root user to reduce the attack surface.

---

### Requirement 2: Configuration Management

**User Story:** As a user, I want to configure the Bot's search keywords and runtime options without modifying source code, so that I can customize behavior per deployment.

#### Acceptance Criteria

1. THE Config_Loader SHALL read the following values from environment variables: `INTERNSHALA_USERNAME`, `INTERNSHALA_PASSWORD`, `OPENAI_API_KEY`, `BOT_KEYWORDS`, `BOT_DRY_RUN`, `BOT_HEADED`.
2. WHEN `BOT_KEYWORDS` is set, THE Config_Loader SHALL parse it as a comma-separated list and override the default keyword list in `script.py`.
3. WHEN `BOT_DRY_RUN` is set to `"true"` (case-insensitive), THE Bot SHALL run in Dry_Run mode.
4. WHEN `BOT_HEADED` is set to `"true"` (case-insensitive), THE Bot SHALL launch Chromium in headed mode.
5. THE Config_Loader SHALL provide a `.env.example` file listing all supported environment variables with placeholder values and inline documentation comments.
6. IF a required environment variable (`INTERNSHALA_USERNAME`, `INTERNSHALA_PASSWORD`, `OPENAI_API_KEY`) is absent or empty, THEN THE Config_Loader SHALL raise a `RuntimeError` with a message identifying the missing variable by name.

---

### Requirement 3: Persistent Session and Selector Storage

**User Story:** As a user, I want my browser session and AI-patched selectors to persist across Bot restarts, so that I do not need to log in or re-heal selectors every run.

#### Acceptance Criteria

1. THE Container SHALL mount the Session_Store directory as a named Docker volume so that the Chromium profile survives container restarts.
2. THE Container SHALL mount the Selector_Store file as a bind-mount or named volume so that AI-healed selectors persist across container restarts.
3. WHEN the Session_Store volume is absent on first run, THE Bot SHALL create the directory and proceed with a fresh login flow.
4. WHEN the Selector_Store file is absent on container start, THE Container SHALL copy the default `selectors.yaml` from the image into the mounted path before starting the Bot.

---

### Requirement 4: Application Log Accessibility

**User Story:** As a user, I want to access the application log CSV outside the container, so that I can review which internships were applied to without entering the container.

#### Acceptance Criteria

1. THE Log_Exporter SHALL write all application records to a path resolvable via a Docker volume mount (e.g., `/app/logs/internshala_applied.csv`).
2. THE Container SHALL expose the `logs/` directory as a mountable volume in the `docker-compose.yml` definition.
3. WHEN a log record is written, THE Log_Exporter SHALL append to the existing CSV file without truncating prior records.
4. WHEN the `logs/` directory does not exist at startup, THE Log_Exporter SHALL create it before writing the first record.

---

### Requirement 5: Docker Compose Setup

**User Story:** As a self-hosted user, I want a single `docker-compose.yml` to start the Bot with all volumes and environment variables wired up, so that I can run the product with one command.

#### Acceptance Criteria

1. THE product SHALL include a `docker-compose.yml` that defines the Bot service, all named volumes (Session_Store, logs), and an `env_file` reference to `.env`.
2. WHEN `docker compose up` is executed with a valid `.env` file, THE Bot SHALL start and begin the login and application flow without additional manual steps.
3. THE `docker-compose.yml` SHALL include a `restart: on-failure` policy so the Bot automatically retries on transient errors.
4. THE `docker-compose.yml` SHALL include a Health_Check definition that verifies the Bot process is running.

---

### Requirement 6: Cloud Deployment Support

**User Story:** As a cloud operator, I want the Bot to be deployable on a cloud VM or container service (e.g., AWS ECS, GCP Cloud Run, Azure Container Instances), so that it can run on a schedule without a local machine.

#### Acceptance Criteria

1. THE Container SHALL be stateless with respect to credentials — all secrets SHALL be injected via environment variables and never baked into the image.
2. THE Container image SHALL be publishable to a public or private Registry using standard `docker push` without modification.
3. THE product SHALL include a `cloud-deploy/` directory containing at minimum one reference deployment configuration (e.g., an ECS task definition JSON or a Cloud Run service YAML).
4. WHEN the Bot is deployed to a headless cloud environment, THE Container SHALL default to headless Chromium mode unless `BOT_HEADED=true` is explicitly set.
5. THE Container SHALL support scheduled execution via an external scheduler (e.g., cron, ECS Scheduled Tasks, Cloud Scheduler) by running to completion and exiting with code `0` on success.

---

### Requirement 7: CI/CD Pipeline

**User Story:** As a developer maintaining the Bot, I want an automated pipeline that builds, tests, and publishes the Docker image on every push to `main`, so that the published image is always up to date.

#### Acceptance Criteria

1. THE CI_Pipeline SHALL build the Docker image and run a smoke test (dry-run execution) on every push to the `main` branch.
2. WHEN all CI_Pipeline checks pass on a tagged commit, THE CI_Pipeline SHALL push the built image to the Registry with both the git tag and `latest` tags.
3. THE CI_Pipeline SHALL cache Docker build layers between runs to reduce build time.
4. IF the smoke test exits with a non-zero code, THEN THE CI_Pipeline SHALL fail the build and SHALL NOT push the image to the Registry.
5. THE CI_Pipeline SHALL store `INTERNSHALA_USERNAME`, `INTERNSHALA_PASSWORD`, and `OPENAI_API_KEY` as encrypted CI secrets and SHALL NOT log these values in build output.

---

### Requirement 8: User-Facing Setup Experience

**User Story:** As a first-time user, I want clear setup instructions that get me from zero to a running Bot in under 10 minutes, so that I can use the product without reading source code.

#### Acceptance Criteria

1. THE product SHALL include a `README.md` with a "Quick Start" section covering: cloning the repo, copying `.env.example` to `.env`, filling in credentials, and running `docker compose up`.
2. THE `README.md` SHALL document all supported environment variables, their types, default values, and whether they are required or optional.
3. THE `README.md` SHALL include a troubleshooting section covering at minimum: CAPTCHA handling, missing OpenAI key errors, and selector healing failures.
4. WHEN the Bot encounters a CAPTCHA during login in headed mode, THE Bot SHALL print a human-readable prompt to stdout instructing the user to solve the CAPTCHA manually and wait.
5. THE product SHALL include a `Makefile` or equivalent with targets: `build`, `run`, `dry-run`, `logs`, and `clean`.

---

### Requirement 9: Security and Secrets Handling

**User Story:** As a security-conscious user, I want to ensure that credentials are never stored in the image or version-controlled files, so that I can safely share or publish the container image.

#### Acceptance Criteria

1. THE `.gitignore` SHALL include `.env`, `internshala_session/`, `logs/`, and any screenshot artifacts (`*.png`, `agent_dom_dump.html`).
2. THE `Dockerfile` SHALL NOT include any `COPY .env` or `ENV` instructions that embed credential values.
3. WHEN the Container image is inspected with `docker history`, THE image layers SHALL contain no credential values.
4. THE product SHALL document that `selectors.yaml` is safe to commit and does not contain sensitive data.
5. WHERE a cloud secrets manager (e.g., AWS Secrets Manager, GCP Secret Manager) is available, THE product documentation SHALL describe how to inject secrets via the platform's native environment variable injection instead of a `.env` file.

---

### Requirement 10: Smoke Test and Validation

**User Story:** As a developer, I want an automated smoke test that validates the packaged Bot can start, load configuration, and complete a dry-run without errors, so that I can verify the packaging is correct before shipping.

#### Acceptance Criteria

1. THE product SHALL include a smoke test script that starts the Bot in Dry_Run mode and asserts it exits with code `0`.
2. WHEN the smoke test runs, THE Bot SHALL successfully load credentials from environment variables, launch Chromium headlessly, navigate to Internshala, and complete the dry-run flow.
3. WHEN the smoke test completes, THE Log_Exporter SHALL have written at least one record with `status=dry_run` to the log file.
4. THE smoke test SHALL complete within 120 seconds under normal network conditions.
5. IF the smoke test detects a missing dependency (e.g., Playwright browser binary not installed), THEN THE smoke test SHALL print a diagnostic message identifying the missing component and exit with a non-zero code.
