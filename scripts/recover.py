import json

transcript_path = r'C:\Users\miure\.gemini\antigravity-ide\brain\86cb424b-d89c-4eef-ae20-e3e696ab87ce\.system_generated\logs\transcript.jsonl'
output_path = r'C:\Ingenieria de software\panaderia_amada\app\admin\routes_hr.py'

with open(transcript_path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for line in reversed(lines):
    data = json.loads(line)
    content = data.get('content', '')
    if 'The following changes were made by the multi_replace_file_content tool' in content and 'crear_empleado' in content and '@@ -86,668 +86,6 @@' in content:
        diff_lines = content.split('\n')
        reconstructed = []
        in_diff = False
        for l in diff_lines:
            if l == '[diff_block_start]':
                in_diff = True
                continue
            if l == '[diff_block_end]':
                in_diff = False
                continue
            if in_diff:
                if l.startswith('-'):
                    reconstructed.append(l[1:])
                elif l.startswith(' '):
                    reconstructed.append(l[1:])
        
        # Read the current file which has the first 85 lines and the end
        with open(output_path, 'r', encoding='utf-8') as current_f:
            current_lines = current_f.read().split('\n')
            
        final_file = current_lines[:85] + reconstructed + current_lines[143:] # 143 is where the rest of the file starts after the bad replace
        
        with open(output_path, 'w', encoding='utf-8') as out:
            out.write('\n'.join(final_file))
        print("Recovered!")
        break
