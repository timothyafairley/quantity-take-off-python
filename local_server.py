"""
Local Development Server

Run this for local testing:
    python local_server.py

Then test with:
    curl -X POST http://localhost:5000/extract \
         -H "Content-Type: application/json" \
         -d '{"pdf_base64": "..."}'
"""

from flask import Flask, request, jsonify
import fitz  # PyMuPDF
import base64
import re
from typing import Dict, List, Any

app = Flask(__name__)


def cluster_text(spans: List[Dict], threshold: int = 5) -> List[Dict]:
    """Merges fragmented vector text based on proximity."""
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
        "all_text_elements": [],
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
    
    # Extract title block info
    title_patterns = {
        'drawing_number': r'(?:DWG|DRAWING)[\s.:]*([A-Z0-9-]+)',
        'revision': r'(?:REV|REVISION)[\s.:]*([A-Z0-9]+)',
        'scale': r'(?:SCALE)[\s.:]*(\d+:\d+|\d+\/\d+)',
        'date': r'(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})',
    }
    
    all_text = ' '.join([el['text'] for el in results.get('all_text_elements', [])])
    
    for key, pattern in title_patterns.items():
        match = re.search(pattern, all_text, re.IGNORECASE)
        if match:
            results['drawing_info'][key] = match.group(1)
    
    doc.close()
    return results


@app.route('/extract', methods=['POST', 'GET'])
def extract():
    if request.method == 'GET':
        return jsonify({
            "api": "PDF Drawing Extraction API",
            "version": "1.0.0",
            "usage": "POST /extract with {'pdf_base64': '<base64-pdf>'}"
        })
    
    try:
        data = request.get_json()
        
        if not data or 'pdf_base64' not in data:
            return jsonify({'error': 'Missing required field: pdf_base64'}), 400
        
        pdf_bytes = base64.b64decode(data['pdf_base64'])
        results = extract_drawing_elements(pdf_bytes)
        
        results['summary'] = {
            'total_pages': len(results['metadata']),
            'total_markers': len(results['markers']),
            'total_text_elements': len(results['all_text_elements']),
            'marker_types': list(results['markers'].keys())
        }
        
        return jsonify(results)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "healthy",
        "service": "quantity-take-off-api",
        "version": "1.0.0"
    })


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        "message": "Quantity Take-Off PDF Extraction API",
        "endpoints": {
            "POST /extract": "Extract text and markers from PDF",
            "GET /health": "Health check"
        }
    })


if __name__ == '__main__':
    print("Starting local development server...")
    print("API available at: http://localhost:5000/extract")
    app.run(host='0.0.0.0', port=5000, debug=True)

