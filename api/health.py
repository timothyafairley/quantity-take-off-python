"""
Health Check Endpoint
Simple endpoint to verify the API is running.
"""

from http.server import BaseHTTPRequestHandler
import json


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        response = {
            "status": "healthy",
            "service": "quantity-take-off-api",
            "version": "1.0.0"
        }
        self.wfile.write(json.dumps(response).encode('utf-8'))

