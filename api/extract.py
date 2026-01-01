"""
PDF Extraction API for Construction Drawings
Vercel Serverless Function

Extracts text, markers, and structural layout from PDF drawings.
"""

from http.server import BaseHTTPRequestHandler
import json
import fitz  # PyMuPDF
import base64
import re
from typing import Dict, List, Any


def cluster_text(spans: List[Dict], threshold: int = 5) -> List[Dict]:
    """
    Merges fragmented vector text based on proximity.
    CAD software often splits text into individual characters - this fixes that.
    """
    if not spans:
        return []
    
    # Sort by Y (vertical position) then X (horizontal position)
    spans.sort(key=lambda s: (s['y'], s['x']))
    
    clusters = []
    if not spans:
        return clusters
    
    current = spans[0].copy()
    
    for next_span in spans[1:]:
        # Check if next span is on the same line and close horizontally
        same_line = abs(next_span['y'] - current['y']) < 2
        close_horizontally = (next_span['x'] - (current['x'] + len(current['text']) * 2)) < threshold
        
        if same_line and close_horizontally:
            # Merge the text
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
    """
    Identifies construction markers like BP1, C1, RW2, SC1, etc.
    Common patterns in structural/construction drawings.
    """
    patterns = [
        r'^[A-Z]{1,4}\d{1,3}[a-z]?$',      # BP1, SC2, RW3a
        r'^[A-Z]{1,2}-\d{1,3}$',            # C-1, B-12
        r'^[A-Z]\d{1,3}[A-Z]?$',            # A1, B12, C3A
        r'^(SC|BP|RW|FB|C|B|W)\d{1,3}$',    # Specific construction codes
    ]
    return any(re.match(p, text.strip()) for p in patterns)


def extract_drawing_elements(pdf_bytes: bytes) -> Dict[str, Any]:
    """
    Extract all text elements, markers, and drawing metadata from PDF.
    """
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
        
        # Extract raw text spans with full metadata
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
        
        # Apply text clustering to fix fragmented CAD text
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
            
            # Categorize the element
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
        
        # Extract vector graphics paths (for structure layout)
        drawings = page.get_drawings()
        page_data["vector_count"] = len(drawings)
        page_data["has_drawings"] = len(drawings) > 0
        
        # Get any images on the page
        images = page.get_images()
        page_data["image_count"] = len(images)
        
        results["pages"].append(page_data)
    
    # Try to extract title block information (usually bottom right)
    extract_title_block_info(results)
    
    doc.close()
    return results


def extract_title_block_info(results: Dict) -> None:
    """
    Extract common title block information from the drawing.
    Title blocks typically contain: Drawing number, revision, scale, date, etc.
    """
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


def extract_tables(page, results: Dict, page_num: int) -> None:
    """
    Attempt to detect and extract tabular data from the page.
    """
    # This is a simplified table detection - can be enhanced
    try:
        tables = page.find_tables()
        for table in tables:
            table_data = {
                'page': page_num + 1,
                'bbox': table.bbox,
                'rows': table.extract()
            }
            results['tables'].append(table_data)
    except Exception:
        # Table extraction might not be available in all PyMuPDF versions
        pass


class handler(BaseHTTPRequestHandler):
    """Vercel Serverless Function Handler"""
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.send_header('Access-Control-Max-Age', '86400')
        self.end_headers()
    
    def do_POST(self):
        """Handle PDF extraction requests"""
        try:
            # Read request body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Validate input
            if 'pdf_base64' not in data:
                self.send_error_response(400, 'Missing required field: pdf_base64')
                return
            
            # Decode PDF
            try:
                pdf_bytes = base64.b64decode(data['pdf_base64'])
            except Exception as e:
                self.send_error_response(400, f'Invalid base64 encoding: {str(e)}')
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
            "version": "1.0.0",
            "endpoints": {
                "POST /api/extract": {
                    "description": "Extract text and markers from PDF drawings",
                    "body": {
                        "pdf_base64": "Base64 encoded PDF file (required)"
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

