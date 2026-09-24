import os
import glob

def update_templates():
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(base_dir, 'templates')
    
    html_files = glob.glob(os.path.join(templates_dir, '**', '*.html'), recursive=True)
    
    target_str = """<link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">"""
    
    replacement_str = """<!-- Preload Fonts to improve LCP -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;500;600;700&family=Inter:wght@300;400;500;600;700&family=Outfit:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <!-- Bundled CSS -->
    <link rel="stylesheet" href="{{ url_for('static', filename='css/bundle.css') }}">"""

    for file_path in html_files:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        if target_str in content:
            new_content = content.replace(target_str, replacement_str)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f"Updated {os.path.basename(file_path)}")

if __name__ == '__main__':
    update_templates()
