#!/usr/bin/env python3

import os
import sys
import gzip
import argparse
from pathlib import Path
import urllib.request
import shutil
import tempfile
import logging

def parse_arguments():
    parser = argparse.ArgumentParser(description='Debian Packages Analyzer')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('-u', '--import-url', \
        help='Import from Debian repository URL (e.g., https://ftp.debian.org/debian/dists/trixie/main/binary-amd64)')
    group.add_argument('-l', '--import-local', help='Import from local directory containing Packages.gz files')
    group.add_argument('-e', '--export', action='store_true', help='Export concatenated Packages files from --input-dir to stdout')
    group.add_argument('-r', '--remove', action='store_true', help='Remove stanza files from --output-dir based on stdin list')
    group.add_argument('-c', '--copy', action='store_true', help='Copy stanza files from --input-dir to --output-dir based on stdin list')
    parser.add_argument('-o', '--output-dir', default='debian_packages', \
        help='Output directory for imported repo, (e.g. /debian/dists/trixie/main/source)')
    parser.add_argument('-i', '--input-dir', help='Input directory for export operation')
    parser.add_argument('-g', '--log-level', default='INFO', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'], \
        help='set the logging level (default: DEBUG)')    
    parser.add_argument('--log-file', help="save logs to file (default: stderr)")

    return parser.parse_args()

def download_packages_gz(url):
    logging.info(f"Downloading package metadata from: {url}")
    try:
        with urllib.request.urlopen(url) as response:
            with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                shutil.copyfileobj(response, tmp_file)
                logging.debug(f"Downloaded {url} to temporary file: {tmp_file.name}")
                return tmp_file.name
    except urllib.error.URLError as e:
        logging.error(f"Error downloading {url}: {e}")
        return None

def parse_packages(f):
    logging.debug("Parsing package metadata")
    packages = []
    current_package = {}
    for line in f:
        line = line.strip()
        if not line:
            # Empty line indicates end of current package stanza
            if current_package:
                packages.append(current_package)
                current_package = {}
        else:
            if ':' in line:
                # Key-value pair
                key, value = line.split(':', 1)
                current_package[key.strip()] = value.strip()
            elif current_package:
                # Continuation line (multi-line field)
                last_key = list(current_package.keys())[-1]
                current_package[last_key] += '\n' + line
    # Add the last package if file doesn't end with empty line
    if current_package:
        packages.append(current_package)
    logging.info(f"Parsed {len(packages)} packages from metadata")
    return packages

def create_file_structure(packages, output_dir):
    logging.info(f"Creating file structure for {len(packages)} packages in {output_dir}")
    for pkg in packages:
        # Determine filename based on package type (binary or source)
        if 'Filename' not in pkg:
            if 'Directory' not in pkg:
                logging.warning(f"Skipping package without Filename or Directory: {pkg.get('Package', 'Unknown')}")
                continue
            filename = f'{pkg["Directory"]}/{pkg["Package"]}_{pkg["Version"]}.dsc'
        else:
            filename = pkg['Filename']
        # Remove the first two path components (pool/component/)
        parts = Path(filename).parts
        filename = Path(*parts[2:])
        file_path = os.path.join(output_dir, filename)
        dir_path = os.path.dirname(file_path)
        
        os.makedirs(dir_path, exist_ok=True)
        logging.debug(f"Creating directory: {dir_path}")
        
        with open(file_path, 'w') as f:
            for key, value in pkg.items():
                f.write(f"{key}: {value}\n")
            f.write("\n")
        logging.debug(f"Created package file: {file_path}")

def remove_no_longer_exist(packages, output_dir):
    logging.info(f"Cleaning up orphaned files in {output_dir}")
    # Build set of expected files
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
        logging.warning(f"Output directory does not exist: {output_dir}")
        return

    # Remove files that are not in expected set
    removed_count = 0
    for root, dirs, files in os.walk(output_dir, topdown=False):
        for filename in files:
            filepath = os.path.join(root, filename)
            rel_path = os.path.relpath(filepath, output_dir)
            parts = Path(rel_path).parts
            rel_path = str(Path(*parts[2:]))
            if rel_path not in expected_files:
                try:
                    os.remove(filepath)
                    removed_count += 1
                    logging.info(f"Removed orphaned file: {rel_path}")
                except OSError as e:
                    logging.warning(f"Package not found for removal: {line}")
        # Remove empty directories
        for dirname in dirs:
            dirpath = os.path.join(root, dirname)
            try:
                if not os.listdir(dirpath):
                    os.rmdir(dirpath)
                    logging.info(f"Removed empty directory: {os.path.relpath(dirpath, output_dir)}")
            except (OSError, FileNotFoundError):
                logging.warning(f"Could not remove directory {dirpath}: {e}")

    logging.info(f"Cleanup completed. Removed {removed_count} orphaned files.")

def import_repository(args):
    logging.info(f"Starting repository import from: {args.import_url}")

    base_url = args.import_url.rstrip('/')
    
    # Construct URL for Packages.gz or Sources.gz
    url = f"{base_url}/Packages.gz"
    if arch == "source":
        url = f"{base_url}/Sources.gz"

    logging.info(f"Processing: {url}")

    # Download and process the metadata file
    packages_gz_path = download_packages_gz(url)
    if not packages_gz_path:
        logging.warning(f"Skipping {url} due to download error")
    with gzip.open(packages_gz_path, 'rt') as f:
        packages = parse_packages(f)
    
        output_dir = os.path.join(args.output_dir)
        
        logging.info(f"Output directory: {output_dir}")
        remove_no_longer_exist(packages, output_dir)
        create_file_structure(packages, output_dir)
    
    os.unlink(packages_gz_path)

def import_local(args):
    local_dir = args.import_local
    logging.info(f"Starting local import from: {local_dir}")
    if not os.path.isdir(local_dir):
        logging.error(f"Directory not found: {local_dir}")
        return
    
    processed_count = 0
    for root, _, files in os.walk(local_dir):
        for file in files:
            if file in ('Packages.gz', 'Sources.gz'):
                packages_gz_path = os.path.join(root, file)
                logging.info(f"Processing local file: {packages_gz_path}")
                
                with gzip.open(packages_gz_path, 'rt') as f:
                    packages = parse_packages(f)
                    
                    rel_path = os.path.relpath(root, local_dir)
                    output_dir = os.path.join(args.output_dir, rel_path)
                    logging.info(f"Output directory: {output_dir}")

                    remove_no_longer_exist(packages, output_dir)
                    create_file_structure(packages, output_dir)
                    processed_count += 1

    logging.info(f"Local import completed. Processed {processed_count} files.")

def read_packages_dir(input_dir):
    logging.info(f"Reading package files from: {input_dir}")
    input_dir = Path(input_dir)
    lines = []
    file_count = 0
    for stanza_file in input_dir.rglob('*'):
        if not stanza_file.is_file(): continue
        with open(stanza_file, 'r') as in_f:
            lines.append(in_f.read())
            file_count += 1
    logging.info(f"Read {file_count} package files")
    return "".join(lines).splitlines()

def remove_packages(lines, output_dir):
    logging.info(f"Removing packages from: {output_dir}")
    if not os.path.exists(output_dir):
        logging.warning(f"Output directory does not exist: {output_dir}")
        return
    # Read existing packages
    packages = parse_packages(read_packages_dir(output_dir))
    packages_dict = {}
    # Create dictionary for easy lookup 
    for p in packages:
        if all(key in p for key in ('Package', 'Version')):
            packages_dict[(p['Package'], p['Version'])] = p
        else:
            logging.warning(f"Skipping package without Package or Version field: {p}")

    # Remove packages specified in input
    removed_count = 0
    for line in lines:
        if tuple(line.split('=')) in packages_dict:
            del packages_dict[tuple(line.split('='))]
            logging.info(f"Marked package for removal: {line}")
            removed_count += 1
        else:
            logging.warning(f"Package not found for removal: {line}")
            
    # Update the directory structure
    remove_no_longer_exist(list(packages_dict.values()), output_dir)
    logging.info(f"Removed {removed_count} packages")

def copy_packages(package_names, input_dir, output_dir):
    logging.info(f"Copying packages from {input_dir} to {output_dir}")
    if not os.path.exists(output_dir):
        logging.error(f"No output directory: {output_dir}")
        return
    packages = parse_packages(read_packages_dir(input_dir))
    create_file_structure(packages, output_dir)

def main():
    args = parse_arguments()

    # Configure logging system
    handlers = []
    if args.log_file: handlers.append(logging.FileHandler(args.log_file)) 
    else: handlers.append(logging.StreamHandler())
    logging.basicConfig(handlers=handlers, level=getattr(logging, args.log_level), format='%(asctime)s %(levelname)s %(message)s')

    logging.debug(f'Debrepoctl started with command line options: {args}')

    lines = []

    if any((args.remove, args.remove)):
        logging.info("Reading package names from stdin")
        for line in sys.stdin:
            if line[0] == "#" or line.strip() == "": continue
            lines.append(line.strip())
        logging.debug(f"Read {len(lines)} package names from stdin")
    
    if args.import_url:
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
    
    logging.info('Debrepoctl completed successfully')

if __name__ == '__main__':
    main()
