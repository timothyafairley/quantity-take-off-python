"""
PDF Extraction API for Construction Drawings
Vercel Serverless Function

Extracts text, markers, and structural layout from PDF drawings.
Accepts both JSON (base64) and direct file uploads.
"""

from http.server import BaseHTTPRequestHandler
import json
import fitz  # PyMuPDF
import base64
import re
import cgi
import io
from typing import Dict, List, Any


def cluster_text(spans: List[Dict], threshold: int = 5) -> List[Dict]:
    """
    Merges fragmented vector text based on proximity.
    CAD software often splits text into individual characters - this fixes that.
    """
    if not spans:
        return []
    
    spans.sort(key=lambda s: (s['y'], s['x']))
    
    clusters = []
    if not spans:
        return clusters
    
    current = spans[0].copy()
    
    for next_span in spans[1:]:
        same_line = abs(next_span['y'] - current['y']) < 2
        close_horizontally = (next_span['x'] - (current['x'] + len(current['text']) * 2)) < threshold
        
        if same_line and close_horizontally:
            current['text'] += next_span['text']
            current['bbox'] = (
                current['bbox'][0],
                current['bbox'][1],
                next_span['bbox'][2],
                max(current['bbox'][3], next_span['bbox'][3])
            )
        else:
            if current['text'].strip():
                clusters.append(current)
            current = next_span.copy()
    
    if current['text'].strip():
        clusters.append(current)
    
    return clusters


def is_construction_marker(text: str) -> bool:
    """Identifies construction markers like BP1, C1, RW2, SC1, etc."""
    patterns = [
        r'^[A-Z]{1,4}\d{1,3}[a-z]?$',
        r'^[A-Z]{1,2}-\d{1,3}$',
        r'^[A-Z]\d{1,3}[A-Z]?$',
        r'^(SC|BP|RW|FB|C|B|W)\d{1,3}$',
    ]
    return any(re.match(p, text.strip()) for p in patterns)


def extract_drawing_elements(pdf_bytes: bytes) -> Dict[str, Any]:
    """Extract all text elements, markers, and drawing metadata from PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    
    results = {
        "metadata": [],
        "pages": [],
        "markers": {},
        "title_blocks": [],
        "all_text_elements": [],
        "tables": [],
        "drawing_info": {}
    }
    
    for page_num, page in enumerate(doc):
        page_data = {
            "page": page_num + 1,
            "width": round(page.rect.width, 2),
            "height": round(page.rect.height, 2),
            "rotation": page.rotation,
            "elements": []
        }
        results["metadata"].append({
            "page": page_num + 1,
            "width": page.rect.width,
            "height": page.rect.height,
            "rotation": page.rotation
        })
        
        raw_spans = []
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        
        for block in blocks:
            if "lines" not in block:
                continue
                
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    
                    raw_spans.append({
                        'text': text,
                        'x': round(span["bbox"][0], 2),
                        'y': round(span["bbox"][1], 2),
                        'bbox': tuple(round(v, 2) for v in span["bbox"]),
                        'font': span.get("font", ""),
                        'size': round(span.get("size", 0), 1),
                        'color': span.get("color", 0),
                        'flags': span.get("flags", 0)
                    })
        
        clean_elements = cluster_text(raw_spans)
        
        for el in clean_elements:
            text = el['text']
            
            element_data = {
                'text': text,
                'x': el['x'],
                'y': el['y'],
                'bbox': el['bbox'],
                'font': el.get('font', ''),
                'size': el.get('size', 0),
                'page': page_num + 1
            }
            
            if is_construction_marker(text):
                element_data['type'] = 'marker'
                if text not in results["markers"]:
                    results["markers"][text] = []
                results["markers"][text].append({
                    'x': el['x'],
                    'y': el['y'],
                    'bbox': el['bbox'],
                    'page': page_num + 1
                })
            else:
                element_data['type'] = 'text'
            
            page_data["elements"].append(element_data)
            results["all_text_elements"].append(element_data)
        
        drawings = page.get_drawings()
        page_data["vector_count"] = len(drawings)
        page_data["has_drawings"] = len(drawings) > 0
        
        images = page.get_images()
        page_data["image_count"] = len(images)
        
        results["pages"].append(page_data)
    
    extract_title_block_info(results)
    
    doc.close()
    return results


def extract_title_block_info(results: Dict) -> None:
    """Extract common title block information from the drawing."""
    title_patterns = {
        'drawing_number': r'(?:DWG|DRAWING)[\s.:]*([A-Z0-9-]+)',
        'revision': r'(?:REV|REVISION)[\s.:]*([A-Z0-9]+)',
        'scale': r'(?:SCALE)[\s.:]*(\d+:\d+|\d+\/\d+)',
        'date': r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
        'sheet': r'(?:SHEET|SHT)[\s.:]*(\d+)\s*(?:OF|/)\s*(\d+)',
    }
    
    all_text = ' '.join([el['text'] for el in results.get('all_text_elements', [])])
    
    for key, pattern in title_patterns.items():
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            results['drawing_info'][key] = match.group(1) if match.lastindex == 1 else match.groups()


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function Handler"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()
    
    def do_POST(self):
        """Handle PDF extraction requests - supports JSON and multipart form data"""
        try:
            content_type = self.headers.get('Content-Type', '')
            content_length = int(self.headers.get('Content-Length', 0))
            
            pdf_bytes = None
            
            # Handle multipart form data (file upload)
            if 'multipart/form-data' in content_type:
                # Parse the multipart form data
                form = cgi.FieldStorage(
                    fp=self.rfile,
                    headers=self.headers,
                    environ={
                        'REQUEST_METHOD': 'POST',
                        'CONTENT_TYPE': content_type,
                        'CONTENT_LENGTH': content_length,
                    }
                )
                
                # Look for file field (try common names)
                file_field = None
                for field_name in ['file', 'pdf', 'document', 'Drawing_PDF', 'data']:
                    if field_name in form:
                        file_field = form[field_name]
                        break
                
                # Also check all fields for a file
                if file_field is None:
                    for key in form.keys():
                        if form[key].filename:
                            file_field = form[key]
                            break
                
                if file_field and file_field.file:
                    pdf_bytes = file_field.file.read()
                else:
                    self.send_error_response(400, 'No file found in form data. Send file with field name: file, pdf, or document')
                    return
            
            # Handle JSON with base64
            elif 'application/json' in content_type or content_type == '':
                body = self.rfile.read(content_length)
                data = json.loads(body.decode('utf-8'))
                
                if 'pdf_base64' not in data:
                    self.send_error_response(400, 'Missing required field: pdf_base64')
                    return
                
                try:
                    pdf_bytes = base64.b64decode(data['pdf_base64'])
                except Exception as e:
                    self.send_error_response(400, f'Invalid base64 encoding: {str(e)}')
                    return
            
            # Handle raw binary PDF
            elif 'application/pdf' in content_type:
                pdf_bytes = self.rfile.read(content_length)
            
            # Handle octet-stream (binary)
            elif 'application/octet-stream' in content_type:
                pdf_bytes = self.rfile.read(content_length)
            
            else:
                self.send_error_response(400, f'Unsupported Content-Type: {content_type}. Use application/json, multipart/form-data, or application/pdf')
                return
            
            if not pdf_bytes or len(pdf_bytes) == 0:
                self.send_error_response(400, 'Empty PDF data received')
                return
            
            # Extract data from PDF
            results = extract_drawing_elements(pdf_bytes)
            
            # Add summary statistics
            results['summary'] = {
                'total_pages': len(results['metadata']),
                'total_markers': len(results['markers']),
                'total_text_elements': len(results['all_text_elements']),
                'marker_types': list(results['markers'].keys())
            }
            
            # Send response
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps(results, indent=2).encode('utf-8'))
            
        except json.JSONDecodeError as e:
            self.send_error_response(400, f'Invalid JSON: {str(e)}')
        except Exception as e:
            self.send_error_response(500, f'Extraction failed: {str(e)}')
    
    def send_error_response(self, status_code: int, message: str):
        """Send error response with CORS headers"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps({'error': message}).encode('utf-8'))
    
    def do_GET(self):
        """Handle GET requests - return API info"""
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        info = {
            "api": "PDF Drawing Extraction API",
            "version": "1.1.0",
            "endpoints": {
                "POST /api/extract": {
                    "description": "Extract text and markers from PDF drawings",
                    "content_types": [
                        "application/json (with pdf_base64 field)",
                        "multipart/form-data (file upload)",
                        "application/pdf (raw binary)"
                    ],
                    "json_body": {
                        "pdf_base64": "Base64 encoded PDF file"
                    },
                    "form_data": {
                        "file": "PDF file upload (or: pdf, document, data)"
                    },
                    "response": {
                        "metadata": "Page dimensions and info",
                        "markers": "Construction markers found (BP1, SC2, etc.)",
                        "all_text_elements": "All text with positions",
                        "drawing_info": "Extracted title block info",
                        "summary": "Statistics about the extraction"
                    }
                }
            }
        }
        self.wfile.write(json.dumps(info, indent=2).encode('utf-8'))
