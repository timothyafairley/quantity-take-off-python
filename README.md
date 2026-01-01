# Quantity Take-Off PDF Extraction API

A serverless Python API for extracting text, construction markers, and structural layout data from PDF construction/engineering drawings. Designed for deployment on Vercel.

## Features

- 📄 **PDF Text Extraction** - Extracts all text elements with precise coordinates
- 🏗️ **Construction Marker Detection** - Identifies markers like BP1, SC2, RW3, C-1, etc.
- 📐 **Layout Preservation** - Maintains spatial positioning of all elements
- 🔧 **CAD Text Clustering** - Fixes fragmented text common in CAD exports
- 📋 **Title Block Extraction** - Parses drawing numbers, revisions, scales, dates
- ⚡ **Serverless** - Runs on Vercel with zero infrastructure management

## API Endpoints

### `POST /api/extract`

Extract text and markers from a PDF drawing.

**Request Body:**
```json
{
  "pdf_base64": "<base64-encoded-pdf-content>"
}
```

**Response:**
```json
{
  "metadata": [
    {
      "page": 1,
      "width": 841.89,
      "height": 595.28,
      "rotation": 0
    }
  ],
  "markers": {
    "SC1": [{ "x": 100, "y": 200, "page": 1 }],
    "BP2": [{ "x": 300, "y": 400, "page": 1 }]
  },
  "all_text_elements": [
    {
      "text": "BASE PLATE DETAIL",
      "x": 150.5,
      "y": 100.2,
      "bbox": [150.5, 100.2, 280.3, 112.4],
      "font": "Arial",
      "size": 12,
      "page": 1,
      "type": "text"
    }
  ],
  "drawing_info": {
    "drawing_number": "533399-5",
    "revision": "A",
    "scale": "1:50"
  },
  "summary": {
    "total_pages": 1,
    "total_markers": 2,
    "total_text_elements": 45,
    "marker_types": ["SC1", "BP2"]
  }
}
```

### `GET /api/health`

Health check endpoint.

### `GET /api/extract`

Returns API documentation.

## Deployment

### Deploy to Vercel

1. **Push to GitHub:**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/timothyafairley/quantity-take-off-python.git
   git push -u origin main
   ```

2. **Deploy via Vercel:**
   - Go to [vercel.com](https://vercel.com)
   - Import your GitHub repository
   - Vercel auto-detects the Python project
   - Click Deploy

3. **Your API will be live at:**
   ```
   https://your-project.vercel.app/api/extract
   ```

## Local Development

### Prerequisites
- Python 3.9+
- pip

### Setup
```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
.\venv\Scripts\activate

# Activate (macOS/Linux)
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Run Locally with Flask (optional)
Create a `local_server.py` for testing:
```bash
python local_server.py
```

## Usage Examples

### Python
```python
import requests
import base64

# Read PDF file
with open("drawing.pdf", "rb") as f:
    pdf_base64 = base64.b64encode(f.read()).decode()

# Send to API
response = requests.post(
    "https://your-project.vercel.app/api/extract",
    json={"pdf_base64": pdf_base64}
)

data = response.json()
print(f"Found {len(data['markers'])} marker types")
for marker, locations in data['markers'].items():
    print(f"  {marker}: {len(locations)} occurrences")
```

### JavaScript/Node.js
```javascript
const fs = require('fs');

const pdfBuffer = fs.readFileSync('drawing.pdf');
const pdfBase64 = pdfBuffer.toString('base64');

fetch('https://your-project.vercel.app/api/extract', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ pdf_base64: pdfBase64 })
})
.then(res => res.json())
.then(data => console.log(data));
```

### cURL
```bash
# Encode PDF to base64 and send
base64 drawing.pdf | curl -X POST \
  -H "Content-Type: application/json" \
  -d "{\"pdf_base64\": \"$(cat -)\"}" \
  https://your-project.vercel.app/api/extract
```

## Marker Detection

The API detects common construction/structural markers:

| Pattern | Examples |
|---------|----------|
| `[A-Z]{1,4}\d{1,3}[a-z]?` | BP1, SC2, RW3a |
| `[A-Z]{1,2}-\d{1,3}` | C-1, B-12 |
| `[A-Z]\d{1,3}[A-Z]?` | A1, B12, C3A |
| Specific codes | SC, BP, RW, FB, C, B, W |

## Configuration

### Vercel Settings (`vercel.json`)
- **Max Duration:** 60 seconds
- **Memory:** 1024 MB
- **Runtime:** Python (automatic)

## Project Structure

```
quantity-take-off/
├── api/
│   ├── extract.py      # Main extraction endpoint
│   └── health.py       # Health check endpoint
├── requirements.txt    # Python dependencies
├── vercel.json        # Vercel configuration
├── local_server.py    # Optional local dev server
└── README.md          # This file
```

## License

MIT

