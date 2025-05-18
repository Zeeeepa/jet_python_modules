import json
import os
import shutil
import sys
from pathlib import Path
from jet.file.utils import save_file
from jet.code.utils import remove_single_line_comments_preserving_triple_quotes


def extract_text_from_ipynb(notebook_path, include_outputs=True, include_code=False, include_comments=False):
    """Extract text content from a Jupyter notebook and return as markdown."""
    try:
        with open(notebook_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)
        markdown_content = []
        for cell in notebook.get('cells', []):
            if cell['cell_type'] == 'markdown':
                markdown_content.extend(cell['source'])
                markdown_content.append('')
            elif cell['cell_type'] == 'code':
                if include_code:
                    code_content = ''.join(cell['source'])
                    if not include_comments:
                        code_content = remove_single_line_comments_preserving_triple_quotes(
                            code_content)
                    markdown_content.append('```python')
                    markdown_content.append(code_content)
                    markdown_content.append('```')
                    markdown_content.append('')
                if include_outputs:
                    for output in cell.get('outputs', []):
                        if 'text' in output:
                            markdown_content.append('```output')
                            markdown_content.extend(output['text'])
                            markdown_content.append('```')
                            markdown_content.append('')
                        elif 'data' in output and 'text/plain' in output['data']:
                            markdown_content.append('```output')
                            markdown_content.extend(
                                output['data']['text/plain'])
                            markdown_content.append('```')
                            markdown_content.append('')
        return '\n'.join(line.rstrip() for line in markdown_content)
    except Exception as e:
        print(f"Error processing {notebook_path}: {str(e)}")
        return None


def extract_comments(input_path, output_dir=None, include_outputs=True, include_code=False, include_comments=False) -> str:
    """Process a single notebook file or directory of notebooks and save as markdown."""
    content = ""
    if os.path.isdir(input_path):
        for file in Path(input_path).glob('*.ipynb'):
            result = extract_text_from_ipynb(
                file,  # Use 'file' instead of 'input_path'
                include_outputs=include_outputs,
                include_code=include_code,
                include_comments=include_comments
            )
            if result is not None:  # Check for None before concatenation
                content += f"\n# {file.name}\n"
                content += result
                content += "\n\n"
            else:
                print(f"Skipping {file} due to processing error")
    else:
        result = extract_text_from_ipynb(
            input_path,
            include_outputs=include_outputs,
            include_code=include_code,
            include_comments=include_comments
        )
        if result is not None:  # Check for None before concatenation
            content += result
        else:
            print(f"Skipping {input_path} due to processing error")
    return content
