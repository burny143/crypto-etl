#!/usr/bin/env python3
"""
consolidate_code.py - Recursively scan a project directory and combine all source code files into a single Markdown file.

Usage:
    python consolidate_code.py [-r ROOT] [-o OUTPUT] [-e EXTENSIONS] [-s SIZE_LIMIT]

Examples:
    python consolidate_code.py                    # Scan current directory, output to project_code.md
    python consolidate_code.py -r . -o code.md  # Custom root and output
    python consolidate_code.py -e py,js,ts      # Only include specific extensions
"""

import argparse
import os
import sys


# Default source code file extensions
DEFAULT_EXTENSIONS = {
    # Python
    ".py",
    # JavaScript/TypeScript
    ".js", ".mjs", ".cjs",
    ".ts", ".mts",
    # Web
    ".html", ".htm",
    ".css", ".scss", ".sass",
    ".jsx", ".tsx",
    # Configuration & Markup
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".xml",
    # Build & Makefile
    ".make", ".mk",
    # Shell & Script
    ".sh", ".bash", ".zsh", ".fish",
    ".ps1",
    # Markup/Content
    ".md", ".rst",
    # Database & Query
    ".sql",
    # Docker & Kubernetes
    ".dockerfile",
    # Go, Rust, Java, C/C++
    ".go", ".rs", ".java", ".c", ".h", ".cpp", ".hpp", ".cs",
    # Other
    ".rb", ".pl", ".pm",
    ".php",
    ".swift", ".kt",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Recursively scan a project directory and combine source code files into a single Markdown file."
    )
    parser.add_argument(
        "-r",
        "--root",
        default=".",
        help="Root directory to scan (default: current directory, '.').",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="project_code.md",
        help="Output Markdown file path (default: 'project_code.md').",
    )
    parser.add_argument(
        "-e",
        "--extensions",
        default=None,
        help=(
            "Comma-separated list of file extensions to include (e.g., 'py,js,ts'). "
            "If not specified, uses default source code extensions."
        ),
    )
    parser.add_argument(
        "-s",
        "--size-limit",
        type=int,
        default=2 * 1024 * 1024,
        help="Maximum file size in bytes to include (default: 2 MB).",
    )
    return parser.parse_args()


def parse_extensions(ext_str):
    """Parse a comma-separated extension string into a set of lowercase extensions."""
    if not ext_str:
        return None
    exts = set()
    for e in ext_str.split(","):
        e = e.strip()
        if e:
            # Ensure leading dot
            if not e.startswith("."):
                e = "." + e
            exts.add(e.lower())
    return exts


def is_binary_file(filepath, size_limit):
    """Check if a file is binary by looking for null bytes in the first 1024 bytes."""
    try:
        with open(filepath, "rb") as f:
            chunk = f.read(min(1024, size_limit))
            return b"\x00" in chunk
    except (OSError, IOError):
        return True


def get_file_language(extension):
    """Determine the syntax highlighting language from a file extension."""
    lang_map = {
        ".py": "python",
        ".js": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".ts": "typescript",
        ".mts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".html": "html",
        ".htm": "html",
        ".css": "css",
        ".scss": "scss",
        ".sass": "sass",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".conf": "ini",
        ".xml": "xml",
        ".sh": "bash",
        ".bash": "bash",
        ".zsh": "zsh",
        ".fish": "fish",
        ".ps1": "powershell",
        ".md": "markdown",
        ".rst": "restructuredtext",
        ".sql": "sql",
        ".dockerfile": "dockerfile",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".rb": "ruby",
        ".pl": "perl",
        ".pm": "perl",
        ".php": "php",
        ".swift": "swift",
        ".kt": "kotlin",
    }
    return lang_map.get(extension.lower())


def read_file_content(filepath, size_limit):
    """Read file content as UTF-8, falling back to Latin-1."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        return content
    except UnicodeDecodeError:
        try:
            with open(filepath, "r", encoding="latin-1") as f:
                content = f.read()
            return content
        except (UnicodeDecodeError, OSError, IOError):
            return None


def should_skip_directory(dirname, skip_dirs):
    """Check if a directory name should be skipped."""
    normalized = dirname.lower()
    return normalized in skip_dirs


def find_source_files(root_dir, extensions=None, size_limit=2 * 1024 * 1024, skip_dirs=None):
    """Recursively find source code files in the root directory."""
    if skip_dirs is None:
        skip_dirs = {
            ".git", ".svn", ".hg", "node_modules", "__pycache__",
            ".venv", "venv", "env", "dist", "build", "target",
            "bin", "obj", ".idea", ".vscode", "coverage",
            ".next", ".nuxt", "vendor", "bower_components",
            "Pods", "Carthage", "DerivedData",
            ".gradle", ".mvn", ".npm", ".yarn", ".pnp",
        }

    # Normalize extensions filter
    if extensions is not None:
        extensions = parse_extensions(",".join(extensions)) if isinstance(extensions, list) else parse_extensions(extensions)
    else:
        extensions = DEFAULT_EXTENSIONS

    source_files = []

    # Use os.walk for cross-platform recursive traversal
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Filter out skipped directories (modify in-place to prevent descending)
        dirnames[:] = [d for d in dirnames if not should_skip_directory(d, skip_dirs)]
        # Sort dirnames for consistent traversal order
        dirnames.sort()

        for filename in filenames:
            # Skip hidden files that might be config/system
            normalized_dir = dirpath.lower()

            # Check if any skipped directory is in the path
            parts = dirpath.replace("\\", "/").split("/")
            skip = False
            for part in parts:
                if part.lower() in skip_dirs:
                    skip = True
                    break
            if skip:
                continue

            filepath = os.path.join(dirpath, filename)

            # Skip the output markdown file itself
            # We'll handle this later after collecting all files, but also check here
            # Actually, let's just skip if it matches the output name pattern - we'll do a more thorough check later

            # Check file extension
            _, ext = os.path.splitext(filename)
            if extensions is not None and ext.lower() not in extensions:
                continue

            # Check file size
            try:
                file_size = os.path.getsize(filepath)
            except OSError:
                continue
            if file_size > size_limit:
                continue

            # Check for binary files
            if is_binary_file(filepath, size_limit):
                continue

            # Compute relative path from root
            try:
                rel_path = os.path.relpath(filepath, root_dir)
            except ValueError:
                continue

            source_files.append((filepath, rel_path, ext))

    # Sort by relative path for consistent output
    source_files.sort(key=lambda x: x[1])
    return source_files


def main():
    args = parse_args()

    root_dir = os.path.abspath(args.root)
    output_path = os.path.abspath(args.output)
    size_limit = args.size_limit
    extensions = args.extensions

    # Determine which extensions to use
    if extensions is not None:
        ext_set = parse_extensions(extensions)
    else:
        ext_set = None  # Use defaults

    # Find all source files
    source_files = find_source_files(root_dir, extensions=ext_set, size_limit=size_limit, skip_dirs=None)

    # Remove the output file from the list if it's included
    filtered_files = []
    for filepath, rel_path, ext in source_files:
        # Normalize paths for comparison
        output_norm = output_path.replace("\\", "/")
        rel_norm = rel_path.replace("\\", "/")
        # Also check if the output path itself is in the relative path
        if output_norm == rel_norm or output_norm.endswith("/" + rel_norm) or rel_norm == output_path:
            continue
        filtered_files.append((filepath, rel_path, ext))

    total_files = len(filtered_files)

    # Ensure output directory exists
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Generate Markdown content
    markdown_lines = []

    # Title section
    markdown_lines.append(f"# Project Code Consolidation")
    markdown_lines.append("")
    markdown_lines.append(f"**Source Directory:** `{root_dir}`")
    markdown_lines.append(f"**Total Files:** {total_files}")
    markdown_lines.append("")

    # File entries
    for filepath, rel_path, ext in filtered_files:
        # Determine syntax highlighting language
        language = get_file_language(ext)
        if language:
            code_fence = f"```{language}"
        else:
            code_fence = "```"

        markdown_lines.append(f"## File: {rel_path}")
        markdown_lines.append("")
        markdown_lines.append(code_fence)
        try:
            content = read_file_content(filepath, size_limit)
            if content is not None:
                # Escape any triple backticks in the content to avoid breaking the fence
                content_escaped = content.replace("```", "\u200b\u200b```")
                markdown_lines.append(content_escaped)
            else:
                markdown_lines.append("_Failed to read file (encoding issue)_")
        except (OSError, IOError) as e:
            markdown_lines.append(f"_Failed to read file: {e}_")
        markdown_lines.append(code_fence + "`")
        markdown_lines.append("")

    # Write the Markdown file
    markdown_content = "\n".join(markdown_lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(markdown_content)

    # Print summary
    print(f"Consolidated {total_files} files into {output_path}")
    print(f"Source directory: {root_dir}")


if __name__ == "__main__":
    main()