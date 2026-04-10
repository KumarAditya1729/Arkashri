#!/usr/bin/env python3
"""
Test script to check available routes
"""

import sys
sys.path.append('/Users/adityashrivastava/Desktop/company_1')

from fastapi import FastAPI
from arkashri.routers.reporting import router as reporting_router
from arkashri.routers.engine_status import router as status_router

app = FastAPI()
app.include_router(status_router, prefix="/api/v1")
app.include_router(reporting_router, prefix="/api/v1")

print('Available routes:')
for route in app.routes:
    if hasattr(route, 'path'):
        print(f'  {route.path} [{route.methods}]')
