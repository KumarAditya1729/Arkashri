#!/usr/bin/env python3
"""
Server entry point for Arkashri Decision Engine
"""

from arkashri.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
