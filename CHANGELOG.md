# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0-rc1] - 2026-09-16
### Added
- First Release Candidate for Traductor PDF.
- Translation pipeline utilizing local Ollama models (`llama3.2:3b` by default).
- Safe Overlay PDF export engine keeping the visual layout intact.
- Glossary management with versions.
- Review and Approval workflow for translation quality assurance.
- Translation Memory for tracking historical translations across the project.
- Batch translation processing capabilities.
- Windows application hardening for deployment.
- SQLite persistence engine.

### Known Limitations
- V1 does not remove original source text (Safe Overlay places translation on top of it).
- Password protected PDFs are not supported yet.
- Complex backgrounds may impede entirely clean overlays.
