import sys
import re

def extract_strings(filename, output_filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Find all sequences of printable characters
    strings = re.findall(b'[a-zA-Z0-9./?=&_-]{5,}', data)
    with open(output_filename, 'w') as out:
        for s in strings:
            try:
                out.write(s.decode('utf-8') + '\n')
            except:
                pass

if __name__ == "__main__":
    extract_strings('.dyad/media/1f6dd4416d5ad9966f1399c2a2722d0e.mitm', 'strings1.txt')
    extract_strings('.dyad/media/f306333995e49235958be36ecaae81d8.mitm', 'strings2.txt')
