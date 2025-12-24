"""Main entry point for Snitch."""

import logging

import uvicorn

from .api import create_app
from .config import load_config


def setup_logging(config):
    """Configure logging."""
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(config.logging.file),
            logging.StreamHandler()
        ]
    )
    
    # Suppress uvicorn access logs
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    
    # Suppress httpx HTTP request logs
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main():
    """Run the application."""
    # Load configuration
    try:
        config = load_config()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return
    
    # Setup logging
    setup_logging(config)
    logger = logging.getLogger(__name__)
    
    logger.info("Starting Snitch...")
    
    # Create app
    app = create_app(config)
    
    # Run server
    uvicorn.run(
        app,
        host=config.server.host,
        port=config.server.port,
        log_config=None  # Use our own logging config
    )


if __name__ == "__main__":
    main()
