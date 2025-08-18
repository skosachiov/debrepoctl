#!/usr/bin/env python3
import os
import gzip
import argparse
from pathlib import Path
import urllib.request
import shutil
import tempfile

def parse_arguments():
    parser = argparse.ArgumentParser(description='Debian Packages Analyzer')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--import-repo', help='Import from Debian repository URL (e.g., https://ftp.debian.org/debian/)')
    group.add_argument('--import-local', help='Import from local directory containing Packages.gz files')
    group.add_argument('--export-file', action='store_true', help='Export concatenated Packages file')
    parser.add_argument('--output-dir', default='debian_packages', help='Output directory for imported files')
    parser.add_argument('--input-dir', help='Input directory for export operation')
    parser.add_argument('--components', default='main,contrib', help='Repository components to analyze')
    parser.add_argument('--architectures', default='binary-amd64,source', help='Architectures to analyze')
    parser.add_argument('--distributions', default='stable', help='Distributions to analyze')
    return parser.parse_args()

def download_packages_gz(url):
    try:
        with urllib.request.urlopen(url) as response:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                shutil.copyfileobj(response, tmp_file)
                return tmp_file.name
    except urllib.error.URLError as e:
        print(f"Error downloading {url}: {e}")
        return None

def parse_packages_gz(packages_gz_path):
    packages = []
    current_package = {}
    
    try:
        with gzip.open(packages_gz_path, 'rt') as f:
            for line in f:
                line = line.strip()
                if not line:
                    if current_package:
                        packages.append(current_package)
                        current_package = {}
                else:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        current_package[key.strip()] = value.strip()
                    elif current_package:
                        last_key = list(current_package.keys())[-1]
                        current_package[last_key] += '\n' + line
    except Exception as e:
        print(f"Error parsing {packages_gz_path}: {e}")
    
    return packages

def create_file_structure(packages, output_dir):
    for pkg in packages:
        if 'Filename' not in pkg:
            if 'Directory' not in pkg:
                continue
            filename = f'{pkg["Directory"]}/{pkg["Package"]}_{pkg["Version"]}.dsc'
        else:
            filename = pkg['Filename']
        parts = Path(filename).parts
        filename = Path(*parts[3:])
        file_path = os.path.join(output_dir, filename)
        dir_path = os.path.dirname(file_path)
        
        os.makedirs(dir_path, exist_ok=True)
        
        with open(file_path, 'w') as f:
            for key, value in pkg.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")

def import_repository(args):
    base_url = args.import_repo.rstrip('/')
    components = args.components.split(',')
    architectures = args.architectures.split(',')
    distributions = args.distributions.split(',')
    
    for dist in distributions:
        for component in components:
            for arch in architectures:
                url = f"{base_url}/dists/{dist}/{component}/{arch}/Packages.gz"
                if arch == "source":
                    url = f"{base_url}/dists/{dist}/{component}/{arch}/Sources.gz"
                print(f"Processing: {url}")
                
                packages_gz_path = download_packages_gz(url)
                if not packages_gz_path:
                    continue
                
                packages = parse_packages_gz(packages_gz_path)
                
                output_dir = os.path.join(args.output_dir, dist, component, f"{arch}")
                create_file_structure(packages, output_dir)
                
                os.unlink(packages_gz_path)

def import_local(args):
    local_dir = args.import_local
    if not os.path.isdir(local_dir):
        print(f"Error: Directory not found: {local_dir}")
        return
    
    for root, _, files in os.walk(local_dir):
        for file in files:
            if file in ('Packages.gz', 'Sources.gz'):
                packages_gz_path = os.path.join(root, file)
                print(f"Processing local file: {packages_gz_path}")
                
                packages = parse_packages_gz(packages_gz_path)
                
                # Determine output path based on relative path from input dir
                rel_path = os.path.relpath(root, local_dir)
                output_dir = os.path.join(args.output_dir, rel_path)
                
                create_file_structure(packages, output_dir)

def export_packages_file(args):
    if not args.input_dir:
        print("Error: --input-dir is required for export operation")
        return
        
    input_dir = Path(args.input_dir)
    output_file = os.path.join(args.output_dir, 'Packages')
    
    with open(output_file, 'w') as out_f:
        for stanza_file in input_dir.rglob('*'):
            with open(stanza_file, 'r') as in_f:
                out_f.write(in_f.read())
    
    print(f"Created concatenated Packages file at: {output_file}")

def main():
    args = parse_arguments()
    
    if args.import_repo:
        import_repository(args)
    elif args.import_local:
        import_local(args)
    elif args.export_file:
        export_packages_file(args)

if __name__ == '__main__':
    main()
