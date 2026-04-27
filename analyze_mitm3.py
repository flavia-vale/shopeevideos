import sys
import re
import zlib

def extract_strings(filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Try to find gzipped chunks
    chunks = re.split(b'\x1f\x8b\x08', data)
    for i, chunk in enumerate(chunks):
        if i == 0: continue
        try:
            decompressed = zlib.decompress(b'\x1f\x8b\x08' + chunk, 16+zlib.MAX_WBITS)
            print(f"--- Decompressed Chunk {i} ---")
            # Look for URLs
            urls = re.findall(r'https?://[^\s"\'<>]+', decompressed.decode('utf-8', errors='ignore'))
            for url in urls:
                if 'shopee' in url:
                    print(url)
            
            # Look for JSON keys related to videos
            if b'video' in decompressed or b'item_id' in decompressed:
                print("Potential data found in chunk", i)
                # Print a bit of the content to see the structure
                print(decompressed[:1000].decode('utf-8', errors='ignore'))
        except Exception:
            pass

    # Raw strings search
    print("--- Raw Strings (Shopee/API) ---")
    strings = re.findall(b'[a-zA-Z0-9./?=&_-]{10,}', data)
    for s in strings:
        try:
            s_str = s.decode('utf-8')
            if 'shopee' in s_str and ('api' in s_str or 'v2' in s_str or 'v4' in s_str):
                print(s_str)
        except:
            pass

if __name__ == "__main__":
    extract_strings('.dyad/media/ef90e88d75b595abdd8807823db55f5d.mitm')
