import sys
import re
import zlib

def extract_strings(filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Try to find gzipped chunks
    # Gzip header is 1f 8b 08
    chunks = re.split(b'\x1f\x8b\x08', data)
    for i, chunk in enumerate(chunks):
        if i == 0: continue
        try:
            # Add the header back
            decompressed = zlib.decompress(b'\x1f\x8b\x08' + chunk, 16+zlib.MAX_WBITS)
            print(f"--- Decompressed Chunk {i} ---")
            # Extract URLs or interesting strings
            urls = re.findall(r'https?://[^\s"\'<>]+', decompressed.decode('utf-8', errors='ignore'))
            for url in urls:
                print(url)
            
            # Look for JSON-like structures
            if b'item_id' in decompressed or b'video' in decompressed:
                print("Found potential data in chunk", i)
                print(decompressed[:500].decode('utf-8', errors='ignore'))
        except Exception:
            pass

    # Also just look for strings in the raw data
    print("--- Raw Strings ---")
    strings = re.findall(b'[a-zA-Z0-9./?=&_-]{10,}', data)
    for s in strings:
        try:
            s_str = s.decode('utf-8')
            if 'shopee' in s_str or 'api' in s_str:
                print(s_str)
        except:
            pass

if __name__ == "__main__":
    if len(sys.argv) > 1:
        extract_strings(sys.argv[1])
