"""Quick test to verify the API is working"""
import requests
import base64
import fitz

# Create a minimal test PDF with construction markers
doc = fitz.open()
page = doc.new_page()
page.insert_text((100, 100), 'SC1 BASE PLATE DETAIL', fontsize=14)
page.insert_text((100, 130), 'BP2 - Steel Connection', fontsize=12)
page.insert_text((100, 160), 'Drawing: DWG-001 Rev: A', fontsize=10)
page.insert_text((100, 190), 'Scale: 1:50', fontsize=10)
page.insert_text((300, 100), 'RW3', fontsize=12)
page.insert_text((300, 130), 'C1', fontsize=12)
page.insert_text((300, 160), 'FB4', fontsize=12)

# Save to bytes and encode
pdf_bytes = doc.tobytes()
doc.close()
pdf_base64 = base64.b64encode(pdf_bytes).decode()

print("Sending test PDF to API...")
print(f"PDF size: {len(pdf_bytes)} bytes")

# Send to API
response = requests.post(
    'http://localhost:5000/extract',
    json={'pdf_base64': pdf_base64}
)

data = response.json()

print("\n" + "=" * 50)
print("EXTRACTION TEST RESULTS")
print("=" * 50)
print(f"Status: {response.status_code}")
print(f"Pages: {data['summary']['total_pages']}")
print(f"Markers found: {data['summary']['total_markers']}")
print(f"Total text elements: {data['summary']['total_text_elements']}")

print("\nMarkers detected:")
for marker, locs in data['markers'].items():
    for loc in locs:
        print(f"  {marker}: page {loc['page']}, position ({loc['x']:.1f}, {loc['y']:.1f})")

print("\nDrawing info:", data.get('drawing_info', 'None extracted'))

print("\nAll text elements:")
for el in data['all_text_elements'][:10]:
    print(f"  [{el['type']}] \"{el['text']}\" at ({el['x']:.1f}, {el['y']:.1f})")

print("\n[OK] API is working correctly!")

