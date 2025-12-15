# Project Context

## Purpose
The Santa Scale Challenge is a reference implementation demonstrating how to orchestrate LLMs, agentic workflows, and distributed batch jobs using Nebius GPU infrastructure, SkyPilot, and MLflow. The project generates personalized gift cards at scale (target: 2 billion cards in 30 days) through an agentic workflow that includes gift recommendation, personalized wish generation, unique illustration, and final HTML/PDF card formatting.

## Tech Stack
- **Python** - Primary programming language (Python 3.10+)
- **SkyPilot** - Distributed processing and cloud orchestration
- **MLflow** - Model tracking, observability, and experiment management
- **vLLM** - Self-hosted LLM serving for gift reasoning and wish generation
- **Stable Diffusion / Flux / Recraft** - Image generation models
- **Nebius** - GPU infrastructure provider
- **uv** - Python package manager (preferred over pip)
- **OpenSpec** - Specification-driven development workflow
- **Pydantic** - Data validation and settings management
- **HTTP/REST** - Service communication protocol

## Project Conventions

### Code Style
- **Type hints required** - All function definitions must include type hints
- **Pydantic for data models** - Use `BaseModel` for all data modeling, validation, and settings
- **Pure functions preferred** - Business logic should use pure functions with clear input/output, no hidden state changes
- **Functional programming** - Prefer functional and declarative patterns over OOP
- **Classes only for connectors** - Use classes only for clients connecting to external systems (e.g., `NotionClient`, `vLLMClient`)
- **No default parameters** - Make all function parameters explicit (no default values)
- **DRY, KISS, YAGNI** - Follow these principles strictly
- **Minimal changes** - Make focused, minimal changes that directly address the request
- **Comments in English only**
- **Strict typing** - Avoid `Any` type; use specific types for all variables and function returns
- **Named parameters** - Use named parameters in function calls when possible
- **Strongly-typed collections** - Prefer typed collections over generic ones for complex data structures

### Architecture Patterns
- **Agentic workflow** - Multi-stage pipeline orchestrated by `santa_agent/orchestrator.py`
- **Tool-based architecture** - Each stage implemented as a tool under `santa_agent/tools/`
- **HTTP-based services** - Self-hosted LLM and image generation services exposed via HTTP endpoints
- **Distributed batch processing** - Workers run via SkyPilot for horizontal scaling
- **Specification-driven development** - Use OpenSpec for change proposals and capability specifications
- **Separation of concerns**:
  - `prototype/` - Jupyter-first experimentation and prototyping
  - `santa_agent/` - Production batch pipeline
  - `models/` - Self-hosted LLM and image generation servers
  - `infra/` - SkyPilot, MLflow, Terraform configurations
  - `demos/` - CLI demos and code snippets
  - `openspec/` - Specifications, change proposals, and project documentation

### Testing Strategy
- Write unit tests using appropriate Python testing frameworks (pytest recommended)
- Test critical user flows and agentic workflows
- Ensure compatibility with distributed execution environments
- Test error handling and edge cases explicitly
- Use explicit error raising - never silently ignore errors
- Raise specific exceptions (ValueError, TypeError) instead of generic Exception
- Log errors with appropriate context before raising them

### Git Workflow
- Use descriptive commit messages
- Follow conventional commit format when applicable
- Use `git --no-pager diff` or `git diff | cat` for non-interactive diff viewing
- Branch strategy: TBD (document when established)

## Domain Context
- **Workflow stages**: Analyze Kid Profile → Gift Recommender → Wish Generator → Image Generation → Card Formatter → Delivery Protocol

## Important Constraints
- **Scale requirement** - Must handle billions of cards, requiring distributed execution
- **Latency** - Single workflow should complete in ~5 seconds
- **Cost optimization** - Enable request batching, efficient GPU utilization
- **Observability** - All runs must be tracked in MLflow for model comparison and evaluation
- **Self-hosted services** - LLM and image generation must run on Nebius infrastructure
- **Lightweight workers** - Batch workers should remain lightweight, using HTTP endpoints to services

## External Dependencies
- **Nebius GPU Infrastructure** - Cloud provider for GPU instances running vLLM and image models
- **SkyPilot** - Handles provisioning, execution, retries, autoscaling, and logging for distributed batch jobs
- **MLflow** - Tracks model versions, latency, artifacts, cost estimates, and final card outputs
- **vLLM** - LLM inference server (self-hosted)
- **Stable Diffusion / Flux / Recraft** - Image generation APIs/models (can be self-hosted or API-based)
- **S3-compatible storage** - For uploading final gift cards and artifacts

## Development Workflow
- **OpenSpec integration** - Use OpenSpec for creating change proposals and managing specifications
- **Auto-sync** - `.cursor/rules.json` automatically syncs YAML specs when Python files change:
  - `models/**/*.py` → syncs `openspec/specs/data_models.yaml`
  - `santa_agent/**/*.py` → syncs `openspec/specs/tools_santa.yaml`
- **Change proposals** - Create proposals in `openspec/changes/` before implementing new features or breaking changes
- **Specification files** - Maintain YAML specs in `openspec/` for data models, tools, workflows, and services
