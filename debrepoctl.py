#!/usr/bin/env python3

import os
import sys
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
    group.add_argument('--export', action='store_true', help='Export concatenated Packages files from --input-dir to stdout')
    group.add_argument('--remove', action='store_true', help='Remove stanza files from --output-dir based on stdin list')
    group.add_argument('--copy', action='store_true', help='Copy stanza files from --input-dir to --output-dir based on stdin list')
    parser.add_argument('--output-dir', default='debian_packages', help='Output directory for imported repo')
    parser.add_argument('--input-dir', help='Input directory for export operation')
    parser.add_argument('--comp', default='main,contrib', help='Repository components to analyze')
    parser.add_argument('--arch', default='binary-amd64,source', help='Architectures to analyze')
    parser.add_argument('--dist', default='stable', help='Distributions to analyze')
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

def parse_packages(f):
    packages = []
    current_package = {}
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
        filename = Path(*parts[2:])
        file_path = os.path.join(output_dir, filename)
        dir_path = os.path.dirname(file_path)
        
        os.makedirs(dir_path, exist_ok=True)
        
        with open(file_path, 'w') as f:
            for key, value in pkg.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")

def remove_no_longer_exist(packages, output_dir):
    expected_files = set()
    for pkg in packages:
        if 'Filename' not in pkg:
            if 'Directory' not in pkg:
                continue
            filename = f'{pkg["Directory"]}/{pkg["Package"]}_{pkg["Version"]}.dsc'
        else:
            filename = pkg['Filename']
        parts = Path(filename).parts
        filename = str(Path(*parts[2:]))
        expected_files.add(filename)

    if not os.path.exists(output_dir):
        return

    for root, dirs, files in os.walk(output_dir, topdown=False):
        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, output_dir)
            
            if rel_path not in expected_files:
                try:
                    os.remove(filepath)
                    print(f"Removed orphaned file: {rel_path}")
                except OSError as e:
                    print(f"Error removing file {rel_path}: {e}")
        
        for dirname in dirs:
            dirpath = os.path.join(root, dirname)
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    print(f"Removed empty directory: {os.path.relpath(dirpath, output_dir)}")
            except (OSError, FileNotFoundError):
                pass

def import_repository(args):
    base_url = args.import_repo.rstrip('/')
    components = args.comp.split(',')
    architectures = args.arch.split(',')
    distributions = args.dist.split(',')
    
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
                with gzip.open(packages_gz_path, 'rt') as f:
                    packages = parse_packages(f)
                
                    output_dir = os.path.join(args.output_dir, dist, component, f"{arch}")
                
                    remove_no_longer_exist(packages, output_dir)
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
                
                with gzip.open(packages_gz_path, 'rt') as f:
                    packages = parse_packages(f)
                    
                    rel_path = os.path.relpath(root, local_dir)
                    output_dir = os.path.join(args.output_dir, rel_path)
                    
                    remove_no_longer_exist(packages, output_dir)
                    create_file_structure(packages, output_dir)

def read_packages_dir(input_dir):
    input_dir = Path(input_dir)
    lines = []
    for stanza_file in input_dir.rglob('*'):
        if not stanza_file.is_file(): continue
        with open(stanza_file, 'r') as in_f:
            lines.append(in_f.read())
    return "".join(lines).splitlines()

def remove_packages(lines, output_dir):
    if not os.path.exists(output_dir):
        return
    packages = parse_packages(read_packages_dir(output_dir))
    packages_dict = {}
    for p in packages:
        print(p)
        if all(key in p for key in ('Package', 'Version')):
            packages_dict[(p['Package'], p['Version'])] = p
    print(packages_dict)
    for line in lines:
        if not packages_dict.pop(tuple(line.split('=')), None):
            print("Key not found")
        else:
            print("Remove line", line)
    remove_no_longer_exist(packages_dict.values(), output_dir)

def copy_packages(package_names, input_dir, output_dir):
    if not os.path.exists(output_dir):
        return
    packages = parse_packages(read_packages_dir(input_dir))
    create_file_structure(packages, output_dir)

def main():
    args = parse_arguments()
    lines = []

    if any((args.remove, args.remove)):
        for line in sys.stdin:
            if line[0] == "#" or line.strip() == "": continue
            line_left_side = line.strip().split("=")[0]
            lines.append(line_left_side)
    
    if args.import_repo:
        import_repository(args)
    elif args.import_local:
        import_local(args)
    elif args.export:
        if not args.input_dir:
            print("Error: --input-dir is required for export operation")
            return
        print(read_packages_dir(args.input_dir))
    elif args.remove:
        remove_packages(lines, args.output_dir)
    elif args.copy:
        copy_packages(lines, args.input_dir, args.output_dir)

if __name__ == '__main__':
    main()
