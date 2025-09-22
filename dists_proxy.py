#!/usr/bin/env python3
"""
Debian HTTP Proxy Service
Redirects requests to http://deb.debian.org/ but serves /dists/ files from local folder
"""

import http.server
import socketserver
import urllib.request
import urllib.parse
import os
from http import HTTPStatus

class DebianProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        try:
            # Check if the path contains "/dists/"
            print("path", self.path)
            if "/dists/" in self.path:
                self.serve_local_file()
            else:
                self.proxy_to_debian()
        except Exception as e:
            self.send_error(500, f"Internal server error: {str(e)}")

    def serve_local_file(self):
        """Serve file from local /tmp/dists/ folder"""
        # Extract the filename from the path
        path_parts = self.path.split('/dists/')
        if len(path_parts) > 1:
            filename = path_parts[1]
            local_path = os.path.join('/tmp/dists', filename)
            
            # Check if file exists locally
            if os.path.exists(local_path) and os.path.isfile(local_path):
                try:
                    with open(local_path, 'rb') as f:
                        content = f.read()
                    
                    # Determine content type based on file extension
                    content_type = self.guess_content_type(local_path)
                    
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-type", content_type)
                    self.send_header("Content-Length", str(len(content)))
                    self.end_headers()
                    self.wfile.write(content)
                    return
                except Exception as e:
                    self.send_error(404, f"Error reading local file: {str(e)}")
                    return
            else:
                print("no exists", local_path)
        
        # If local file doesn't exist, fall back to proxy
        self.proxy_to_debian()

    def proxy_to_debian(self):
        """Proxy request to http://deb.debian.org/"""
        target_url = f"http://deb.debian.org{self.path}"
        
        try:
            # Create request with original headers
            req = urllib.request.Request(target_url)
            
            # Copy headers from original request
            for header, value in self.headers.items():
                if header.lower() not in ['host', 'connection']:
                    req.add_header(header, value)
            
            # Make the request
            with urllib.request.urlopen(req) as response:
                # Get response content
                content = response.read()
                
                # Send response headers
                self.send_response(response.getcode())
                for header, value in response.headers.items():
                    if header.lower() not in ['connection', 'transfer-encoding']:
                        self.send_header(header, value)
                self.end_headers()
                
                # Send response content
                self.wfile.write(content)
                
        except urllib.error.HTTPError as e:
            self.send_error(e.code, e.reason)
        except Exception as e:
            self.send_error(500, f"Proxy error: {str(e)}")

    def guess_content_type(self, filename):
        """Guess content type based on file extension"""
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            '.deb': 'application/x-debian-package',
            '.gz': 'application/gzip',
            '.bz2': 'application/x-bzip2',
            '.xz': 'application/x-xz',
            '.txt': 'text/plain',
            '.html': 'text/html',
            '.css': 'text/css',
            '.js': 'application/javascript',
            '.json': 'application/json',
            '.xml': 'application/xml',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.gif': 'image/gif',
            '.ico': 'image/x-icon',
        }
        return content_types.get(ext, 'application/octet-stream')

def run_server():
    """Run the proxy server"""
    PORT = 8000
    HOST = 'localhost'
    
    with socketserver.TCPServer((HOST, PORT), DebianProxyHandler) as httpd:
        print(f"Debian proxy server running on {HOST}:{PORT}")
        print("Requests to /dists/ will be served from /tmp/dists/")
        print("All other requests will be proxied to http://deb.debian.org/")
        print("Press Ctrl+C to stop the server")
        
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down server...")
            httpd.shutdown()

if __name__ == "__main__":
    run_server()
