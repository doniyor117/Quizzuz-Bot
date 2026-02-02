import asyncio
import os
from bot_services.export_service import generate_set_pdf

async def test_pdf():
    print("Testing PDF generation...")
    
    # Mock data
    set_data = {'set_name': 'Test Set', 'created_at': '2025-11-27'}
    cards = [{'term': 'Hello', 'definition': 'World'}, {'term': 'Test', 'definition': 'Passed'}]
    
    try:
        path = await generate_set_pdf(set_data, cards)
        print(f"✅ PDF generated at: {path}")
        
        # Check file size
        size = os.path.getsize(path)
        print(f"File size: {size} bytes")
        
        if size > 0:
            print("SUCCESS: PDF generation works!")
        else:
            print("FAILURE: PDF is empty")
            
    except Exception as e:
        print(f"❌ ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_pdf())
