# Snitch

An *arr-style application for downloading image galleries using gallery-dl.

## Features

- 📥 Download galleries from any gallery-dl supported site
- 📁 Configurable download locations
- 🔄 Job queue system for managing downloads
- 🎯 StashApp integration for automatic library updates
- 🌐 REST API for external integrations (browser extensions, scripts)

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Copy example config
cp config.example.yaml config.yaml

# Edit config.yaml with your settings

# Run the service
python -m snitch.main
```

## API Endpoints

- `POST /api/download` - Submit URL(s) for download
- `GET /api/queue` - View download queue
- `GET /api/history` - View download history
- `GET /api/folders` - List configured download folders
- `POST /api/stash/scan` - Trigger StashApp library scan

## Configuration

See `config.example.yaml` for configuration options.
